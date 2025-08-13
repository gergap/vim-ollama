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
# When set to true, we use our own templates and don't use the Ollama built-in templates.
# Is is the only way to make this work reliable. As soon is this works also with Ollama
# REST API reliable we can get rid of our own templates.
USE_CUSTOM_TEMPLATE = True

# create logger
log = None

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
        log.error(f"Config file {config_path} not found.")
        sys.exit(1)

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

    if "suffix" in config["pre"].lower():
        # these models require suffix first
        newprompt = config["pre"] + parts[1] + config["suffix"] + parts[0] + config["middle"]
    else:
        newprompt = config["pre"] + parts[0] + config["suffix"] + parts[1] + config["middle"]
    log.debug(newprompt)

    return newprompt, parts[1]

def generate_code_completion(config, prompt, baseurl, model, options):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': baseurl.split('//')[1].split('/')[0]
    }
    endpoint = baseurl + "/api/generate"
    log.debug('endpoint: ' + endpoint)

    # Parse options if it's a string
    if isinstance(options, str):
        options = json.loads(options)

    # Ensure stop tokens are set correctly
    stop_tokens = config.get('stop', [config.get('eot', '')]).copy()

    if USE_CUSTOM_TEMPLATE:
        log.info('Using custom prompt in raw mode')
        prompt, actual_suffix = fill_in_the_middle(config, prompt)
        # Add actual suffix to stop tokens, avoiding duplicates
        stop = actual_suffix.split("\n")[0]
        log.debug(f'stop={stop}')
        if stop and stop not in stop_tokens:
            # add suffix until up to the first newline as stop token
            stop_tokens.append(stop)
        options['stop'] = stop_tokens
        data = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'raw': True,
            'options': options
        }
    else:
        log.info("Using Ollama's built-in templates and suffix argument")
        parts = prompt.split('<FILL_IN_HERE>')
        log.debug(parts)

        if len(parts) != 2:
            log.error("Prompt does not contain '<FILL_IN_HERE>'.")
            sys.exit(1)

        prompt = parts[0]
        actual_suffix = parts[1]
        stop = actual_suffix.split("\n")[0]
        log.debug(f'stop={stop}')
        if stop and stop not in stop_tokens:
            # add suffix until up to the first newline as stop token
            stop_tokens.append(stop)
        options['stop'] = stop_tokens
        data = {
            'model': model,
            'prompt': prompt,
            'suffix': actual_suffix,
            'stream': False,
            'raw': False,
            'options': options
        }
    log.debug('request: ' + json.dumps(data, indent=4))

    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
        log.debug('response: ' + json.dumps(json_response, indent=4))
        completion = json_response.get('response')
        log.info('completion: ' + completion)

        # Remove EOT marker if present
        eot = config.get('eot', '')
        if eot and completion.endswith(eot):
            completion = completion[:-len(eot)]

        # Trim any regenerated actual suffix from the output
        if actual_suffix:
            if completion.startswith(actual_suffix):
                log.debug('startswith actual suffix')
                completion = completion[len(actual_suffix):]
            elif actual_suffix in completion:
                log.debug('split actual suffix')
                completion = completion.split(actual_suffix)[0]

        log.debug(f'completion={completion}')
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
    parser.add_argument('-T', action='store_false', default=True, help="Use Ollama code generation suffix (experimental)")
    args = parser.parse_args()

    log = OllamaLogger(args.log_dir, args.log_filename)
    log.setLevel(args.log_level)
    USE_CUSTOM_TEMPLATE = args.T

    # parse options JSON string
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    # strip suffix (e.g ':7b-code') from modelname
    modelname = args.model
    modelname = modelname.rsplit(':', 1)[0]
    if USE_CUSTOM_TEMPLATE:
        config = load_config(modelname)
    else:
        config = None

    prompt = sys.stdin.read()
    response = generate_code_completion(config, prompt, args.url, args.model, options)
    print(response, end='')
