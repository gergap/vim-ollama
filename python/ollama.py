#!/usr/bin/env python3
# This script uses the generate API endpoint for oneshot code completion.
import requests
import sys
import argparse
import json
import logging
import os
from logging.handlers import RotatingFileHandler

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'

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

def log_debug(message):
    """
    Log a debug message.
    """
    logger = logging.getLogger()
    logger.debug(message)

def generate_code_completion(prompt, baseurl, model, options):
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

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Complete code with Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS, help="Specify the Ollama REST API options.")
    args = parser.parse_args()

    # parse options JSON string
    #eprint('options: ' + args.options)
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    prompt = sys.stdin.read()
    response = generate_code_completion(prompt, args.url, args.model, options)
    print(response, end='')
