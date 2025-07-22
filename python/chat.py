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
from OllamaLogger import OllamaLogger
import os

# Default values
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'codellama:code'
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
DEFAULT_TIMEOUT = 10

# create logger
log = None

async def stream_chat_message(messages, endpoint, model, options, timeout):

    # OpenAI provider: use ChatCompletion API
    if g_provider == 'openai':
        try:
            import openai
        except ImportError:
            log.error("openai package not installed. Install with `pip install openai`.")
            print("openai package not installed. Install with `pip install openai`.")
            return
        # set API key
        if g_api_key:
            openai.api_key = g_api_key
        else:
            key = os.getenv('OPENAI_API_KEY')
            if not key:
                log.error("OpenAI API key not provided. Use --api-key or set OPENAI_API_KEY.")
                print("OpenAI API key not provided. Use --api-key or set OPENAI_API_KEY.")
                return
            openai.api_key = key
        # stream chat completions
        assistant_message = ''
        try:
            # support both pre-1.0 and >=1.0 openai packages
            if hasattr(openai, 'OpenAI'):
                client = openai.OpenAI()
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=options.get('temperature', 0),
                    top_p=options.get('top_p', 1),
                    stream=True
                )
            else:
                stream = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=options.get('temperature', 0),
                    top_p=options.get('top_p', 1),
                    stream=True
                )
            for chunk in stream:
                # delta may be a dict (old SDK) or ChoiceDelta object (new SDK)
                d = chunk.choices[0].delta
                if isinstance(d, dict):
                    delta = d.get('content', '')
                else:
                    delta = getattr(d, 'content', '') or ''
                assistant_message += delta
                print(delta, end='', flush=True)
            print('<EOT>', flush=True)
        except Exception as e:
            print(f"An error occurred: {e}")
            log.error(f"An error occurred: {e}")
        # append to history
        if assistant_message:
            messages.append({'role': 'assistant', 'content': assistant_message.strip()})
        return

    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': endpoint.split('//')[1].split('/')[0]
    }

    data = {
        'model': model,
        'messages': messages,
        "raw": True,
        'options': options
    }
    log.debug('request: ' + json.dumps(data, indent=4))

    assistant_message = ""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
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
        log.error("Read timeout occurred.")
    except asyncio.CancelledError:
        log.info("Task was cancelled.")
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        log.error(f"An error occurred: {str(e)}")

    # Add the assistant's message to the conversation history
    if assistant_message:
        messages.append({"role": "assistant", "content": assistant_message.strip()})

async def main(provider, baseurl, model, options, systemprompt, timeout, api_key):
    conversation_history = []
    endpoint = baseurl + "/api/chat"
    log.debug('endpoint: ' + endpoint)

    multiline_input = False
    multiline_message = []

    if systemprompt != '':
        conversation_history.append({"role": "system", "content": systemprompt})

    while True:
        try:
            user_message = input("").strip()

            if multiline_input:
                if user_message == '"""':
                    multiline_input = False
                    complete_message = "\n".join(multiline_message)
                    conversation_history.append({"role": "user", "content": complete_message})
                    multiline_message = []

                    task = asyncio.create_task(stream_chat_message(conversation_history, endpoint, model, options, timeout))
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
                    task = asyncio.create_task(stream_chat_message(conversation_history, endpoint, model, options, timeout))
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
    parser = argparse.ArgumentParser(description="Chat with an Ollama or OpenAI LLM.")
    parser.add_argument('-m', '--model', type=str, default=DEFAULT_MODEL,
                        help="Specify the model name to use.")
    parser.add_argument('-u', '--url', type=str, default=DEFAULT_HOST,
                        help="Specify the base endpoint URL to use (default="+DEFAULT_HOST+")")
    parser.add_argument('-o', '--options', type=str, default=DEFAULT_OPTIONS,
                        help="Specify the Ollama or OpenAI REST API options.")
    parser.add_argument('-s', '--system-prompt', type=str, default='',
                        help="Specify alternative system prompt.")
    parser.add_argument('-t', '--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help="Specify the timeout")
    parser.add_argument('-p', '--provider', choices=['ollama', 'openai'], default='ollama',
                        help="API provider to use (ollama or openai)")
    parser.add_argument('-k', '--api-key', type=str, default='',
                        help="OpenAI API key (or set OPENAI_API_KEY)")
    parser.add_argument('-l', '--log-level', type=int, default=OllamaLogger.ERROR,
                        help="Specify log level")
    parser.add_argument('-f', '--log-filename', type=str, default="chat.log",
                        help="Specify log filename")
    parser.add_argument('-d', '--log-dir', type=str, default="/tmp/logs",
                        help="Specify log file directory")
    args = parser.parse_args()

    log = OllamaLogger(args.log_dir, args.log_filename)
    log.setLevel(args.log_level)
    # global provider settings for openai branch
    g_provider = args.provider
    g_api_key = args.api_key

    # parse options JSON string
    try:
        options = json.loads(args.options)
    except:
        options = DEFAULT_OPTIONS

    while True:
        try:
            asyncio.run(main(args.provider, args.url, args.model, options,
                             args.system_prompt, args.timeout, args.api_key))
        except KeyboardInterrupt:
            print("Canceled.")
    print("\nExiting the chat. (outer)")
