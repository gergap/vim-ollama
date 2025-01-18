#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import requests
import argparse

# We can load a model using an empy prompt
def load_ollama_model(base_url, model_name, keep_alive):
    url = f"{base_url}/api/generate"

    # Data to be sent in the POST request
    data = {
        "model": model_name,
        "keep_alive": keep_alive
    }
    try:
        # Make a POST request to load the model
        response = requests.post(url, json = data)

        # Check if the response status code is 200 (OK)
        if response.status_code == 200:
            data = response.json()  # Assuming the response is JSON

            print("Loaded model successfully.")
        else:
            print(f"Failed to load model. Status code: {response.status_code}")
            exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")
        exit(1)

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Load Ollama model")
    parser.add_argument('-u', '--url', type=str, default="http://localhost:11434", help="Base URL of the Ollama API")
    parser.add_argument('-m', '--model', type=str, required=True, help="Model name")
    parser.add_argument('-k', '--keep-alive', type=int, default=300, help="Keep alive interval in seconds (0 unloads the model)")

    # Parse arguments
    args = parser.parse_args()

    # Call the function with the provided base URL
    load_ollama_model(args.url, args.model, args.keep_alive)

if __name__ == "__main__":
    main()
