#!/usr/bin/env python3
import requests
import argparse
import json
import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from difflib import ndiff

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_HOST = 'http://tux:11434'
DEFAULT_MODEL = 'qwen2.5-coder:14b'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
CONTEXT_LINES = 10

# Shared variable to indicate whether the editing thread is active
g_thread_lock = threading.Lock()
g_editing_thread = None
# We bring the worker thread results into the main thread using these variables
g_result = None
g_start_line = 0
g_end_line = 0
g_new_code_lines = []
g_diff = []
g_original_content = []
g_debug_mode = False  # You can turn this on/off as needed

def debug_print(*args):
    global g_debug_mode
    if g_debug_mode:
        print(' '.join(map(str, args)))

def setup_logging(log_file='ollama.log', log_level=logging.ERROR):
    """
    Set up logging configuration.
    """
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Create a file handler which logs even debug messages
    if not os.path.exists('/tmp/logs'):
        os.makedirs('/tmp/logs')

    log_path = os.path.join('/tmp/logs', log_file)
    fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=2)
    fh.setLevel(log_level)

    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)

    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

def close_logging():
    """
    Close all logging handlers.
    """
    logger = logging.getLogger()
    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)

def log_debug(message):
    """
    Log a debug message.
    """
    logger = logging.getLogger()
    logger.debug(message)

def log_error(message):
    """
    Log a error message.
    """
    logger = logging.getLogger()
    logger.error(message)

def compute_diff(old_lines, new_lines):
    """
    Compute differences between old and new lines.

    Args:
        old_lines (list): The original code as a list of strings.
        new_lines (list): The modified code as a list of strings.

    Returns:
        list: A list of dictionaries describing the changes.
    """
    diff = list(ndiff(old_lines, new_lines))
    return diff

def apply_diff(diff, buf, line_offset=0):
    """
    Apply differences directly to a Vim buffer.

    Args:
        diff (iterable): The result of ndiff comparing old and new lines.
        buf: The Vim buffer to apply changes to.
        line_offset (int): Line offset for the current buffer.
    """
    debug_print("\n".join(diff))
    deleted_lines = []  # Collect deleted lines for multi-line display

    for line in diff:

        if line.startswith('+ '):
            debug_print(f"add line: '{line}'")
            # Added line
            lineno = line_offset
            content = line[2:].rstrip()
            VimHelper.InsertLine(lineno, content, buf)
            VimHelper.HighlightLine(lineno, 'OllamaDiffAdd', len(content), buf)
            if deleted_lines:
                # Show the collected deleted lines above the current added line
                for i, deleted_line in enumerate(deleted_lines):
                    VimHelper.ShowTextAbove(lineno, 'OllamaDiffDel', json.dumps(deleted_line), buf)
                deleted_lines = []  # Reset deleted lines
                VimHelper.PlaceSign(lineno, 'ChangedLine', buf)
            else:
                VimHelper.PlaceSign(lineno, 'NewLine', buf)

            line_offset += 1

        elif line.startswith('- '):
            debug_print("delete line")
            # Deleted line
            lineno = line_offset
            old_content = VimHelper.DeleteLine(lineno, buf)
            if old_content != line[2:]:
                raise Exception(f"error: diff does not apply at deleted line {lineno}: {line}")
            deleted_lines.append(old_content)  # Collect the deleted line content

        elif line.startswith('? '):
            debug_print("info line")
            # This line is a marker for the previous change (not handled)
            continue

        elif line.startswith('  '):
            debug_print("unchanged line")
            # Unchanged line
            if deleted_lines:
                # Show the collected deleted lines above the current unchanged line
                for i, deleted_line in enumerate(deleted_lines):
                    VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', json.dumps(deleted_line), buf)
                deleted_lines = []  # Reset deleted lines
                VimHelper.PlaceSign(lineno, 'DeletedLine', buf)

            lineno = line_offset
            old_content = VimHelper.GetLine(lineno, buf)
            debug_print(f"line {lineno}: '{old_content}'")
            debug_print(f"diffline {lineno}: '{line}'")
            content = line[2:]
            if content != old_content:
                debug_print(f"existing line: '{old_content}'")
                debug_print(f"expected line: '{content}'")
                raise Exception(f"error: diff does not apply at unmodified line {lineno}: {content}")
            line_offset += 1
        else:
            debug_print(f"other: '{line}'")
            line_offset += 1


    # Handle any remaining deleted lines at the end
    if deleted_lines:
        for i, deleted_line in enumerate(deleted_lines):
            VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', json.dumps(deleted_line), buf)

