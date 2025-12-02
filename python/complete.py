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
from OllamaCredentials import OllamaCredentials

# try to load OpenAI package if it exists
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# try to load Mistral package if it exists
try:
    from mistralai import Mistral
except ImportError:
    Mistral = None

# try to load Anthropic package if it exists
try:
    from anthropic import Anthropic  # type: ignore
except ImportError:
    Anthropic = None

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_PROVIDER = 'ollama'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
DEFAULT_TEMPERATURE = 0
DEFAULT_MAX_TOKENS = 300
DEFAULT_MISTRAL_MODEL = 'codestral-2501'
DEFAULT_OPENAI_MODEL = 'gpt-4.1-mini'
DEFAULT_OPENAI_RESPONSES_MODEL = 'gpt-5.1-codex'
DEFAULT_CLAUDE_MODEL = 'claude-sonnet-4-20250514'

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
    """ Code completion using Ollama REST API """
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

def generate_code_completion_mistral(prompt, baseurl, model, options, credentialname):
    """ Code completion using Mistral REST API """
    if Mistral is None:
        raise ImportError("Mistral package not found. Please install via 'pip install mistralai'.")

    # Mistral provider does not need baseurl, we just set it to lookup the 
    # correct API key
    if not baseurl:
        baseurl = 'https://api.mistral.ai/'

    cred = OllamaCredentials()
    api_key = cred.GetApiKey('mistral', credentialname)
    log.debug('Using Mistral API')
    client = Mistral(api_key=api_key)

    parts = prompt.split('<FILL_IN_HERE>')
    if len(parts) != 2:
        log.error("Prompt must contain <FILL_IN_HERE> marker for OpenAI mode.")
        sys.exit(1)
    prompt = parts[0]
    suffix = parts[1]

    stop_marker = extract_stop_marker(suffix)
    stops = [stop_marker] if stop_marker else []

    temperature = options.get('temperature', DEFAULT_TEMPERATURE)
    # min_tokens = options.get('min_tokens', 1)
    max_tokens = options.get('max_tokens', DEFAULT_MAX_TOKENS)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    log.debug('prompt: ' + str(prompt))
    log.debug('suffix: ' + str(suffix))
    log.debug('stops: ' + str(stops))

    try:
        response = client.fim.complete(
            model=model,
            prompt=prompt,
            suffix=suffix,
            temperature=temperature,
    #        min_tokens=min_tokens,
            max_tokens=max_tokens,
            stop=stops
        )
        response = response.choices[0].message.content
        log.debug('response: ' + response)
    except Exception as e:
        # Print only the root cause message, not the full traceback
        print(f"Error: {e}", file=sys.stderr)
        log.error(str(e))
        sys.exit(1)

    return response

def extract_stop_marker(after: str) -> str | None:
    """Return the first meaningful line of `after` to use as a stop marker."""
    for line in after.splitlines():
        s = line.strip()
        if s:  # skip empty lines
            return line.rstrip()  # preserve indentation
    return None

def generate_code_completion_openai(prompt, baseurl, model, options, sampling_enabled, credentialname):
    """Generate code completion using OpenAI's official Python SDK"""
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    cred = OllamaCredentials()
    api_key = cred.GetApiKey('openai', credentialname)

    log.debug('Using OpenAI chat completion endpoint (prompt engineering)')
    if baseurl:
        log.debug(f'baseurl={baseurl}')
        client = OpenAI(base_url=baseurl, api_key=api_key)
    else:
        log.debug(f'Using default OpenAI URL')
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
    stops = [stop_marker] if stop_marker else []

    temperature = options.get('temperature', DEFAULT_TEMPERATURE)
    max_tokens = options.get('max_tokens', DEFAULT_MAX_TOKENS)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    log.debug('stops: ' + str(stops))
    log.debug('sampling_enabled: ' + str(sampling_enabled))
    try:
        # Build request parameters
        request_params = {
            'model': model,
            'messages': [{"role": "user", "content": full_prompt}],
        }

        # Check if model supports sampling parameters
        if sampling_enabled:
            request_params['temperature'] = temperature
            request_params['max_tokens'] = max_tokens
            request_params['stop'] = stops
        else:
            request_params['max_completion_tokens'] = max_tokens

        response = client.chat.completions.create(**request_params)
        response = response.choices[0].message.content.strip()
        log.debug('response: ' + response)
    except Exception as e:
        # Print only the root cause message, not the full traceback
        print(f"Error: {e}", file=sys.stderr)
        log.error(str(e))
        sys.exit(1)

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

