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
    parsed_diff = []
    line_number = 0
    last_deleted = -1

    for line in diff:
        line = line.rstrip()
        print(line)
        if line.startswith('+ '):
            if line_number == last_deleted:
                parsed_diff.append({'line_number': line_number + 1, 'line': line[2:], 'type': 'changed'})
            else:
                parsed_diff.append({'line_number': line_number + 1, 'line': line[2:], 'type': 'added'})
            line_number += 1
        elif line.startswith('- '):
#            parsed_diff.append({'line_number': line_number + 1, 'line': line[2:], 'type': 'deleted'})
            last_deleted = line_number
        elif line.startswith('  '):
            line_number += 1
            parsed_diff.append({'line_number': line_number, 'line': line[2:], 'type': 'unchanged'})

    return parsed_diff

def apply_changes(buffer, diff, start):
    """
    Apply accepted changes to the Vim buffer.

    Args:
        buffer (list): The original Vim buffer as a list.
        diff (list): The computed diff.
        start (int): The starting line number.
    """
    new_lines = [change['line'] for change in diff if change['type'] != 'deleted']
    buffer[start:start + len(new_lines)] = new_lines

def reject_changes(buffer, original_lines, start):
    """
    Revert to the original lines.

    Args:
        buffer (list): The Vim buffer as a list.
        original_lines (list): The original lines to restore.
        start (int): The starting line number.
    """
    buffer[start:start + len(original_lines)] = original_lines

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

#    print(prompt)
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

def highlight_changes(start, diff):
    """
    Highlight added, modified, and deleted lines in Vim using the generated diff.

    Args:
        start: Starting line number of the range in the buffer.
        diff: List of tuples representing the diff.
              Each tuple is in the form (status, line_number, line_content)
              - status: 'added', 'changed', 'deleted'
    """
    # Clear existing signs and matches
    vim.command(f'sign unplace * buffer={vim.current.buffer.number}')
    vim.command('call clearmatches()')

    # Highlight groups
    highlight_groups = {
        'added': 'DiffAdd',
        'changed': 'DiffChange',
        'deleted': 'DiffDelete'
    }

    # Line number lists for matchaddpos
    added_lines = []
    changed_lines = []
    deleted_lines = []

    sign_counter = 1  # Counter for unique sign IDs

    # Parse the diff and classify lines
    for change in diff:
        line_number = start + change['line_number'] + 1  # Convert diff-relative line to Vim buffer line
        status = change['type']
        log_debug(f'{status} {line_number}')

        if status == 'added':
            added_lines.append(line_number)
            vim.command(f'sign place {sign_counter} line={line_number} name=NewLine buffer={vim.current.buffer.number}')
        elif status == 'changed':
            changed_lines.append(line_number)
            vim.command(f'sign place {sign_counter} line={line_number} name=ChangedLine buffer={vim.current.buffer.number}')
        elif status == 'deleted':
            deleted_lines.append(line_number)
            vim.command(f'sign place {sign_counter} line={line_number} name=DeletedLine buffer={vim.current.buffer.number}')
        sign_counter += 1

    # Add full-line highlights using matchaddpos
    if added_lines:
        vim.command(f'call matchaddpos("{highlight_groups["added"]}", {added_lines})')
    if changed_lines:
        vim.command(f'call matchaddpos("{highlight_groups["changed"]}", {changed_lines})')
    if deleted_lines:
        vim.command(f'call matchaddpos("{highlight_groups["deleted"]}", {deleted_lines})')

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
    global g_new_code_lines
    global g_diff
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
        g_new_code_lines = new_code_lines
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
        # create a list of deleted/added/unchanged lines
        lines = []
        for change in diff:
            status = change['type']
            lines.append(change['line'])
        # Replace the selected range with the new code
        vim.current.buffer[g_start_line:g_end_line + 1] = lines
#        vim.current.buffer[g_start_line:g_end_line + 1] = g_new_code_lines
        highlight_changes(g_start_line, g_diff)
        result = 'Done'
    except Exception as e:
        log_error(f"Error in get_job_status: {e}")
        result = 'Error'

    close_logging()
    return result

def test(settings):
    # some test parameters
    ft='cpp'
    preamble="""#include <stdio.h>

"""
    code="""// Das ist die Hauptfunktion
int main()
"""
    postamble="""{
    printf("Hello World\n");
    return 0;
}
"""
    #request="translate all comments to english"
    request="add missing arguments"
    lines = edit_code(request, preamble, code, postamble, ft, settings)
    print("\n".join(lines))

# Main entry point
if __name__ == "__main__":
    # create dummy Vim object if not running inside Vim
    global vim
    vim = {}
    setup_logging(log_level=logging.DEBUG)
    log_debug('main')
    parser = argparse.ArgumentParser(description="Complete code with Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the Ollama REST API options.")
    args = parser.parse_args()

    settings = {
        'url': args.url,
        'model': args.model,
        'options': args.options
    }
    # testing code in standalone mode
    test(settings)
else:
    # importing to Vim
    import vim
