#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import json
import os
import requests
import threading
from difflib import ndiff
from ChatTemplate import ChatTemplate
from OllamaLogger import OllamaLogger
from OllamaCredentials import OllamaCredentials
from dataclasses import dataclass
from dataclasses import asdict
from typing import Iterable
from typing import Optional

# create logger
log = None

# Try to import OpenAI SDK
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = 'qwen2.5-coder:14b'
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
# default options if missing
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
# default parameters if options is given, but missing these entries
DEFAULT_TEMPERATURE = 0
DEFAULT_MAX_TOKENS = 5000
CONTEXT_LINES = 10

# Shared variable to indicate whether the editing thread is active
g_thread_lock = threading.Lock()
g_editing_thread = None
# We bring the worker thread results into the main thread using these variables
g_result = None
g_errormsg = ''
g_start_line = 0 # start line of edit
g_end_line = 0 # end line of edit
g_new_code_lines = []
g_diff = []
g_groups = []
g_original_content = []
g_debug_mode = False  # You can turn this on/off as needed
g_change_index = -1
g_dialog_callback = None

def CreateLogger():
    global log
    log = OllamaLogger('/tmp/logs', 'edit.log')
    log.setLevel(0)
    VimHelper.SetLogger(log)

def SetLogLevel(level):
    if log == None:
        CreateLogger()
    log.setLevel(level)

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

@dataclass
class Group:
    start_line: int
    end_line: int
    changes: list[str]

def group_diff(diff: Iterable[str], starting_line: int = 1) -> list[Group]:
    """
    Group consecutive changes into chunks, excluding unchanged lines.

    Args:
        diff: The result of ndiff comparing old and new lines.
        starting_line: Line number offset for the original code.

    Returns:
        list[Group]: A list of Group objects, each representing a consecutive
                     set of changes.
    """
    grouped_diff: list[Group] = []
    current_group: list[str] = []
    current_start_line: int | None = None
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
                grouped_diff.append(
                    Group(
                        start_line=current_start_line,
                        end_line=line_number,
                        changes=current_group.copy(),
                    )
                )
                current_group.clear()
        elif line.startswith('? '):
            # Context-only marker, skip it
            continue

        # Increment line number for each line processed
        if not line.startswith('? ') and not line.startswith('- '):
            line_number += 1

    # Add the remaining group if it has any lines
    if current_group:
        grouped_diff.append(
            Group(
                start_line=current_start_line,
                end_line=line_number - 1,
                changes=current_group.copy(),
            )
        )

    return grouped_diff


def apply_diff_groups(groups, buf):
    global g_groups

    log.debug('apply_diff_groups')
    # Save current groups in global context
    g_groups = groups
    for index, g in enumerate(groups):
        apply_diff(index, g.changes, buf, g.start_line)

def apply_diff(changeId, diff, buf, line_offset):
    """
    Apply differences directly to a Vim buffer as inline diff.

    Args:
        diff (iterable): The result of ndiff comparing old and new lines.
        buf: The Vim buffer to apply changes to.
        line_offset (int): Line offset for the current buffer.
    """
    log.debug(f'apply_diff for changeId={changeId}')
    debug_print("\n".join(diff))
    deleted_lines = []  # Collect deleted lines for multi-line display

    for line in diff:

        if line.startswith('+ '):
            debug_print(f"add line: '{line}'")
            # Added line
            lineno = line_offset
            content = line[2:].rstrip()
            VimHelper.InsertLine(lineno, content, buf)
            VimHelper.HighlightLine(lineno, changeId, 'OllamaDiffAdd', len(content), buf)
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
            lineno = line_offset
            if deleted_lines:
                # Show the collected deleted lines above the current unchanged line
                for i, deleted_line in enumerate(deleted_lines):
                    VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', deleted_line, buf)
                deleted_lines = []  # Reset deleted lines
                VimHelper.PlaceSign(lineno, 'DeletedLine', buf)

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
    # check if lineno is below buf's max lines
    if line_offset >= len(buf):
        if deleted_lines:
            for i, deleted_line in enumerate(deleted_lines):
                VimHelper.ShowTextBelow(line_offset-1, 'OllamaDiffDel', deleted_line, buf)
    else:
        if deleted_lines:
            for i, deleted_line in enumerate(deleted_lines):
                VimHelper.ShowTextAbove(line_offset, 'OllamaDiffDel', deleted_line, buf)

