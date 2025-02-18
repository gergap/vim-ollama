#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
# This script uses the generate API endpoint for oneshot code completion.
import requests
import sys
import argparse
import json
import os
import subprocess
import getpass
from abc import ABC, abstractmethod
from OllamaLogger import OllamaLogger

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
DEFAULT_BACKEND = 'ollama'

# Create logger
log = None

class LLMBackend(ABC):
    """ Abstract Base Class for LLM Backends """

    def __init__(self, baseurl, model, options):
        self.baseurl = baseurl
        self.model = model
        self.options = options

    def get_api_key(self, server):
        try:
            CREDENTIAL_NAME = f'api_keys/{server}'
            # Run the `pass show` command to retrieve the password
            pass_process = subprocess.Popen(['pass', 'show', CREDENTIAL_NAME], stdout=subprocess.PIPE)
            password_bytes, _ = pass_process.communicate()
            password = password_bytes.decode('utf-8')  # Decode bytes to string using utf-8 encoding
            return password.strip()  # Remove any leading/trailing whitespace
        except Exception as e:
            print(f"Error retrieving password from password store: {e}")
            # Fallback to password prompt
            return getpass.getpass(prompt='Enter API Key: ')

    @abstractmethod
    def generate_code_completion(self, config, prompt):
        pass

class OllamaBackend(LLMBackend):
    """ Ollama Backend Implementation """

    def generate_code_completion(self, config, prompt):
        headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Host': self.baseurl.split('//')[1].split('/')[0]
        }
        endpoint = self.baseurl + "/api/generate"
        log.debug('endpoint: ' + endpoint)

        # Generate model specific prompt
        prompt = fill_in_the_middle(config, prompt)

        data = {
            'model': self.model,
            'prompt': prompt,
            'stream': False,
            'raw': True,
            'options': self.options
        }
        log.debug('request: ' + json.dumps(data, indent=4))

        response = requests.post(endpoint, headers=headers, json=data)

        if response.status_code == 200:
            json_response = response.json()
            log.debug('response: ' + json.dumps(json_response, indent=4))
            completion = json_response.get('response')
            log.info('completion: ' + completion)

            try:
                index = completion.find(config.get('eot', '<EOT>'))
                if index != -1:
                    completion = completion[:index]  # remove EOT marker
            except:
                pass

            return completion.rstrip()
        else:
            raise Exception(f"Error: {response.status_code} - {response.text}")

class OpenWebUIBackend(LLMBackend):
    """ OpenWebUI Backend Implementation """

    def generate_code_completion(self, config, prompt):
        # get server name from URL
        server_name = self.baseurl.split('//')[1].split('/')[0]
        api_key = self.get_api_key(server_name)
        print(f"api_key={api_key}")

        # create HTTP headers
        headers = {
            'Authorization': f"Bearer {api_key}",
            'Content-Type': 'application/json',
            'Accept': '*/*'
        }
        endpoint = self.baseurl + "/api/chat/completions"
        log.debug('endpoint: ' + endpoint)

        # Generate model specific prompt
        prompt = fill_in_the_middle(config, prompt)

        data = {
            'model': self.model,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'stream': False,
            'options': self.options
        }
        log.debug('request: ' + json.dumps(data, indent=4))

        response = requests.post(endpoint, headers=headers, json=data)

        if response.status_code == 200:
            json_response = response.json()
            log.debug('response: ' + json.dumps(json_response, indent=4))
            completion = json_response.get('choices')[0].get('message', {}).get('content', '')
            log.info('completion: ' + completion)
            return completion.rstrip()
        else:
            raise Exception(f"Error: {response.status_code} - {response.text}")

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
    log.debug(newprompt)

    return newprompt

def backend_factory(backend_type, baseurl, model, options):
    if backend_type == 'ollama':
        return OllamaBackend(baseurl, model, options)
    elif backend_type == 'openwebui':
        return OpenWebUIBackend(baseurl, model, options)
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete code with LLMs.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL.")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the REST API options.")
    parser.add_argument('-b', '--backend', type=str, default=DEFAULT_BACKEND, help="Specify the backend type (ollama or openwebui).")
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

    # strip suffix (e.g ':7b-code') from modelname
    modelname = args.model.rsplit(':', 1)[0]
    config = load_config(modelname)
    prompt = sys.stdin.read()

    # Create instance of configured backend
    backend = backend_factory(args.backend, args.url, args.model, options)
    # Complete the code
    response = backend.generate_code_completion(config, prompt)
    print(response, end='')
