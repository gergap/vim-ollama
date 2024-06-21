#!/usr/bin/env python3
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
    # Hack a few test suggestions
    if (prompt == 'int main'):
        print('(int argc, char *argv[])', end='')
        return
    if (prompt.endswith('printf')):
        print('("Hello, World\\n");')
        return
    if (prompt.endswith('for')):
        print('(int i=0; i<count; i++) {\n    // TODO\n}')
        return
    return

    response = requests.post(url, headers=headers, json=data)
    suggestions = response.json().get('suggestions', [])
    if suggestions:
        print(suggestions[0])
    else:
        print('')

if __name__ == "__main__":
    prompt = sys.stdin.read()
    get_suggestions(prompt)