def generate_code_completion_claude(prompt, baseurl, model, options, credentialname):
    """Generate code completion using Anthropic Claude API"""
    if Anthropic is None:
        raise ImportError("Anthropic package not found. Please install via 'pip install anthropic'.")

    cred = OllamaCredentials()
    api_key = cred.GetApiKey('anthropic', credentialname)

    log.debug('Using Anthropic Claude API')
    if baseurl:
        log.debug(f'baseurl={baseurl}')
        client = Anthropic(api_key=api_key, base_url=baseurl)
    else:
        log.debug(f'Using default Anthropic URL')
        client = Anthropic(api_key=api_key)

    parts = prompt.split('<FILL_IN_HERE>')
    if len(parts) != 2:
        log.error("Prompt must contain <FILL_IN_HERE> marker for Claude mode.")
        sys.exit(1)
    before = parts[0]
    after = parts[1]

    lang = options.get('lang', 'C')
    # Claude doesn't support Fill-in-the-middle, use prompt engineering
    full_prompt = f"""Fill in the missing code between the markers below.

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

    temperature = options.get('temperature', DEFAULT_TEMPERATURE)
    max_tokens = options.get('max_tokens', DEFAULT_MAX_TOKENS)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    
    try:
        response = client.messages.create(
            model=model or DEFAULT_CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": full_prompt}]
        )
        
        response_text = response.content[0].text.strip()
        log.debug('response: ' + response_text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        log.error(str(e))
        sys.exit(1)

    # convert response to lines
    lines = response_text.splitlines()
    if lines:
        # remove 1st element from array if it starts with ```
        if lines[0].startswith("```"):
            lines.pop(0)
        # remove last element from array if it starts with ```
        if lines[-1].startswith("```"):
            lines.pop()

        response_text = "\n".join(lines)

    return response_text

def generate_code_completion_openai_legacy(prompt, baseurl, model, options, credentialname):
    """Generate code completion using OpenAI's official Python SDK"""
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    log.debug('Using OpenAI legacy completion endpoint (FIM support)')
    cred = OllamaCredentials()
    api_key = cred.GetApiKey('openai', credentialname)

    if baseurl:
        log.debug(f'baseurl={baseurl}')
        client = OpenAI(base_url=baseurl, api_key=api_key)
    else:
        log.debug(f'Using default OpenAI URL')
        client = OpenAI(api_key=api_key)

    config = {
        'pre': '<|fim_prefix|>',
        'middle': '<|fim_middle|>',
        'suffix': '<|fim_suffix|>',
        'eot': '<|endoftext|>'
    }
    full_prompt = fill_in_the_middle(config, prompt)
    log.debug('full_prompt: ' + full_prompt)

    temperature = options.get('temperature', DEFAULT_TEMPERATURE)
    max_tokens = options.get('max_tokens', DEFAULT_MAX_TOKENS)

    log.debug('model: ' + str(model))
    log.debug('temperature: ' + str(temperature))
    log.debug('max_tokens: ' + str(max_tokens))
    response = client.completions.create(
        model=model,
        prompt=full_prompt,
        temperature=temperature,
        max_tokens=max_tokens
    )
    response = response.choices[0].text
    log.debug('response: ' + response)

    return response.rstrip()

