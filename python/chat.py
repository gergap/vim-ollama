#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
#
# Unified chat client for Ollama and OpenAI APIs.
# Supports conversation context and multiline input.

import sys
import argparse
import httpx
import json
import asyncio
import os
import datetime
from OllamaLogger import OllamaLogger

# Try to import OpenAI SDK
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Default values
DEFAULT_PROVIDER = "ollama"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "codellama:code"
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT = 10

log = None


async def stream_chat_message_ollama(messages, endpoint, model, options, timeout):
    """Stream chat responses from Ollama API."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Host": endpoint.split("//")[1].split("/")[0],
    }

    data = {
        "model": model,
        "messages": messages,
        "raw": True,
        "options": options,
    }
    log.debug("request: " + json.dumps(data, indent=4))

    assistant_message = ""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=data) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line:
                            message = json.loads(line)
                            if "message" in message and "content" in message["message"]:
                                content = message["message"]["content"]
                                assistant_message += content
                                print(content, end="", flush=True)

                                # If <EOT> is detected, stop processing
                                if "<EOT>" in content:
                                    break
                            # Stop if response contains an indication of completion
                            if message.get("done", False):
                                print("<EOT>", flush=True)
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


async def stream_chat_message_openai(messages, endpoint, model, options):
    """Stream chat responses from OpenAI API."""
    if AsyncOpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")

    if endpoint:
        log.info('Using OpenAI endpoint '+endpoint)
        client = AsyncOpenAI(base_url=endpoint, api_key=api_key)
    else:
        log.info('Using official OpenAI endpoint')
        client = AsyncOpenAI(api_key=api_key)
    assistant_message = ""

    temperature = options.get('temperature', 0.2)
    max_tokens = options.get('max_tokens', 500)
    top_p = options.get('top_p', 1.0)

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                assistant_message += token
                print(token, end="", flush=True)

        print("<EOT>", flush=True)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        log.error(f"Error in OpenAI stream: {str(e)}")

    if assistant_message:
        messages.append({"role": "assistant", "content": assistant_message.strip()})


async def main(provider, endpoint, model, options, systemprompt, timeout):
    conversation_history = []
    log.debug("endpoint: " + str(endpoint))

    multiline_input = False
    multiline_message = []

    if systemprompt:
        if provider == "ollama":
            # Let Ollama know the current date
            systemprompt = f"Today's date is {datetime.date.today().isoformat()}"
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

                    if provider == "ollama":
                        task = asyncio.create_task(
                            stream_chat_message_ollama(conversation_history, endpoint, model, options, timeout)
                        )
                    else:
                        task = asyncio.create_task(
                            stream_chat_message_openai(conversation_history, endpoint, model, options)
                        )
                    await task
                else:
                    multiline_message.append(user_message)
            else:
                if user_message == '"""':
                    multiline_input = True
                    multiline_message = []
                elif user_message.lower() in ["exit", "quit", "/bye"]:
                    print("Exiting the chat.")
                    exit(0)
                else:
                    conversation_history.append({"role": "user", "content": user_message})
                    if provider == "ollama":
                        task = asyncio.create_task(
                            stream_chat_message_ollama(conversation_history, endpoint, model, options, timeout)
                        )
                    else:
                        task = asyncio.create_task(
                            stream_chat_message_openai(conversation_history, endpoint, model, options)
                        )
                    await task

        except KeyboardInterrupt:
            print("\nStreaming interrupted. Showing prompt again...")
            if "task" in locals():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat with an Ollama or OpenAI LLM.")
    parser.add_argument("-p", "--provider", type=str, default=DEFAULT_PROVIDER,
                        choices=["ollama", "openai"],
                        help="LLM provider: 'ollama' (default) or 'openai'")
    parser.add_argument("-m", "--model", type=str, default=None, help="Specify the model name to use.")
    parser.add_argument("-u", "--url", type=str, default=None,
                        help="Base endpoint URL.")
    parser.add_argument("-o", "--options", type=str, default=DEFAULT_OPTIONS,
                        help="Ollama REST API options.")
    parser.add_argument("-s", "--system-prompt", type=str, default="", help="Specify system prompt.")
    parser.add_argument("-t", "--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds.")
    parser.add_argument("-l", "--log-level", type=int, default=OllamaLogger.ERROR, help="Log level.")
    parser.add_argument("-f", "--log-filename", type=str, default="chat.log", help="Log filename.")
    parser.add_argument("-d", "--log-dir", type=str, default="/tmp/logs", help="Log file directory.")
    args = parser.parse_args()

    log = OllamaLogger(args.log_dir, args.log_filename)
    log.setLevel(args.log_level)

    # Parse options JSON
    try:
        options = json.loads(args.options)
    except json.JSONDecodeError:
        options = json.loads(DEFAULT_OPTIONS)

    # Choose model defaults
    if args.provider == "openai":
        model = args.model or DEFAULT_OPENAI_MODEL
        endpoint = args.url or None
    else:
        model = args.model or DEFAULT_MODEL
        endpoint = args.url or DEFAULT_HOST
        endpoint = endpoint + "/api/chat"

    while True:
        try:
            asyncio.run(main(args.provider, endpoint, model, options, args.system_prompt, args.timeout))
        except KeyboardInterrupt:
            print("Canceled.")
    print("\nExiting the chat. (outer)")
