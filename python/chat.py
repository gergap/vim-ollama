#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This script uses the chat API endpoint which allows to create conversations
# and supports sending the history of messages as context.
import sys
import argparse
import httpx
import json
import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'

def setup_logging(log_file='ollama.log', log_level=logging.DEBUG):
    """
    Set up logging configuration.
    """
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Create a file handler which logs even debug messages
    if not os.path.exists('logs'):
        os.makedirs('logs')

    log_path = os.path.join('logs', log_file)
    fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=2)
    fh.setLevel(log_level)

    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)

    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

def log_debug(message):
    """
    Log a debug message.
    """
    logger = logging.getLogger()
    logger.debug(message)

async def stream_chat_message(messages, endpoint, model):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': endpoint.split('//')[1].split('/')[0]
    }

    data = {
        'model': model,
        'messages': messages
    }
    log_debug('request: ' + json.dumps(data, indent=4))

    assistant_message = ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream('POST', endpoint, headers=headers, json=data) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line:
                            message = json.loads(line)
                            if 'message' in message and 'content' in message['message']:
                                content = message['message']['content']
                                assistant_message += content
                                print(content, end='', flush=True)

                                # If <EOT> is detected, stop processing
                                if '<EOT>' in content:
                                    break
                            # Stop if response contains an indication of completion
                            if message.get('done', False):
                                print('<EOT>', flush=True)
                                break
                else:
                    await response.aread()
                    raise Exception(f"Error: {response.status_code} - {response.text}")
    except httpx.ReadTimeout:
        print("Read timeout occurred. Please try again.")
        log_debug("Read timeout occurred.")
    except asyncio.CancelledError:
        log_debug("Task was cancelled.")
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        log_debug(f"An error occurred: {str(e)}")

    # Add the assistant's message to the conversation history
    if assistant_message:
        messages.append({"role": "assistant", "content": assistant_message.strip()})

async def main(baseurl, model):
    conversation_history = []
    endpoint = baseurl + "/api/chat"
    log_debug('endpoint: ' + endpoint)

    multiline_input = False
    multiline_message = []

    while True:
        try:
            user_message = input("").strip()

            if multiline_input:
                if user_message == '"""':
                    multiline_input = False
                    complete_message = "\n".join(multiline_message)
                    conversation_history.append({"role": "user", "content": complete_message})
                    multiline_message = []

                    task = asyncio.create_task(stream_chat_message(conversation_history, endpoint, model))
                    await task
                else:
                    multiline_message.append(user_message)
            else:
                if user_message == '"""':
                    multiline_input = True
                    multiline_message = []
                elif user_message.lower() in ['exit', 'quit', '/bye']:
                    print("Exiting the chat.")
                    exit(0)
                else:
                    conversation_history.append({"role": "user", "content": user_message})
                    task = asyncio.create_task(stream_chat_message(conversation_history, endpoint, model))
                    await task

        except KeyboardInterrupt:
            print("\nStreaming interrupted. Showing prompt again...")
            # Cancel the current task to clean up properly
            if 'task' in locals():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Chat with an Ollama LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL, help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST, help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    args = parser.parse_args()
    while True:
        try:
            asyncio.run(main(args.url, args.model))
        except KeyboardInterrupt:
            print("Canceled.")
    print("\nExiting the chat. (outer)")
