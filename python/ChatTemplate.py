#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This class can generate model specific chats for different roles
# using the tags use for training the model.
# This way we can generate model agnostic conversations.
import json
from jinja2 import Template

# apply template using Jinja2 template specified in config.chat_template
class ChatTemplate:
    def __init__(self, template_path):
        with open(template_path, 'r') as file:
            chat_template = file.read()
            chat_template = chat_template.replace('    ', '').replace('\n', '')
            self.template = Template(chat_template)

    def render(self, messages, bos_token='', eos_token=None, add_generation_prompt=False):
        return self.template.render(
            messages=messages,
            bos_token=bos_token,
            eos_token=eos_token,
            add_generation_prompt=add_generation_prompt
        )

# Example Conversation
#chat = [
#    {"role": "system", "content": "You are a Vim code assistant plugin"},
#    {"role": "user", "content": "Hello, how are you?"},
#    {"role": "assistant", "content": "I'm doing great. How can I help you today?"},
#    {"role": "user", "content": "I'd like to show off how chat templating works!"},
#]
#chat_template = ChatTemplate(f"{config['chat_template']}")
#rendered_chat = chat_template.render(messages=chat, bos_token='<s>', eos_token='</s>', add_generation_prompt=True)
#print(rendered_chat)

