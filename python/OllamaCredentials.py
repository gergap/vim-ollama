#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This class is used by the other Vim-Ollama python scripts
# to retrieve API credentials. These can be set as env variables
# or can be retrieved from UNIX Pass tool.
import os
import signal
import subprocess
from typing import Optional


PASS_EXECUTABLE = "/usr/bin/pass"
PASS_TIMEOUT = 10


def _terminate_pass_process(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (AttributeError, OSError):
            pass
    process.kill()


class OllamaCredentials:
    def GetApiKey(self, provider: str, credentialname: Optional[str]) -> str:
        """
        Retrieve the API key for the given provider.

        Supported providers:
          - 'ollama'         → no API key needed, returns ''
          - 'openai'         → use OPENAI_API_KEY env var or pass entry
          - 'openai_legacy'  → same as 'openai', kept for compatibility
          - 'mistral'        → use MISTRAL_API_KEY env var or pass entry

        Priority:
          1. Environment variable override
          2. UNIX pass (if credentialname is given and pass is available)
          3. Empty string (ollama) or EnvironmentError if missing
        """

        provider = provider.lower().strip()

        # 1. Ollama (local) doesn't require authentication
        if provider == "ollama":
            if not credentialname:
                return ""

        # Determine environment variable
        if provider in ("openai", "openai_legacy"):
            env_var = "OPENAI_API_KEY"
        elif provider == "mistral":
            env_var = "MISTRAL_API_KEY"
        elif provider == "ollama":
            env_var = "OLLAMA_API_KEY"
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # 2. Environment variable override
        key = os.getenv(env_var)
        if key:
            return key.strip()

        # 3. Try UNIX pass if available
        if credentialname:
            if (not isinstance(credentialname, str) or not credentialname
                    or credentialname.startswith("-")
                    or any(ord(character) < 32 or character.isspace() for character in credentialname)):
                raise ValueError("credential name contains invalid characters")

        if credentialname and os.path.isfile(PASS_EXECUTABLE) and os.access(PASS_EXECUTABLE, os.X_OK):
            try:
                pass_process = subprocess.Popen(
                    [PASS_EXECUTABLE, "show", "--", credentialname],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    **({"start_new_session": True} if os.name == "posix" else {}),
                )
                try:
                    password_bytes, _ = pass_process.communicate(timeout=PASS_TIMEOUT)
                except subprocess.TimeoutExpired:
                    _terminate_pass_process(pass_process)
                    pass_process.communicate()
                    raise
                if pass_process.returncode != 0:
                    raise EnvironmentError("password store lookup failed")
                password = password_bytes.decode("utf-8").split("\n", 1)[0].strip()
                if password:
                    return password
            except Exception:
                pass

        # 4. No key found
        raise EnvironmentError(f"Missing {env_var} environment variable and no credential found in pass.")
