#!/usr/bin/env python3
import requests
import argparse
import json
import logging
import os
import threading
from logging.handlers import RotatingFileHandler

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_HOST = 'http://tux:11434'
DEFAULT_MODEL = 'qwen2.5-coder:14b'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
CONTEXT_LINES = 10

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
#include <stdio.h>

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

def vim_edit_code(request, firstline, lastline, settings, callback):
    """
    Vim function to edit a selected range of code.

    Args:
        request (str): The request to be satisfied by the translation.
        firstline: first line to change
        lastline: last line to change
        settings: Ollama settings

    This function extracts the selected range, adds context lines, calls edit_code, and replaces the selection with the result.
    """
    setup_logging(log_level=logging.DEBUG)
    log_debug(f'*** vim_edit_code: request={request}')

    buffer = vim.current.buffer
    filetype = vim.eval('&filetype')
    (start, end) = int(firstline) - 1, int(lastline) - 1

    # Add context lines
    preamble_start = max(0, start - CONTEXT_LINES)
    postamble_end = min(len(buffer), end + CONTEXT_LINES + 1)

    # Note in python vim lines are zero based
    preamble = "\n".join(buffer[preamble_start:start])
    code = "\n".join(buffer[start:end + 1])
    postamble = "\n".join(buffer[end + 1:postamble_end])

    log_debug('preample: ' + preamble)
    log_debug('code: ' + code)
    log_debug('postamble: ' + postamble)

    # Edit the code
    new_code_lines = edit_code(request, preamble, code, postamble, filetype, settings)
    #new_code_lines = code.split("\n")
    log_debug('new_code: ' + "\n".join(new_code_lines))

    # Replace the selected range with the new code
    vim.current.buffer[start:end + 1] = new_code_lines
    close_logging()
    vim.command(f'call {callback}("done")')

def start_vim_edit_code(request, firstline, lastline, settings, callback):
    # Start the thread
    thread = threading.Thread(target=vim_edit_code, args=(request, firstline, lastline, settings, callback))
    thread.start()

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
