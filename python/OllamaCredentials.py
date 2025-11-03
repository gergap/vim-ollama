#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This class is used by the other Vim-Ollama python scripts
# to retrieve API credentials. These can be set as env variables
# or can be retrieved from UNIX Pass tool.
import os
import subprocess

class OllamaCredentials:

    def GetApiKey(self, url: str, credentialname: None|str) -> str:
        # Check if UNIX pass exists (/usr/bin/pass) and is executable
        #if credentialname and os.path.isfile('/usr/bin/pass') and os.access('/usr/bin/pass', os.X_OK):
        #    # Retrieve API key from pass store
        #    try:
        #        # redirect stdout, ignore stderr
        #        pass_process = subprocess.Popen(['pass', 'show', credentialname], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        #        password_bytes, _ = pass_process.communicate()
        #        password = password_bytes.decode('utf-8')  # Decode bytes to string using utf-8 encoding
        #        # only use first line
        #        password = password.split('\n')[0]
        #        return password.strip()  # Remove any leading/trailing whitespace
        #    except Exception as e:
        #        print(f"Error retrieving password from password store: {e}")
        #        return ""

        # Get API key from env variable
        if url == '': # OpenAI
            key = os.getenv('OPENAI_API_KEY', '')
            if not key:
                raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")
            return key

        # Mistral.ai
        if url.startswith('https://api.mistral.ai/'):
            key = os.getenv('MISTRAL_API_KEY', '')
            if not key:
                raise EnvironmentError("Missing MISTRAL_API_KEY environment variable.")
            return key

        # fallback to OPENAI_API_KEY
        return os.getenv('OPENAI_API_KEY', '')

