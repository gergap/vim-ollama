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
        user_message = input("\nYou: ").strip()
        if user_message.lower() in ['exit', 'quit']:
            print("Exiting the chat.")
            break

        conversation_history.append({"role": "user", "content": user_message})

        await stream_chat_message(conversation_history)

        # Append assistant's message to conversation history to maintain context
        # Here we assume that the assistant's response is printed out line by line
        # Adjust as necessary depending on how the response is formatted

if __name__ == "__main__":
    asyncio.run(main())

