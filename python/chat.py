#!/usr/bin/env python3
# This script uses the chat API endpoint which allows to create conversations
# and supports sending the history of messages as context.
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

def setup_logging(log_file='ollama.log', log_level=logging.DEBUG):
    """
    Set up logging configuration.
    """
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Create a file handler which logs even debug messages
    if not os.path.exists('logs'):
        os.makedirs('logs')

    log_path = os.path.join('logs', log_file)
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

def generate_code_completion(prompt, baseurl, model):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': baseurl.split('//')[1].split('/')[0]
    }
    endpoint = baseurl + "/api/chat"
    log_debug('endpoint: ' + endpoint)

    data = {
        'model': model,
        'messages': [
#            {
#                'role': 'system',
#                'content': 'Respond with just one sentence.'
#            },
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'stream': False,
        'options': {
            'temperature': 0,
            'top_p': 0.95
        }
    }
    log_debug('request: ' + json.dumps(data, indent=4))

    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
        log_debug('response: ' + json.dumps(json_response, indent=4))
        message = response.json().get('message')
        content = message.get('content') if message else ''
        return content.strip()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Chat with an Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    args = parser.parse_args()

    prompt = sys.stdin.read()
    response = generate_code_completion(prompt, args.url, args.model)
    print(response, end='')