#!/usr/bin/env python3
import sys
import httpx
import json
import asyncio

# Replace with your actual endpoint
ENDPOINT = 'http://tux:11434/api/chat'
MODEL = 'starcoder2:15b'

async def stream_chat_message(messages):
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': 'tux:11434'
    }

    data = {
        'model': MODEL,
        'messages': messages
    }

    async with httpx.AsyncClient() as client:
        async with client.stream('POST', ENDPOINT, headers=headers, json=data) as response:
            if response.status_code == 200:
                async for line in response.aiter_lines():
                    if line:
                        message = json.loads(line)
                        if 'message' in message and 'content' in message['message']:
                            print(message['message']['content'], end='', flush=True)
                        # Stop if response contains an indication of completion
                        if message.get('done', False):
                            return
            else:
                raise Exception(f"Error: {response.status_code} - {response.text}")

async def main():
    conversation_history = []

    while True:
        try:
            user_message = input("You: ").strip()
            if user_message.lower() in ['exit', 'quit']:
                print("Exiting the chat.")
                exit(0)

            conversation_history.append({"role": "user", "content": user_message})

            task = asyncio.create_task(stream_chat_message(conversation_history))
            await task

        except KeyboardInterrupt:
            print("\nStreaming interrupted. Showing prompt again...")
            # Cancel the current task to clean up properly
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("Canceled.")
    print("\nExiting the chat. (outer)")
