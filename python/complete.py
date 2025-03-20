#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
# This script uses the generate API endpoint for oneshot code completion.
import requests
import sys
import argparse
import json
import os
from OllamaLogger import OllamaLogger

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'

# create logger
log = None

def load_template_remote(base_url, model_name):
    """
    Load model template via REST API.
    """
    url = f"{base_url}/api/show"
    data = {"name": model_name}

    try:
        response = requests.post(url, json=data)

        if response.status_code == 200:
            model_info = response.json()

            if info_key in model_info:
                return model_info['template']
            else:
                print("Key 'template' not found in model info.")
                exit(1)
        else:
            print(f"Failed to retrieve model info. Status code: {response.status_code}")
            exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")
        exit(1)

def load_template(base_url, model_name):
    """
    Load model template from file, but fallback to remote loading
    and caching it locally.
    """
    # get the directory where the python script resides
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # construct the full path to the config file relative to the script directory
    templ_path = os.path.join(script_dir, "configs", f"{modelname}.templ")
    try:
        with open(templ_path, 'r') as file:
            template = json.load(file)
            return template
    except filenotfounderror:
        template = load_template_remote(base_url, model_name)
        # save template
        with open(templ_path, 'w') as file:
            file.write(template)

        return template

def load_config(modelname):
    # Get the directory where the Python script resides
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path to the config file relative to the script directory
    config_path = os.path.join(script_dir, "configs", f"{modelname}.json")
    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
            return config
    except FileNotFoundError:
        log.info(f"Config file {config_path} not found.")
        return None

# config.json example:
# {
#     "pre": "<PRE> ",
#     "middle": " <MIDDLE>",
#     "suffix": " <SUFFIX>",
#     "eot": " <EOT>"
# }
def fill_in_the_middle(config, prompt):
    """
    Searches for the string '<FILL_IN_HERE>' in the prompt and
    creates a model specific fill-in-the-middle-prompt.
    """
    parts = prompt.split('<FILL_IN_HERE>')
    log.debug(parts)

    if len(parts) != 2:
        log.error("Prompt does not contain '<FILL_IN_HERE>'.")
        sys.exit(1)

    newprompt = config["pre"] + parts[0] + config["suffix"] + parts[1] + config["middle"]
    log.debug('fill_in_the_middle: ' + newprompt)

    return newprompt

def process_go_template(template, prompt):
    """
    searches for the string '<FILL_IN_HERE>' in the prompt and
    creates a model specific fill-in-the-middle-prompt using
    the included Go template.
    """
    parts = prompt.split('<FILL_IN_HERE>')
    log.debug(parts)

    if len(parts) != 2:
        log.error("Prompt does not contain '<FILL_IN_HERE>'.")
        sys.exit(1)

    values = {
        "Prompt": parts[0],
        "Suffix": parts[1]
    }

    try:
        # Call the Go program with the template as stdin and JSON data as an argument
        result = subprocess.run(
            ["./process_template", json.dumps(values)],
            input=template,
            capture_output=True,
            text=True,
            check=True
        )
        newprompt = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to process template: {e}")
        sys.exit(1)

    log.debug('process_go_template: ' + newprompt)

    return newprompt

def generate_code_completion(prompt, baseurl, model, options):
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
        log.debug('response: ' + json.dumps(json_response, indent=4))
        completion = response.json().get('response')
        log.info('completion:' + completion)

        # find index of sub string
        try:
            index = completion.find(config.get('eot', '<EOT>'))
            if index != -1:
                completion = completion[:index] # remove EOT marker
        except:
            pass

        return completion.rstrip()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete code with Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the Ollama REST API options.")
    parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR, help="Specify log level")
    parser.add_argument('-f', '--log-filename', type=str, default="complete.log", help="Specify log filename")
    parser.add_argument('-d', '--log-dir', type=str, default="/tmp/logs", help="Specify log file directory")
    args = parser.parse_args()

    log = OllamaLogger(args.log_dir, args.log_filename)
    log.setLevel(args.log_level)

    # parse options JSON string
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    prompt = sys.stdin.read()

    # strip suffix (e.g ':7b-code') from modelname
    modelname = args.model
    modelname = modelname.rsplit(':', 1)[0]
    config = load_config(modelname)

    if config:
        # generate model specific prompt
        prompt = fill_in_the_middle(config, prompt)
    else:
        # Use Go template for generating prompt
        template = load_template(args.url, args.model)
        prompt = process_go_template(template, prompt)

    response = generate_code_completion(prompt, args.url, args.model, options)
    print(response, end='')
