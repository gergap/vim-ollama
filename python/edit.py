#!/usr/bin/env python3
import requests
import argparse
import json

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_HOST = 'http://tux:11434'
DEFAULT_MODEL = 'qwen2.5-coder:14b'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'

def log_debug(message):
    return

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
    log_debug('endpoint: ' + endpoint)

    data = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'raw' : True,
        'options': options
    }
    log_debug('request: ' + json.dumps(data, indent=4))

    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
        log_debug('response: ' + json.dumps(json_response, indent=4))
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

def edit_code(request, preamble, code, postamble, ft):
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

    response = generate_code_completion(prompt, args.url, args.model, options)
    # check if we got a valid response
    if response is None or len(response) == 0:
        return []

    # split repsonse into lines
    lines = response.split('\n')
    # search for our end marker, the LLM often produces more then we need
    num_lines=0
    for line in lines:
        if (line =='<STOP EDITING HERE>'):
            break;
        num_lines += 1
    # remove remainder
    lines = lines[:num_lines]
    return lines

def test():
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
    lines = edit_code(request, preamble, code, postamble, ft)
    print("\n".join(lines))

# Main entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete code with Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the Ollama REST API options.")
    args = parser.parse_args()

    # parse options JSON string
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    test()

