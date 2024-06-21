#!/usr/bin/env python3
import requests
import sys

# Replace with your actual API key and endpoint
ENDPOINT = 'http://tux:11434/api/generate'
MODEL = 'codellama:code'

def generate_code_completion(prompt):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': 'tux:11434'
    }

    data = {
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': 0,
            'top_p': 0.95
        },
        'num_predict': 10
    }

    response = requests.post(ENDPOINT, headers=headers, json=data)

    if response.status_code == 200:
        completion = response.json().get('response')
        return completion.strip()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    prompt = sys.stdin.read()
    response = generate_code_completion(prompt)
    print(response, end='')