def accept_changes(buffer):
    """
    Apply accepted changes to the Vim buffer.

    Args:
        buffer (list): The original Vim buffer as a list.
        diff (list): The computed diff (ndiff output).
        start (int): The starting line number.
    """
    # Clear all signs in the buffer
    VimHelper.SignClear(buffer)

    bufno = buffer.number
    # remove properties from all lines
    vim.command(f"call prop_clear(1, line('$'))")
    debug_print("Changes accepted: All annotations and signs removed.")

def reject_changes(buffer, original_lines, start):
    """
    Revert to the original lines.

    Args:
        buffer (list): The Vim buffer as a list.
        original_lines (list): The original lines to restore.
        start (int): The starting line number.
    """
#    line_offset = start - 1  # Adjust to 0-based index
#    debug_print(f"Reverting changes starting from line {start}")
#
#    # Compute the range to replace in the buffer
#    num_lines_to_replace = len(original_lines)
#    buffer[line_offset:line_offset + num_lines_to_replace] = original_lines

    # Clear all signs in the buffer
    VimHelper.SignClear(buffer)

    # simply undo last change
    vim.command(f"undo")
    debug_print("Changes rejected. Original content restored.")

def create_prompt(request, preamble, code, postamble, ft) -> str:
    """
    Creates a prompt for the OpenAI API based on the given parameters.

    Args:
        request (str): The request to be satisfied by the translation.
        preamble (str): The preamble to be included in the code block.
        code (str): The code block to be changed.
        postamble (str): The postamble to be included in the code block.
        ft (str): The file type of the code block.

    Returns:
        str: The prompt for the OpenAI API.
    """

    prompt = f"""<|im_start|>user
```{ft}
{preamble}
<START EDITING HERE>{code}<STOP EDITING HERE>
{postamble}
```
Please rewrite the entire code block above, editing the portion below "<START EDITING HERE>" in order to satisfy the following request: '{request}'. You should rewrite the entire code block without leaving placeholders, even if the code is the same as before. When you get to "<STOP EDITING HERE>", end your response.
<|im_end|>
<|im_start|>assistant
Sure! Here's the entire code block, including the rewritten portion:
```c
{preamble}
<START EDITING HERE>
"""

#    debug_print(prompt)
    return prompt

