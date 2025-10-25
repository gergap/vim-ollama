#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
# This script uses either Ollama or OpenAI API for oneshot code completion.

import requests
import sys
import argparse
import json
import os
from OllamaLogger import OllamaLogger

# try to load OpenAI package if it exists
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_PROVIDER = 'ollama'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
DEFAULT_OPENAI_MODEL = 'gpt-4.1-mini'

# When set to true, we use our own templates and don't use the Ollama built-in templates.
# Is is the only way to make this work reliable. As soon is this works also with Ollama
# REST API reliable we can get rid of our own templates.
USE_CUSTOM_TEMPLATE = True
log = None


def load_config(modelname):
    # strip suffix (e.g ':7b-code') from modelname
    modelname = modelname.rsplit(':', 1)[0]
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

    if "suffix" in config["pre"]:
        newprompt = config["pre"] + parts[1] + config["suffix"] + parts[0] + config["middle"]
    else:
        newprompt = config["pre"] + parts[0] + config["suffix"] + parts[1] + config["middle"]
    log.debug(newprompt)

    return newprompt

def generate_code_completion(config, prompt, baseurl, model, options):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': baseurl.split('//')[1].split('/')[0]
    }
    endpoint = baseurl + "/api/generate"
    log.debug('endpoint: ' + endpoint)

    if USE_CUSTOM_TEMPLATE:
        log.info('Using custom prompt in raw mode')
        # generate model specific prompt using our templates
        prompt = fill_in_the_middle(config, prompt)
        # Use Ollama Codegen API in raw mode, bypassing the Ollama template processing
        data = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'raw' : True,
            'options': options
        }
    else:
        log.info("Using Ollama's built-in templates and suffix argument.")
        # Use Ollama code completion API using built-in templates.
        # Code completion should be done between prompt and suffix argument
        parts = prompt.split('<FILL_IN_HERE>')
        log.debug(parts)

        if len(parts) != 2:
            log.error("Prompt does not contain '<FILL_IN_HERE>'.")
            sys.exit(1)

        prompt = parts[0]
        suffix = parts[1]
        data = {
            'model': model,
            'prompt': prompt,
            'suffix': suffix,
            'stream': False,
            'raw' : False,
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

def extract_stop_marker(after: str) -> str | None:
    """Return the first meaningful line of `after` to use as a stop marker."""
    for line in after.splitlines():
        s = line.strip()
        if s:  # skip empty lines
            return line.rstrip()  # preserve indentation
    return None

def generate_code_completion_openai(prompt, baseurl, model, options):
    """Generate code completion using OpenAI's official Python SDK"""
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")

    if baseurl:
        client = OpenAI(base_url=baseurl, api_key=api_key)
    else:
        client = OpenAI(api_key=api_key)

    parts = prompt.split('<FILL_IN_HERE>')
    if len(parts) != 2:
        log.error("Prompt must contain <FILL_IN_HERE> marker for OpenAI mode.")
        sys.exit(1)
    before = parts[0]
    after = parts[1]

    lang = options.get('lang', 'C')
    # OpenAI does not support Fill-in-the-middle, so we need to use prompt engineering.
    full_prompt = f"""You are a professional code completion engine.
Fill in the missing code between the markers below.

Rules:
- Do NOT repeat any code that appears in the AFTER section.
- Return only the exact code that fits between BEFORE and AFTER.
- Do NOT add explanations or comments.
- Output the missing code only.

Language: {lang}

BEFORE:
{before}

AFTER:
{after}
"""
    log.debug('full_prompt: ' + full_prompt)

    stop_marker = extract_stop_marker(after)
    stops = [stop_marker] if stop_marker else None

    temperature = options.get('temperature', 0)
    max_tokens = options.get('max_tokens', 300)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    log.debug('stops: ' + str(stops))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        stop=stops
    )
    response = response.choices[0].message.content.strip()
    log.debug('response: ' + response)

    # convert response to lines
    lines = response.splitlines()
    if lines:
        # remove 1st element from array if it starts with ```
        if lines[0].startswith("```"):
            lines.pop(0)
        # remove last element from array if it starts with ```
        if lines[-1].startswith("```"):
            lines.pop()

        response = "\n".join(lines)

    return response


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Complete code using Ollama or OpenAI LLM.")
        parser.add_argument('-p', '--provider', type=str, default=DEFAULT_PROVIDER,
                            help="LLM provider: 'ollama' (default) or 'openai'")
        parser.add_argument('-m', '--model', type=str, default=None,
                            help="Model name (Ollama or OpenAI).")
        parser.add_argument('-u', '--url', type=str, default=None,
                            help="Base endpoint URL (for Ollama only).")
        parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS,
                            help="Ollama REST API options (JSON string).")
        parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR,
                            help="Specify log level")
        parser.add_argument('-f', '--log-filename', type=str, default="complete.log",
                            help="Specify log filename")
        parser.add_argument('-d', '--log-dir', type=str, default="/tmp/logs",
                            help="Specify log file directory")
        parser.add_argument('-T', action='store_false', default=True,
                            help="Use Ollama code generation suffix (experimental)")
        args = parser.parse_args()

        log = OllamaLogger(args.log_dir, args.log_filename)
        log.setLevel(args.log_level)
        USE_CUSTOM_TEMPLATE = args.T

        # parse options JSON string
        try:
            options = json.loads(args.options)
        except json.JSONDecodeError:
            options = json.loads(DEFAULT_OPTIONS)

        prompt = sys.stdin.read()

        if args.provider == "ollama":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_MODEL
            baseurl = args.url or DEFAULT_HOST
            config = load_config(modelname) if USE_CUSTOM_TEMPLATE else None
            response = generate_code_completion(config, prompt, baseurl, modelname, options)
        elif args.provider == "openai":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_OPENAI_MODEL
            baseurl = args.url or None
            response = generate_code_completion_openai(prompt, baseurl, modelname, options)
        else:
            log.error(f"Unknown provider: {args.provider}")
            sys.exit(1)

        print(response, end='')

    except KeyboardInterrupt:
        # Allow Ctrl+C without traceback
        print("Error: Aborted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Print only the root cause message, not the full traceback
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
