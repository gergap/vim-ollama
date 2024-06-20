# python/ollama.py
import sys
import json
import requests

def get_suggestions(prompt):
    url = sys.argv[1]
    headers = {
        'Content-Type': 'application/json',
    }
    data = {
        'prompt': prompt
    }
    response = requests.post(url, headers=headers, json=data)
    suggestions = response.json().get('suggestions', [])
    if suggestions:
        print(suggestions[0])
    else:
        print('')

if __name__ == "__main__":
    prompt = sys.stdin.read()
    get_suggestions(prompt)

