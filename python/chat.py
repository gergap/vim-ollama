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
import datetime
from OllamaLogger import OllamaLogger
from OllamaCredentials import OllamaCredentials

# Try to import OpenAI SDK
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Default values
DEFAULT_PROVIDER = "ollama"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 10
# Default models if missing
DEFAULT_MODEL = "codellama:code"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
# default options if missing
DEFAULT_OPTIONS = '{ "temperature": 0, "top_p": 0.95 }'
# default parameters if options is given, but missing these entries
DEFAULT_TEMPERATURE = 0
DEFAULT_MAX_TOKENS = 5000

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

    if assistant_message:
        messages.append({"role": "assistant", "content": assistant_message.strip()})


async def stream_chat_message_openai(messages, endpoint, model, options, credentialname):
    """Stream chat responses from OpenAI API."""
    if AsyncOpenAI is None:
        raise ImportError("OpenAI package not found. Please install via 'pip install openai'.")

    log.debug('Using OpenAI completion endpoint')
    cred = OllamaCredentials()
    api_key = cred.GetApiKey(endpoint, credentialname)
    # don't trace API keys in production, just a development helper
    #log.debug(f'api_key={api_key}')

    if endpoint:
        log.info('Using OpenAI endpoint '+endpoint)
        client = AsyncOpenAI(base_url=endpoint, api_key=api_key)
    else:
        log.info('Using official OpenAI endpoint')
        client = AsyncOpenAI(api_key=api_key)
    assistant_message = ""

    temperature = options.get('temperature', DEFAULT_TEMPERATURE)
    max_tokens = options.get('max_tokens', DEFAULT_MAX_TOKENS)
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


async def main(provider, endpoint, model, options, systemprompt, timeout, credentialname):
    conversation_history = []
    log.debug("endpoint: " + str(endpoint))

    multiline_input = False
    multiline_message = []
    image_buffer = []

    if systemprompt:
        if provider == "ollama":
            # Let Ollama know the current date
            systemprompt = f"Today's date is {datetime.date.today().isoformat()}"
        conversation_history.append({"role": "system", "content": systemprompt})

    def build_user_message_with_images(text, image_paths=None):
        message = {"role": "user", "content": text}
        if image_paths:
            images_b64 = []
            for path in image_paths:
                with open(path, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode("utf-8"))
            message["images"] = images_b64
        return message

    while True:
        try:
            user_message = input("").strip()

            # Bild hinzufügen
            if user_message.startswith(":img "):
                path = user_message[5:].strip()
                image_buffer.append(path)
                print(f"Image queued: {path}")
                continue

            if multiline_input:
                if user_message == '"""':
                    multiline_input = False
                    complete_message = "\n".join(multiline_message)
                    conversation_history.append(build_user_message_with_images(complete_message, image_buffer))
                    multiline_message = []
                    image_buffer = []

                    if provider == "ollama":
                        task = asyncio.create_task(
                            stream_chat_message_ollama(conversation_history, endpoint, model, options, timeout)
                        )
                    else:
                        task = asyncio.create_task(
                            stream_chat_message_openai(conversation_history, endpoint, model, options, credentialname)
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
                    conversation_history.append(build_user_message_with_images(user_message, image_buffer))
                    image_buffer = []
                    if provider == "ollama":
                        task = asyncio.create_task(
                            stream_chat_message_ollama(conversation_history, endpoint, model, options, timeout)
                        )
                    else:
                        task = asyncio.create_task(
                            stream_chat_message_openai(conversation_history, endpoint, model, options, credentialname)
                        )

                    await task

        except KeyboardInterrupt:
            print("\nStreaming interrupted. Showing prompt again...")
            if 'task' in locals():
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
    parser.add_argument('-k', '--keyname', default=None,
                        help="Credential name to lookup API key and password store")
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

    try:
        while True:
            try:
                asyncio.run(main(args.provider, endpoint, model, options, args.system_prompt, args.timeout, args.keyname))
            except KeyboardInterrupt:
                print("Canceled.")
                break
    except Exception as e:
        # Print only the root cause message, not the full traceback
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nExiting the chat. (outer)")
