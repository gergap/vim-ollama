---
name: bubblewrap-tool-diagnostics
description: Diagnose OllamaEdit bubblewrap execution failures and prepare the exact Vim allowlist configuration without repeated unsafe retries.
version: 1.0
tags: [vim-ollama, bubblewrap, sandbox, execute, networking]
author: user
---

# Bubblewrap Tool Diagnostics

Use this skill whenever a workspace `execute` call runs through bubblewrap and
fails, especially after an executable has been added to an allowlist.

## Stop Before Retrying

Do not repeatedly retry the same command after a sandboxed execution failure.
Stop the current job, inspect the complete diagnostic, and classify the
failure first. Do not work around a sandbox failure by changing the command,
using a shell, invoking another executable, or weakening the sandbox.

The execute result classifies non-zero exits when possible. Treat
`failure_kind: bubblewrap` and a message beginning with `bubblewrap failed`
as sandbox-launch failures. Treat `failure_kind: command` and a message saying
that the output is from the executable as application failures. The latter
includes normal tool/API/configuration errors such as authentication failure,
invalid arguments, a missing repository remote, or an API response. Do not
classify those as bubblewrap errors.

If the result has `failure_kind: unknown`, the command exited without useful
diagnostic output and the cause cannot be determined from the exit code alone.
Report that uncertainty instead of claiming bubblewrap was blocked.

Bubblewrap does not provide per-file or per-socket denial logs for the wrapped
program. Use the result's `sandbox_policy` to see whether networking was
enabled and which external paths were mounted read-only. A missing file or
credential path must be added explicitly to
`g:ollama_bwrap_readonly_paths`; a network-dependent command must be added to
`g:ollama_bwrap_network_allowlist`. Do not infer the exact denied path from an
exit code, and do not rerun a potentially mutating command under tracing just
to discover it.

Treat errors mentioning bubblewrap, `bwrap`, an inaccessible path, a missing
file that is known to exist outside the project, permission denied before the
program starts, missing certificates/keys/configuration, or unavailable
network access as possible sandbox configuration errors. Confirm the required
path or capability before proposing a fix.

## Required Vim Configuration

Prepare the user-facing Vim configuration using exact canonical executable
paths. Do not add wildcard paths or broad directories to the executable
allowlist. The execute confirmation's optional smart permanent approval is a
separate command-token pattern and does not replace this executable-path
requirement.

```vim
let g:ollama_execute_allowlist = ['/absolute/path/to/program']
let g:ollama_bwrap_network_allowlist = ['/absolute/path/to/program']
let g:ollama_bwrap_readonly_paths = ['/absolute/path/to/config-or-certificate']
```

Add the executable to `g:ollama_execute_allowlist` when the `execute` tool
rejects it as a system executable. Add it to
`g:ollama_bwrap_network_allowlist` only when the program genuinely needs
network access. Add each external configuration directory, certificate,
client certificate, private key, credential helper file, or other required
read-only input to `g:ollama_bwrap_readonly_paths`.

For example, a GitLab CLI installation may require:

```vim
let g:ollama_execute_allowlist = ['/usr/bin/glab']
let g:ollama_bwrap_network_allowlist = ['/usr/bin/glab']
let g:ollama_bwrap_readonly_paths = [
      \ expand('~/.config/glab-cli'),
      \ expand('~/path/to/user.crt'),
      \ expand('~/path/to/user.nopass.key'),
      \ expand('~/path/to/ca.pem'),
      \ ]
```

Never print or copy tokens, passwords, private-key contents, or full secret
configuration into the conversation. Report only the required path names and
which setting needs the path.

## Recovery Procedure

1. Stop the current task and do not issue another identical tool call.
2. Load this skill with `find_skill` if it is not already loaded.
3. Identify the exact executable path, required arguments, working directory,
   external files, and whether network access is necessary.
4. Distinguish a bubblewrap setup failure from a successfully launched tool
   that returned an ordinary non-zero exit status.
5. Tell the user exactly which entries to add to the three Vim variables.
6. Ask the user to reload Vim or restart OllamaEdit after changing the config.
7. Retry only after the user confirms that the configuration is active.

Do not edit `~/.vim/config/ollama.vim` or expose credentials automatically
unless the user explicitly requests that change and confirms the paths.