def apply_change(diff, buf, line_offset=1):
    """
    Apply differences directly to a Vim buffer without inline diff.

    Args:
        diff (iterable): The result of ndiff comparing old and new lines.
        buf: The Vim buffer to apply changes to.
        line_offset (int): Line offset for the current buffer.
    """
    debug_print("\n".join(diff))

    for line in diff:

        if line.startswith('+ '):
            debug_print(f"add line: '{line}'")
            # Added line
            lineno = line_offset
            content = line[2:].rstrip()
            VimHelper.InsertLine(lineno, content, buf)

            line_offset += 1

        elif line.startswith('- '):
            debug_print("delete line")
            # Deleted line
            lineno = line_offset
            old_content = VimHelper.DeleteLine(lineno, buf)
            if old_content != line[2:]:
                raise Exception(f"error: diff does not apply at deleted line {lineno}: {line} != {old_content}")

        elif line.startswith('? '):
            debug_print("info line")
            # This line is a marker for the previous change (not handled)
            continue

        elif line.startswith('  '):
            debug_print("unchanged line")

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

def create_prompt(template_name, request, preamble, code, postamble, ft) -> str:
    """
    Creates a prompt for the LLM based on the given parameters.

    Args:
        request (str): The request to be satisfied by the translation.
        preamble (str): The preamble to be included in the code block.
        code (str): The code block to be changed.
        postamble (str): The postamble to be included in the code block.
        ft (str): The file type of the code block.

    Returns:
        str: The prompt for the code editing task.
    """

    # Get the directory where the Python script resides
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path to the config file relative to the script directory
    template_path = os.path.join(script_dir, "chat_templates", template_name)
    chat_template = ChatTemplate(template_path)
    chat = [
            { "role": "system", "content": "You are a Vim code assistant plugin." },
            { "role": "user", "content":
f"""```{ft}
{preamble}
<START_EDIT_HERE>{code}
<STOP_EDIT_HERE>
{postamble}
```
Please rewrite the code between the tags `<START_EDIT_HERE>` and `<STOP_EDIT_HERE>`, **{request}**. Ensure that no comments remain and that the code is still functional. Output only the modified raw text. Don't surrend it with markdown backticks.
"""}
    ]

    prompt = chat_template.render(messages=chat, add_generation_prompt=True)
    # Start the answer of the assistant to set it on the right path...
    prompt += f"""Sure! Here's the rewritten code block:
```c
{preamble}
<START_EDIT_HERE>"""
    debug_print(prompt)
    return prompt

