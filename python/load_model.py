#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
# Loads the given model via Ollama REST API
# Options:
# -u: <url>
# -m: <model>
import sys
import argparse
import requests

# Default values
DEFAULT_HOST = 'http://localhost:11434'

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load an Ollama LLM.")
    # model argument is mandatory
    parser.add_argument('-m', '--model', type=str, help="Specify the model name to load.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    args = parser.parse_args()
    if not args.model:
        parser.error("The -m option is required.")

    # Construct the full URL for the Ollama REST API call
    url = f"{args.url}/api/chat"
    # if the message array is emoty, the model will be loaded into memory
    msg = {
        "model": args.model,
        "messages": []
    }

    # Print the URL for debugging purposes
    print(f"Loading model from {url}")
    try:
        # Send a GET request to load the model
        response = requests.post(url, json=msg)

        if response.status_code == 200:
            print("Model loaded successfully.")
        else:
            print(f"Failed to load model. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while loading the model: {e}")


