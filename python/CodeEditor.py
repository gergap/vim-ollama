#!/usr/bin/env python3
import requests
import argparse
import json
import os
import time
import threading
from difflib import ndiff
from ChatTemplate import ChatTemplate
from OllamaLogger import OllamaLogger

# create logger
log = OllamaLogger('edit.log', log_level=10)

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
g_start_line = 0 # start line of edit
g_end_line = 0 # end line of edit
g_restored_lines = 0 # number of restored lines (undone deletes)
g_new_code_lines = []
g_diff = []
g_groups = []
g_original_content = []
g_debug_mode = False  # You can turn this on/off as needed
g_change_index = -1
g_dialog_callback = None

# Debug prints for development. This output is shown as Vim message.
def debug_print(*args):
    global g_debug_mode
    if g_debug_mode:
        print(' '.join(map(str, args)))

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

def group_diff(diff, starting_line=1):
    """
    Group consecutive changes into chunks, excluding unchanged lines.

    Args:
        diff (iterable): The result of ndiff comparing old and new lines.
        starting_line (int): Line number offset for the original code.

    Returns:
        list: A list of dictionaries, where each dictionary contains:
              - 'start_line': The starting line number of the group.
              - 'end_line': The ending line number of the group.
              - 'changes': A list of strings representing the changes in the group.
    """
    grouped_diff = []
    current_group = []
    current_start_line = None
    line_number = starting_line

    for line in diff:
        if line.startswith('- ') or line.startswith('+ '):
            # Start a new group if this is the first change in a group
            if not current_group:
                current_start_line = line_number
            current_group.append(line)
        elif line.startswith('  '):
            # Unchanged line stops the current group
            if current_group:
                grouped_diff.append({
                    'start_line': current_start_line,
                    'end_line': line_number,
                    'changes': current_group
                })
                current_group = []
        elif line.startswith('? '):
            # Context-only marker, skip it
            continue

        # Increment line number for each line processed
        if not line.startswith('? ') and not line.startswith('- '):
            line_number += 1

    # Add the remaining group if it has any lines
    if current_group:
        grouped_diff.append({
            'start_line': current_start_line,
            'end_line': line_number - 1,
            'changes': current_group
        })

    return grouped_diff

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
                    VimHelper.ShowTextAbove(lineno, 'OllamaDiffDel', deleted_line, buf)
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
                raise Exception(f"error: diff does not apply at deleted line {lineno}: {line} != {old_content}")
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
                    VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', deleted_line, buf)
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
            VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', deleted_line, buf)

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

def create_prompt(template_name, request, preamble, code, postamble, ft) -> str:
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

    chat_template = ChatTemplate(f"chat_templates/{template_name}")
    chat = [
            { "role": "system", "content": "You are a Vim code assistant plugin." },
            { "role": "user", "content":
f"""```{ft}
{preamble}
<START EDITING HERE>{code}<STOP EDITING HERE>
{postamble}
```
Please rewrite the entire code block above, editing the portion below "<START EDITING HERE>" in order to satisfy the following request: '{request}'. You should rewrite the entire code block without leaving placeholders, even if the code is the same as before. When you get to "<STOP EDITING HERE>", end your response.
"""}
    ]

    prompt = chat_template.render(messages=chat, add_generation_prompt=True)
    # Start the answer of the assistant to set it on the right path...
    prompt += f"""Sure! Here's the entire code block, including the rewritten portion:
```c
{preamble}
<START EDITING HERE>"""
    debug_print(prompt)
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
    log.debug('endpoint: ' + endpoint)

    data = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'raw' : True,
        'options': options
    }
    log.debug('request: ' + json.dumps(data, indent=4))

    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
#        log.debug('response: ' + json.dumps(json_response, indent=4))
        completion = response.json().get('response')

        log.debug(completion)
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
        prompt = create_prompt('chat_templates/chatml.jinja', request, preamble, code, postamble, ft)
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

        log.debug('preample: ' + preamble)
        log.debug('code: ' + code)
        log.debug('postamble: ' + postamble)

        # Edit the code
        new_code_lines = edit_code(request, preamble, code, postamble, filetype, settings)

        # Produce diff
        diff = compute_diff(code_lines, new_code_lines)

        # Finish operartion
        result = 'Done'
    except Exception as e:
        log.error(f"Error in vim_edit_code: {e}")
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

    log.debug(f'*** vim_edit_code: request={request}')

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
    global g_restored_lines
    global g_new_code_lines
    global g_diff
    global g_groups
    global g_change_index

    log.debug(f"result={g_result}")
    groups = None
    try:
        is_running = False
        if g_editing_thread:
            with g_thread_lock:
                is_runining = g_editing_thread.is_alive()

        if (is_running):
            return "InProgress", None

        # Job Complete
        if g_result != 'Done':
            return g_result, None

        # Success:
        apply_diff(g_diff, vim.current.buffer, g_start_line)

        g_groups = group_diff(g_diff, g_start_line)
        log.debug(g_groups)
        g_change_index = 0
        g_restored_lines = 0
        result = 'Done'
    except Exception as e:
        log.error(f"Error in get_job_status: {e}")
        result = 'Error'

    return result, g_groups

