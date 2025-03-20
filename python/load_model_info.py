#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
import requests
import argparse

def get_model_info(base_url, model_name, info_key):
    url = f"{base_url}/api/show"
    data = {"name": model_name}

    try:
        response = requests.post(url, json=data)

        if response.status_code == 200:
            model_info = response.json()

            if info_key in model_info:
                print(model_info[info_key])
            else:
                print(f"Key '{info_key}' not found in model info.")
        else:
            print(f"Failed to retrieve model info. Status code: {response.status_code}")
            exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")
        exit(1)

def main():
    parser = argparse.ArgumentParser(description="Retrieve Ollama model information")
    parser.add_argument('-u', '--url', type=str, default="http://localhost:11434", help="Base URL of the Ollama API")
    parser.add_argument('model', type=str, help="Model name")
    parser.add_argument('info_key', type=str, help="Key of the model information to display")

    args = parser.parse_args()
    get_model_info(args.url, args.model, args.info_key)

if __name__ == "__main__":
    main()

