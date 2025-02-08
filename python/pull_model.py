#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import requests
import argparse
import json
import sys

def create_progress_bar(completed, total, bar_length=50):
    """
    Create an ASCII progress bar.
    :param completed: Bytes completed.
    :param total: Total bytes.
    :param bar_length: Length of the progress bar.
    :return: Progress bar as a string.
    """
    if total == 0:
        return "[Error: Total size is zero]"

    progress = completed / total
    blocks = int(progress * bar_length)
    bar = "=" * blocks + " " * (bar_length - blocks)
    percent = int(progress * 100)
    completed = int(completed / (1024*1024))
    total = int(total / (1024*1024))
    # I still prefer MB, but I'm sure sombody would complain if I don't use MiB...
    return f"[{bar}] {percent}% ({completed}/{total} MiB)"

def pull_model(base_url, model_name):
    url = f"{base_url}/api/pull"

    # Data to be sent in the POST request
    data = {
        "model": model_name,
        "stream": True  # Enable streaming responses
    }

    try:
        # Send POST request with streaming enabled
        with requests.post(url, json=data, stream=True) as response:
            # Check if the response status code is 200 (OK)
            if response.status_code == 200:
                print(f"Loading {model_name} ...", flush=True)

                # Process the streaming response line by line
                for line in response.iter_lines():
                    if line:  # Ensure the line is not empty
                        try:
                            json_response = json.loads(line)

                            if json_response.get('error', None):
                                error = json_response["error"]
                                print(f"Error: {error}", flush=True)
                                exit(1)

                            status = json_response.get("status", "Unknown status")

                            # Handle progress updates
                            if "digest" in json_response:
                                digest = json_response["digest"]
                                completed = json_response.get("completed", 0)
                                total = json_response.get("total", 0)
                                progress_bar = create_progress_bar(completed, total)
                                # Print both lines: model loading status and progress bar
                                print(f"Loading {model_name} ...\\n{progress_bar}", flush=True)
                            else:
                                print(f"Loading {model_name} ...\\n{status}", flush=True)
                        except json.JSONDecodeError:
                            print(f"Failed to decode JSON: {line}")
                            exit(1)
            else:
                print(f"Failed to pull model. Status code: {response.status_code}")
                print("Error:", response.text)
                exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")
        exit(1)

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Pull an Ollama model")
    parser.add_argument('-u', '--url', type=str, default="http://localhost:11434", help="Base URL of the Ollama API")
    parser.add_argument('-m', '--model', type=str, required=True, help="Name of the model to pull")

    # Parse arguments
    args = parser.parse_args()

    # Call the function with the provided base URL and model name
    pull_model(args.url, args.model)

if __name__ == "__main__":
    main()