def generate_code_completion(prompt, baseurl, model, options):
    """
    Calls the Ollama REST API with the given prompt.

    Args:
        prompt (str): The prompt for the OpenAI API.
        baseurl (str): The base URL of the Ollama server.
        model (str): The name of the model to use.
        options (dict): Additional options for the API call.

    Returns:
        str: The completion from the OpenAI API.
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': baseurl.split('//')[1].split('/')[0]
    }
    endpoint = baseurl + "/api/generate"
#    log_debug('endpoint: ' + endpoint)

    data = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'raw' : True,
        'options': options
    }
#    log_debug('request: ' + json.dumps(data, indent=4))

    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
#        log_debug('response: ' + json.dumps(json_response, indent=4))
        completion = response.json().get('response')

        # find index of sub string
        index = completion.find('<|endoftext|>')
        if index == -1:
            index = completion.find('<EOT>')
        if index != -1:
            completion = completion[:index]

        return completion.rstrip()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

def edit_code(request, preamble, code, postamble, ft, settings):
    """
    Edit code with Ollama LLM.

    Args:
        request (str): The request to be satisfied by the translation.
        preamble (str): The preamble to be included in the code block.
        code (str): The code block to be changed.
        postamble (str): The postamble to be included in the code block.
        ft (str): The file type of the code block.

    Returns:
        Array of lines containing the changed code.
    """

    if settings.get('simulate', 0):
        response = settings['response']
    else:
        prompt = create_prompt(request, preamble, code, postamble, ft)
        url = settings.get('url', DEFAULT_HOST)
        model = settings.get('model', DEFAULT_MODEL)
        options = settings.get('options', DEFAULT_OPTIONS)
        options = json.loads(options)
        response = generate_code_completion(prompt, url, model, options)

    # check if we got a valid response
    if response is None or len(response) == 0:
        return []

    # split repsonse into lines
    lines = response.split('\n')
    # search for our end marker, the LLM often produces more then we need
    num_lines=0
    last_line=None
    for line in lines:
        # find end tag in line
        pos = line.find('<STOP EDITING HERE>')
        if (pos == 0):
            break;
        elif (pos > 0):
            last_line = line[:pos]
            break;
        num_lines += 1
    # remove remainder
    lines = lines[:num_lines]
    if last_line:
        lines.append(last_line)
    return lines

def group_changes(diff, threshold=3):
    """
    Group consecutive changes into blocks.

    Args:
        diff: Parsed diff output (list of dictionaries).
        threshold: Number of unchanged lines allowed between grouped changes.

    Returns:
        List of grouped change blocks.
    """
    blocks = []
    current_block = []
    unchanged_count = 0

    for change in diff:
        if change['type'] in ['added', 'changed', 'deleted']:
            # Reset unchanged count, add to current block
            unchanged_count = 0
            current_block.append(change)
        elif change['type'] == 'unchanged':
            # Increment unchanged line count
            unchanged_count += 1
            if unchanged_count > threshold:
                # Commit current block, start a new one
                if current_block:
                    blocks.append(current_block)
                    current_block = []
                unchanged_count = 0

    # Add final block if not empty
    if current_block:
        blocks.append(current_block)

    return blocks

def vim_edit_code(request, firstline, lastline, settings):
    """
    Vim function to edit a selected range of code.

    Args:
        request (str): The request to be satisfied by the translation.
        firstline: first line to change
        lastline: last line to change
        settings: Ollama settings

    This function extracts the selected range, adds context lines, calls edit_code, and replaces the selection with the result.
    """
    global g_result
    global g_original_content
    global g_new_code_lines
    global g_diff
    new_code_lines = ''
    diff = ''
    result = ''
    try:
        buffer = vim.current.buffer
        filetype = vim.eval('&filetype')
        (start, end) = int(firstline) - 1, int(lastline) - 1

        # Add context lines
        preamble_start = max(0, start - CONTEXT_LINES)
        postamble_end = min(len(buffer), end + CONTEXT_LINES + 1)

        # Note in python vim lines are zero based
        preamble_lines  = buffer[preamble_start:start]
        code_lines      = buffer[start:end + 1]
        postamble_lines = buffer[end + 1:postamble_end]

        # Join arryas to strings
        preamble  = "\n".join(preamble_lines)
        code      = "\n".join(code_lines)
        postamble = "\n".join(postamble_lines)

        log_debug('preample: ' + preamble)
        log_debug('code: ' + code)
        log_debug('postamble: ' + postamble)

        # Edit the code
        new_code_lines = edit_code(request, preamble, code, postamble, filetype, settings)

        # Produce diff
        diff = compute_diff(code_lines, new_code_lines)

        # Finish operartion
        result = 'Done'
    except Exception as e:
        log_error(f"Error in vim_edit_code: {e}")
        # Finish operation with error
        result = 'Error'

    # write results to global vars
    with g_thread_lock:
        # backup existing code
        g_original_content = code_lines
        # save new code in global variables
        g_new_code_lines = new_code_lines
        # save diff and result
        g_diff = diff
        g_result = result

def start_vim_edit_code(request, firstline, lastline, settings):
    global g_editing_thread
    global g_result
    global g_start_line
    global g_end_line

    setup_logging(log_level=logging.DEBUG)
    log_debug(f'*** vim_edit_code: request={request}')

    g_result = 'InProgress'
    g_start_line = int(firstline)
    g_end_line = int(lastline)
    # Start the thread
    g_editing_thread = threading.Thread(target=vim_edit_code, args=(request, firstline, lastline, settings))
    g_editing_thread.start()

def get_job_status():
    """
    Check if the editing thread is still running.

    Returns:
        str: Job status: 'InProgress', 'Done', 'Error'
    """
    global g_editing_thread
    global g_result
    global g_start_line
    global g_end_line
    global g_new_code_lines
    global g_diff

    log_debug(f"result={g_result}")
    groups = None
    try:
        is_running = False
        if g_editing_thread:
            with g_thread_lock:
                is_runining = g_editing_thread.is_alive()

        if (is_running):
            return "InProgress"

        # Job Complete
        if g_result != 'Done':
            return g_result

        # Success:
        apply = 1
        if apply:
            apply_diff(g_diff, vim.current.buffer, g_start_line)
        else:
            groups = highlight_changes(g_start_line - 1, g_diff)

        result = 'Done'
    except Exception as e:
        log_error(f"Error in get_job_status: {e}")
        result = 'Error'

    close_logging()
    return result, groups

def AcceptChanges():
    accept_changes(vim.current.buffer)

def RejectChanges():
    reject_changes(vim.current.buffer, g_original_content, g_start_line)

# Main entry point
if __name__ == "__main__":
    print("The script works only inside Vim.")
else:
    # importing to Vim
    import vim
    import VimHelper
