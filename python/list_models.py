#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import requests
import argparse
import os
import sys

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_PROVIDER = "ollama"

def list_ollama_models(base_url):
    """List models installed in a local Ollama server."""
    url = f"{base_url}/api/tags"
    try:
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

def list_openai_models():
    """List models available to the current OpenAI API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    url = "https://api.openai.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
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
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="List models from Ollama or OpenAI")
    parser.add_argument("-p", "--provider", type=str, default=DEFAULT_PROVIDER,
                        choices=["ollama", "openai"],
                        help="Provider to list models from (default: ollama)")
    parser.add_argument("-u", "--url", type=str, default=DEFAULT_OLLAMA_URL,
                        help="Base URL for Ollama (ignored for OpenAI)")
    # Parse arguments
    args = parser.parse_args()

    if args.provider == "ollama":
        list_ollama_models(args.url)
    elif args.provider == "openai":
        list_openai_models()
    else:
        print(f"Unknown provider: {args.provider}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
