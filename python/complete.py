#!/usr/bin/env python3
# This script uses the generate API endpoint for oneshot code completion.
import requests
import sys
import argparse
import json
from OllamaLogger import OllamaLogger

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'

# create logger
log = OllamaLogger('ollama.log')

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

        # find index of sub string
        index = completion.find('<|endoftext|>')
        if index == -1:
            index = completion.find('<EOT>')
        if index != -1:
            completion = completion[:index]

        return completion.rstrip()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete code with Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the Ollama REST API options.")
    parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR, help="Specify log level")
    args = parser.parse_args()

    log.setLevel(args.log_level)

    # parse options JSON string
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    prompt = sys.stdin.read()
    response = generate_code_completion(prompt, args.url, args.model, options)
    print(response, end='')
