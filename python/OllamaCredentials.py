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
    def GetApiKey(self, provider: str, credentialname: str | None) -> str:
        """
        Retrieve the API key for the given provider.

        Supported providers:
          - 'ollama'         → no API key needed, returns ''
          - 'openai'         → use OPENAI_API_KEY env var or pass entry
          - 'openai_legacy'  → same as 'openai', kept for compatibility
          - 'mistral'        → use MISTRAL_API_KEY env var or pass entry
          - 'anthropic'      → use ANTHROPIC_API_KEY env var or pass entry

        Priority:
          1. Environment variable override
          2. UNIX pass (if credentialname is given and pass is available)
          3. Empty string (ollama) or EnvironmentError if missing
        """

        provider = provider.lower().strip()

        # 1. Ollama doesn't require authentication
        if provider == "ollama":
            return ""

        # Determine environment variable
        if provider in ("openai", "openai_legacy"):
            env_var = "OPENAI_API_KEY"
        elif provider == "mistral":
            env_var = "MISTRAL_API_KEY"
        elif provider == "anthropic":
            env_var = "ANTHROPIC_API_KEY"
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # 2. Environment variable override
        key = os.getenv(env_var)
        if key:
            return key.strip()

        # 3. Try UNIX pass if available
        if credentialname and os.path.isfile("/usr/bin/pass") and os.access("/usr/bin/pass", os.X_OK):
            try:
                pass_process = subprocess.Popen(
                    ["pass", "show", credentialname],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                password_bytes, _ = pass_process.communicate()
                password = password_bytes.decode("utf-8").split("\n", 1)[0].strip()
                if password:
                    return password
            except Exception as e:
                print(f"Error retrieving password from password store: {e}")

        # 4. No key found
        raise EnvironmentError(f"Missing {env_var} environment variable and no credential found in pass.")