def AcceptAllChanges():
    accept_changes(vim.current.buffer)

def RejectAllChanges():
    reject_changes(vim.current.buffer, g_original_content, g_start_line)

def ShowAcceptDialog(dialog_callback, index):
    global g_groups, g_dialog_callback
    if not g_groups:
        print("No groups, ignoring ShowAcceptDialog.")
        return

    # get current group
    group = g_groups[index]
    start_line = group.get('start_line', 1)

    # move cursor to line lineno
    vim.command(f'execute "normal! {start_line}G"')
    # move cursor to col 0
    vim.command(f'execute "normal! 0"')
    vim.command(f'redraw')

    # save callback for later calls
    g_dialog_callback = dialog_callback
    count = len(g_groups)
    msg = f"Accept change {index+1} of {count}? y/n"
    # show popup
    vim.command(f'call popup_dialog("{msg}", {{ "line": {start_line}, "filter": "popup_filter_yesno", "callback": "{dialog_callback}", "padding": [2, 4, 2, 4] }})')

def DialogCallback(id, result):
    global g_change_index, g_groups
    if not g_groups or g_change_index is None:
        print("No groups or invalid index, ignoring callback.")
        return

    # Handle based on result
    if result == 1:  # 'y' pressed, meaning accept
        AcceptChange(g_change_index)
    elif result == 0:  # 'n' pressed, meaning reject
        RejectChange(g_change_index)
    else:
        print(f"Unexpected result: {result}")
    NextChange()

def NextChange():
    global g_change_index, g_groups, g_dialog_callback
    count = len(g_groups)
    if (count == 0):
        # no more changes left
        return

    # update index
    g_change_index += 1
    if (g_change_index >= len(g_groups)):
        # not more changes
        g_groups = None
        g_change_index = -1
        VimHelper.SignClear(vim.current.buffer)
        print("No more changes.")
        return

    ShowAcceptDialog(g_dialog_callback, g_change_index)

def AcceptChange(index):
    global g_change_index, g_groups
    global g_restored_lines
    if not g_groups or g_change_index is None:
        print("No groups or invalid index, ignoring AcceptChange.")
        return
    log.debug("AcceptChange")
    group = g_groups[g_change_index]
    log.debug(group)
    start_line = group.get('start_line', 1) + g_restored_lines
    end_line = group.get('end_line', 1) + g_restored_lines
    buf = vim.current.buffer

    log.debug(f"remove signs from {start_line} to {end_line}")
    # remove signs
    for line in range(start_line, end_line + 1):
        VimHelper.UnplaceSign(line, buf)

    # remove abovetext
    log.debug(f"remove abovetext from {start_line} to {end_line}")
    vim.command(f'call prop_clear({start_line}, {end_line})')

def RejectChange(index):
    global g_change_index, g_groups
    global g_restored_lines
    if not g_groups or g_change_index is None:
        print("No groups or invalid index, ignoring RejectChange.")
        return
    log.debug("RejectChange")
    group = g_groups[g_change_index]
    log.debug(group)
    start_line = group.get('start_line', 1) + g_restored_lines
    end_line = group.get('end_line', 1) + g_restored_lines
    buf = vim.current.buffer

    # remove any abovetext
    log.debug(f"remove abovetext from {start_line} to {end_line}")
    vim.command(f'call prop_clear({start_line}, {end_line})')

    # undo all changes of current group
    lineno = start_line
    for line in group.get('changes'):
        log.debug(f"remove signs from line {lineno}")
        VimHelper.UnplaceSign(lineno, buf)
        # undo change
        if (line.startswith('- ')):
            content = line[2:]
            # restore deleted line
            log.debug(f"restore line {lineno}")
            VimHelper.InsertLine(lineno, content)
            lineno += 1
            g_restored_lines += 1
        elif (line.startswith('+ ')):
            # remove added line
            log.debug(f"delete line {lineno}")
            VimHelper.DeleteLine(lineno)
    log.debug(f"restored_lines={g_restored_lines}")


# Main entry point
if __name__ == "__main__":
    print("The script works only inside Vim.")
else:
    # importing to Vim
    import vim
    import VimHelper
