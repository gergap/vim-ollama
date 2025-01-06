#!/usr/bin/env python3
import requests
import argparse

def list_ollama_models(base_url):
    url = f"{base_url}/api/tags"

    try:
        # Make a GET request to fetch the list of models
        response = requests.get(url)

        # Check if the response status code is 200 (OK)
        if response.status_code == 200:
            data = response.json()  # Assuming the response is JSON

            # Check if the 'models' key exists in the response
            if 'models' in data:
                models = data['models']  # Extract the list of models

                # Print the names of the models
                if models:
                    for model in models:
                        print(model['name'])  # Print the model name
                else:
                    print("No models found.")
            else:
                print("'models' key not found in the response.")
                exit(1)
        else:
            print(f"Failed to retrieve models. Status code: {response.status_code}")
            exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {e}")
        exit(1)

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="List Ollama models")
    parser.add_argument('-u', '--url', type=str, default="http://localhost:11434", help="Base URL of the Ollama API")

    # Parse arguments
    args = parser.parse_args()

    # Call the function with the provided base URL
    list_ollama_models(args.url)

if __name__ == "__main__":
    main()
