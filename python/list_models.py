#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import requests
import argparse
import os
import sys
from OllamaLogger import OllamaLogger
from OllamaCredentials import OllamaCredentials

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_PROVIDER = "ollama"
log = None

def list_ollama_models(base_url):
    """List models installed in a local Ollama server."""
    url = f"{base_url}/api/tags"
    try:
        log.debug(f'url={url}')
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to retrieve models (status {response.status_code})", file=sys.stderr)
            sys.exit(1)

        data = response.json()
        models = data.get("models", [])
        if not models:
            print("No models found.", file=sys.stderr)
            return
        for model in models:
            print(model["name"])
    except requests.exceptions.RequestException as e:
        print(f"Error contacting Ollama: {e}", file=sys.stderr)
        sys.exit(1)

def list_openai_models(base_url, credentialname):
    """List models available to the current OpenAI API key."""
    if not base_url:
        base_url = 'https://api.mistral.ai/v1'

    cred = OllamaCredentials()
    api_key = cred.GetApiKey(base_url, credentialname)

    url = f"{base_url}/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
        log.debug(f'url={url}')
        log.debug(f'headers={headers}')
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to retrieve OpenAI models (status {response.status_code})", file=sys.stderr)
            print(response.text, file=sys.stderr)
            sys.exit(1)

        data = response.json()
        models = data.get("data", [])
        if not models:
            print("No models found.", file=sys.stderr)
            return
        for m in models:
            print(m["id"])
    except requests.exceptions.RequestException as e:
        print(f"Error contacting OpenAI: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    global log
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="List models from Ollama or OpenAI")
    parser.add_argument("-p", "--provider", type=str, default=DEFAULT_PROVIDER,
                        choices=["ollama", "mistral", "openai", "openai_legacy"],
                        help="Provider to list models from (default: ollama)")
    parser.add_argument("-u", "--url", type=str, default=None,
                        help="Base URL for Ollama, Mistral or OpenAI")
    parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR,
                        help="Specify log level")
    parser.add_argument('-f', '--log-filename', type=str, default="list_models.log",
                        help="Specify log filename")
    parser.add_argument('-d', '--log-dir', type=str, default="/tmp/logs",
                        help="Specify log file directory")
    parser.add_argument('-k', '--keyname', default=None,
                        help="Credential name to lookup API key and password store")
    # Parse arguments
    args = parser.parse_args()

    log = OllamaLogger(args.log_dir, args.log_filename)
    log.setLevel(args.log_level)

    if args.provider == "ollama":
        if args.url == None:
            args.url = DEFAULT_OLLAMA_URL
        list_ollama_models(args.url)
    elif args.provider == "openai" or args.provider == "openai_legacy" or args.provider == "mistral":
        list_openai_models(args.url, args.keyname)
    else:
        print(f"Unknown provider: {args.provider}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