def generate_code_completion_openai_responses(prompt, baseurl, model, options, credentialname):
    """Generate code completion using OpenAI's /v1/responses endpoint for GPT-5.1-Codex"""
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    log.debug('Using OpenAI responses endpoint (for GPT-5.1-Codex)')
    cred = OllamaCredentials()
    api_key = cred.GetApiKey('openai', credentialname)

    if baseurl:
        endpoint = f"{baseurl}/v1/responses"
    else:
        endpoint = "https://api.openai.com/v1/responses"

    log.debug(f'endpoint: {endpoint}')

    parts = prompt.split('<FILL_IN_HERE>')
    if len(parts) != 2:
        log.error("Prompt must contain <FILL_IN_HERE> marker.")
        sys.exit(1)

    # For code completion, we just use the before part as input
    before = parts[0]
    after = parts[1]

    # Build the input prompt for code completion
    # Use similar structure as Claude prompt for better results
    lang = options.get('lang', 'C')

    full_input = f"""Fill in the missing code between the markers below.

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

    # Use higher token limit for gpt-5.1-codex which uses reasoning tokens
    max_output_tokens = options.get('max_completion_tokens', options.get('max_tokens', DEFAULT_MAX_TOKENS))

    log.debug('model: ' + str(model))
    log.debug('max_output_tokens: ' + str(max_output_tokens))
    log.debug('input: ' + full_input)

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    data = {
        'model': model,
        'input': full_input,
        'max_output_tokens': max_output_tokens
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        if response.status_code != 200:
            log.error(f'API error: {response.text}')
        response.raise_for_status()
        result = response.json()
        log.debug('response: ' + json.dumps(result, indent=2))

        # Extract the completion from the response
        # The responses endpoint can return different formats
        completion = None

        # Check if response has the new format with 'output' array
        if 'output' in result and isinstance(result['output'], list):
            log.debug(f'Result has output array with {len(result["output"])} items')
            # Look for message type items in the output array
            for idx, item in enumerate(result['output']):
                log.debug(f'Output item {idx}: type={item.get("type")}')
                if item.get('type') == 'message' and item.get('status') == 'completed':
                    content = item.get('content', [])
                    log.debug(f'Message content has {len(content)} items')
                    for content_idx, content_item in enumerate(content):
                        log.debug(f'Content {content_idx}: type={content_item.get("type")}')
                        if content_item.get('type') == 'output_text':
                            completion = content_item.get('text', '')
                            log.debug(f'Found output_text: {completion}')
                            break
                    if completion:
                        break

            # If no message found, log the incomplete status
            if not completion and result.get('status') == 'incomplete':
                log.warning(f'Response incomplete: {result.get("incomplete_details")}')
                # For incomplete responses with only reasoning, we might need to handle differently
                log.error('No message output found, only reasoning. Model may need different prompt.')

        # Handle list format (old format)
        elif isinstance(result, list):
            log.debug(f'Result is a list with {len(result)} items')
            for idx, item in enumerate(result):
                log.debug(f'Item {idx}: type={item.get("type")}, status={item.get("status")}')
                if item.get('type') == 'message' and item.get('status') == 'completed':
                    content = item.get('content', [])
                    log.debug(f'Message content has {len(content)} items')
                    for content_idx, content_item in enumerate(content):
                        log.debug(f'Content {content_idx}: type={content_item.get("type")}')
                        if content_item.get('type') == 'output_text':
                            completion = content_item.get('text', '')
                            log.debug(f'Found output_text: {completion}')
                            break
                    if completion:
                        break

        # Fallback for other formats
        elif 'text' in result:
            completion = result['text']
        elif 'choices' in result and len(result['choices']) > 0:
            completion = result['choices'][0].get('text', result['choices'][0].get('message', {}).get('content', ''))

        if not completion:
            log.error('Could not extract completion from response')
            log.error('Response structure: ' + json.dumps(result, indent=2))
            return ""

        # Ensure completion is a string
        if not isinstance(completion, str):
            log.error(f'Completion is not a string, type: {type(completion)}')
            completion = str(completion)

        log.debug('Final completion: ' + completion)
        return completion.strip()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        log.error(str(e))
        sys.exit(1)

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Complete code using Ollama or OpenAI LLM.")
        parser.add_argument('-p', '--provider', type=str, default=DEFAULT_PROVIDER,
                            help="LLM provider: 'ollama' (default), 'mistral' or 'openai'")
        parser.add_argument('-m', '--model', type=str, default=None,
                            help="Model name (Ollama or OpenAI).")
        parser.add_argument('-u', '--url', type=str, default=None,
                            help="Base endpoint URL (for Ollama only).")
        parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS,
                            help="Ollama REST API options (JSON string).")
        parser.add_argument("-se", "--sampling-enabled", type=int, default=1, help="Enable or disable sampling.")
        parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR,
                            help="Specify log level")
        parser.add_argument('-f', '--log-filename', type=str, default="complete.log",
                            help="Specify log filename")
        parser.add_argument('-d', '--log-dir', type=str, default="/tmp/logs",
                            help="Specify log file directory")
        parser.add_argument('-T', action='store_false', default=True,
                            help="Use Ollama code generation suffix (experimental)")
        parser.add_argument('-k', '--keyname', default=None,
                            help="Credential name to lookup API key and password store")
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
        elif args.provider == "mistral":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_MISTRAL_MODEL
            baseurl = args.url or None
            response = generate_code_completion_mistral(prompt, baseurl, modelname, options, args.keyname)
        elif args.provider == "openai":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_OPENAI_MODEL
            baseurl = args.url or None
            response = generate_code_completion_openai(prompt, baseurl, modelname, options, args.sampling_enabled, args.keyname)
        elif args.provider == "openai_legacy":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_OPENAI_MODEL
            baseurl = args.url or None
            response = generate_code_completion_openai_legacy(prompt, baseurl, modelname, options, args.keyname)
        elif args.provider == "claude":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_CLAUDE_MODEL
            baseurl = args.url or None
            response = generate_code_completion_claude(prompt, baseurl, modelname, options, args.keyname)
        elif args.provider == "openai_responses":
            if args.model:
                modelname = args.model
            else:
                modelname = DEFAULT_OPENAI_RESPONSES_MODEL
            baseurl = args.url or None
            response = generate_code_completion_openai_responses(prompt, baseurl, modelname, options, args.keyname)
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
        log.error(str(e))
        sys.exit(1)