def generate_code_completion(prompt, baseurl, model, options):
    """
    Calls the Ollama REST API with the given prompt.

    Args:
        prompt (str): The prompt for Ollama model.
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

    if model is None:
        model = DEFAULT_MODEL
    if options is None:
        options = json.loads(DEFAULT_OPTIONS)

    log.debug('model: ' + str(model))
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
        log.debug('response: ' + json.dumps(json_response, indent=4))
        completion = response.json().get('response')
        if completion is None:
            error = response.json().get('error', 'no response')
            raise Exception(f"Error: {error}")

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

def generate_code_completion_openai(prompt, baseurl='', model='', options=None, credentialname=None):
    """
    Calls OpenAI API with the given prompt.
    Returns the raw completion text.
    """
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Install via `pip install openai`.")

    if model is None:
        model = DEFAULT_OPENAI_MODEL

    log.debug('Using OpenAI completion endpoint')
    cred = OllamaCredentials()
    api_key = cred.GetApiKey(baseurl, credentialname)

    if baseurl:
        log.info('Using OpenAI endpoint '+baseurl)
        client = OpenAI(base_url=baseurl, api_key=api_key)
    else:
        log.info('Using official OpenAI endpoint')
        client = OpenAI(api_key=api_key)

    # Extract options
    if options is None:
        options = json.loads(DEFAULT_OPTIONS)

    temperature = options.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = options.get("max_tokens", DEFAULT_MAX_TOKENS)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    response = client.chat.completions.create(
        model=model or DEFAULT_OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # OpenAI returns a list of choices
    completion = response.choices[0].message.content
    log.debug(completion)
    # convert response to lines
    lines = completion.splitlines()
    if lines:
        # remove 1st element from array if it starts with ```
        if lines[0].startswith("```"):
            lines.pop(0)
        # remove last element from array if it starts with ```
        if lines[-1].startswith("```"):
            lines.pop()

        completion = "\n".join(lines)
    completion = completion.strip()
    log.debug(completion)

    # Strip any end markers
    for end_marker in ["<|endoftext|>", "<STOP_EDIT_HERE>", "<EOT>"]:
        idx = completion.find(end_marker)
        if idx != -1:
            completion = completion[:idx]

    return completion.rstrip()

def edit_code(request, preamble, code, postamble, ft, settings, credentialname):
    """
    Edit code with Ollama or OpenAI LLM.

    Args:
        request (str): The request to be satisfied by the translation.
        preamble (str): The preamble to be included in the code block.
        code (str): The code block to be changed.
        postamble (str): The postamble to be included in the code block.
        ft (str): The file type of the code block.

    Returns:
        Array of lines containing the changed code.
    """

    provider = settings.get("provider", DEFAULT_PROVIDER)

    if settings.get('simulate', 0):
        response = settings['response']
    else:
        # TODO: choose correct template based on selected model
        prompt = create_prompt('chatml.jinja', request, preamble, code, postamble, ft)
        url = settings.get('url', None)
        model = settings.get('model', None)
        options = settings.get('options', None)
        options = json.loads(options)
        if provider == "openai":
            response = generate_code_completion_openai(prompt, url, model, options, credentialname)
        else:
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
        pos = line.find('<STOP_EDIT_HERE>')
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

def vim_edit_code(request, firstline, lastline, settings, credentialname):
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
    global g_errormsg
    global g_original_content
    global g_new_code_lines
    global g_diff
    new_code_lines = ''
    diff = ''
    result = ''
    errormsg = ''
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

        # Join arrays to strings
        preamble  = "\n".join(preamble_lines)
        code      = "\n".join(code_lines)
        postamble = "\n".join(postamble_lines)

        log.debug('preamble: ' + preamble)
        log.debug('code: ' + code)
        log.debug('postamble: ' + postamble)

        # Edit the code
        new_code_lines = edit_code(request, preamble, code, postamble, filetype, settings, credentialname)

        # Produce diff
        diff = compute_diff(code_lines, new_code_lines)

        # Finish operation
        result = 'Done'
    except Exception as e:
        log.error(f"Error in vim_edit_code: {e}")
        # Finish operation with error
        result = 'Error'
        errormsg = str(e)

    # write results to global vars
    with g_thread_lock:
        # backup existing code
        g_original_content = code_lines
        # save new code in global variables
        g_new_code_lines = new_code_lines
        # save diff and result
        g_diff = diff
        g_result = result
        g_errormsg = errormsg

def start_vim_edit_code(request, firstline, lastline, settings, credentialname):
    global log
    global g_editing_thread
    global g_result
    global g_errormsg
    global g_start_line
    global g_end_line

    if log == None:
        CreateLogger()
    log.debug(f'*** vim_edit_code: request={request}')

    g_errormsg =''
    g_result = 'InProgress'
    g_start_line = int(firstline)
    g_end_line = int(lastline)
    # Start the thread
    g_editing_thread = threading.Thread(target=vim_edit_code, args=(request, firstline, lastline, settings, credentialname))
    g_editing_thread.start()

def get_job_status():
    """
    Check if the editing thread is still running.
    This is called from Vim main thread using a timer callback to be able to update the GUI.

    Returns:
        Tuple of job status, diff groups and error message
        Job status: 'InProgress', 'Done', 'Error'
    """
    global g_editing_thread
    global g_result
    global g_errormsg
    global g_start_line
    global g_end_line
    global g_new_code_lines
    global g_diff
    global g_change_index

    groups = None
    log.debug(f"result={g_result}")
    try:
        is_running = False
        if g_editing_thread:
            with g_thread_lock:
                is_running = g_editing_thread.is_alive()

        if (is_running):
            return "InProgress", None, ''

        # Job Complete
        if g_result != 'Done':
            # Error
            return g_result, None, g_errormsg

        # Success:
        groups = group_diff(g_diff, g_start_line)
        log.debug(groups)
        g_change_index = 0

        use_inline_diff = int(vim.eval('g:ollama_use_inline_diff'))
        if use_inline_diff:
            apply_diff_groups(groups, vim.current.buffer)
        else:
            apply_change(g_diff, vim.current.buffer, g_start_line)

        result = 'Done'
    except Exception as e:
        log.error(f"Error in get_job_status: {e}")
        g_errormsg = str(e)
        result = 'Error'

    return result, groups, g_errormsg

def AcceptAllChanges():
    global g_groups
    g_groups = None
    buf = vim.current.buffer
    VimHelper.ClearAllHighlights('OllamaDiffAdd', buf)
    VimHelper.ClearAllHighlights('OllamaDiffDel', buf)

def RejectAllChanges():
    global g_groups
    log.debug(f"RejectAllChanges")
    if not g_groups:
        log.debug("RejectAllChanges called, but g_groups is None")
        return
    groups = g_groups
    g_groups = None
    for i, g in enumerate(groups):
        RejectChange(i)

def FindGroupForLine(line: int) -> tuple[int, Optional[Group]]:
    """
    Find the group whose start_line matches the given line number.

    Args:
        line: The line number to search for.

    Returns:
        A tuple (index, Group) if found, otherwise (0, None).
    """
    global g_groups
    log.debug(f"FindGroupForLine line={line}")

    if not g_groups:
        return 0, None

    for i, g in enumerate(g_groups):
        log.debug(f"{i}: start_line={g.start_line}")
        if g.start_line == line:
            return i, g

    return 0, None

def GetGroup(index: int) -> Optional[Group]:
    global g_groups

    # check range
    if index < 0 or index >= len(g_groups):
        log.debug(f'GetGroup: index {index} out of range')
        return None

    return g_groups[index]

def AcceptChangeLine(line: int) -> None:
    log.debug(f"AcceptChangeLine at line {line}")

    index, group = FindGroupForLine(line)
    # sanity check
    if not group:
        log.error(f"AcceptChangeLine: group for line {line} not found")
        return

    AcceptChange(index)


def AcceptChange(index: int) -> None:
    log.debug(f"AcceptChange at {index}")

    group = GetGroup(index)
    # sanity check
    if not group:
        log.error(f"AcceptChange: group for index {index} not found")
        return

    # Convert dataclass to dict for logging
    log.debug("diff group: " + json.dumps(group.__dict__, indent=4))

    # compute start and end lines
    start_line = group.start_line
    end_line = group.end_line
    buf = vim.current.buffer

    log.debug(f"remove signs from {start_line} to {end_line}")
    # remove signs
    for line in range(start_line, end_line + 1):
        VimHelper.UnplaceSign(line, buf)

    # remove abovetext
    log.debug(f"remove abovetext from {start_line} to {end_line}")
    VimHelper.ClearHighlights(index, 'OllamaDiffAdd', buf)
    VimHelper.ClearHighlights(index, 'OllamaDiffDel', buf)

def RejectChangeLine(line: int) -> None:
    log.debug(f"RejectChangeLine at line {line}")

    index, group = FindGroupForLine(line)
    # sanity check
    if not group:
        log.error(f"RejectChangeLine: group for line {line} not found")
        return

    RejectChange(index)


def RejectChange(index: int) -> None:
    log.debug(f"RejectChange at {index}")
    restored_lines = 0

    group = GetGroup(index)
    # sanity check
    if not group:
        log.error(f"RejectChange: group for index {index} not found")
        return

    log.debug("diff group: " + json.dumps(asdict(group), indent=4))

    # compute start and end lines
    start_line = group.start_line
    end_line = group.end_line
    buf = vim.current.buffer

    # remove any abovetext
    log.debug(f"remove abovetext from {start_line} to {end_line}")
    VimHelper.ClearHighlights(index, 'OllamaDiffAdd', buf)
    VimHelper.ClearHighlights(index, 'OllamaDiffDel', buf)

    # undo all changes of current group
    lineno = start_line
    for line in group.changes:
        log.debug(f"remove signs from line {lineno}")
        VimHelper.UnplaceSign(lineno, buf)

        if line.startswith('- '):
            content = line[2:]
            # restore deleted line
            log.debug(f"restore line {lineno}")
            VimHelper.InsertLine(lineno, content, buf)
            lineno += 1
            restored_lines += 1

        elif line.startswith('+ '):
            content = line[2:]
            # remove added line
            log.debug(f"delete line {lineno}")
            old_content = VimHelper.DeleteLine(lineno, buf)
            if old_content != content:
                raise Exception(
                    f"error: diff does not apply to restore deleted line {lineno}: {content!r} != {old_content!r}"
                )
            restored_lines -= 1

    log.debug(f"restored_lines={restored_lines}")

    # correct lines of remaining groups: index+1 and above
    for i in range(index + 1, len(g_groups)):
        g = g_groups[i]
        g.start_line += restored_lines
        g.end_line += restored_lines

# Main entry point
if __name__ == "__main__":
    print("The script works only inside Vim.")
else:
    # importing to Vim
    import vim
    import VimHelper
