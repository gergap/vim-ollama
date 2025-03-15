#!/usr/bin/env python3
# Simple test program for creating prompts using the Go template language.
import subprocess
import json
import sys
import logging

# Set up logging
log = logging.getLogger(__name__)
#logging.basicConfig(level=logging.DEBUG)

def get_model_template(modelname):
    """
    Fetches the model template from `ollama show --template <modelname>`.
    """
    try:
        result = subprocess.run(["ollama", "show", "--template", modelname], 
                                capture_output=True, text=True, check=True)
        template = result.stdout.strip()
        log.debug(f"Template from ollama:\n{template}")
        return template
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to get template for model {modelname}: {e}")
        sys.exit(1)

def process_template_go(template, prompt, suffix=""):
    """
    Calls the Go program to process the template correctly.
    """
    values = {
        "Prompt": prompt,
        "Suffix": suffix
    }

    try:
        # Call the Go program with the template as stdin and JSON data as an argument
        result = subprocess.run(
            ["./process_template", json.dumps(values)],
            input=template,
            capture_output=True,
            text=True,
            check=True
        )
        processed_prompt = result.stdout.strip()
        log.debug(f"Processed Prompt:\n{processed_prompt}")
        return processed_prompt
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to process template: {e}")
        sys.exit(1)

# Example usage
if __name__ == "__main__":
    model_name = "starcoder2:3b"  # Example model
    template = get_model_template(model_name)

    user_prompt = "print"
    user_suffix = '("Hello World");'  # The missing part to be predicted

    final_prompt = process_template_go(template, user_prompt, user_suffix)

    print(final_prompt)
