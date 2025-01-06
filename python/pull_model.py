#!/usr/bin/env python3
import requests
import argparse
import json

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
                print(f"Pulling model: {model_name}")

                # Process the streaming response line by line
                for line in response.iter_lines():
                    if line:  # Ensure the line is not empty
                        try:
                            json_response = json.loads(line)
#                            print(json_response)

                            if json_response.get('error', None):
                                error = json_response["error"]
                                print(f"Error: {error}")
                                exit(1)

                            status = json_response.get("status", "Unknown status")

                            # Print detailed information from the stream
                            if "digest" in json_response:
                                digest = json_response["digest"]
                                completed = json_response.get("completed", 0)
                                total = json_response.get("total", 0)
                                print(f"{status}: Digest={digest}, Completed={completed}/{total} bytes")
                            else:
                                print(status)
                        except json.JSONDecodeError:
                            print(f"Failed to decode JSON: {line}")
            else:
                print(f"Failed to pull model. Status code: {response.status_code}")
                print("Error:", response.text)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")

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
