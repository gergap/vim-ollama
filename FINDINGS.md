# Code Review Findings

This review covers the Vimscript entrypoints, Python tool runner, network/provider
helpers, setup code, shell helpers, and the existing Python tests. Findings are
ordered approximately by risk. Line numbers refer to the reviewed checkout.

## Security Findings

### S1. `webfetch` permits SSRF to local and cloud metadata services

**Severity: High**  
**References:** `python/CodeEditor.py:1046-1088`, `python/CodeEditor.py:563-567`, `python/CodeEditor.py:1743-1749`

**Status: Fixed:** `webfetch` now rejects non-global DNS results, disables
ambient proxy use, and validates redirect destinations before following them.

Before the fix, the only URL validation checked for an `http://` or `https://`
prefix. Requests could therefore target loopback, RFC1918, link-local,
Unix-hosted development services, and cloud metadata endpoints.
`requests.get` also followed redirects by default, so a permitted public URL
could redirect to an internal address. The tool remains exposed in Plan and
range modes, despite those modes being described as read-only.

An untrusted repository instruction or model response can request internal
URLs such as `http://169.254.169.254/` and place the response in model context.

**Residual recommendation:** Consider removing web access from Plan mode and
using an explicit host allowlist for deployments requiring stronger network
isolation. DNS validation occurs immediately before each request, but a fully
pinned resolver/connection would be needed to eliminate DNS-rebinding races.

### S2. `vim-make` does not enforce the secure helper, and native helper builds expose the whole project as writable

**Severity: Medium, configuration-dependent**  
**References:** `autoload/ollama/edit.vim:558-598`, `scripts/mk:35-40`, `scripts/mk:85-109`

The documented configuration is a valid mitigation: `scripts/mk` does run CMake,
make, and Ninja inside bubblewrap. This finding is not claiming that the helper
itself is bypassed when it is correctly configured. The issue is that `RunMake`
starts `/bin/sh -c <makeprg plus targets>` directly and does not enforce that
`&makeprg` is the helper or apply its own sandbox. A default or ordinary
`makeprg` therefore runs Makefile recipes with the host user's privileges.

There is also a scope mismatch in the helper. For a native Makefile,
`BUILD_DIR=$SOURCE_DIR`; the helper then puts that same directory in
`WRITABLE_DIRS`. Its bubblewrap command consequently makes the entire project
writable, not only build output, despite the comment at `scripts/mk:85`.

This is especially important because the model can request `vim-make` from
workspace and range sessions and project files can be prompt-injected.

**Recommendation:** Either require/verify `scripts/mk` (or another approved
wrapper) before exposing `vim-make`, or apply the plugin's sandbox policy
directly. For native builds, use a dedicated out-of-tree build directory or
explicitly document that the whole source tree is writable. Keep target
validation strict and add an explicit confirmation for unsandboxed builds.

### S3. Workspace file mutations have no per-operation confirmation or review

**Severity: High, conditional on an untrusted or misdirected model**  
**References:** `python/CodeEditor.py:1146-1254`, `python/CodeEditor.py:1840-1855`

Once a workspace session is opened, `create_file`, `delete_file`,
`delete_folder`, `chmod`, line edits, and archive extraction are applied
immediately. There is no user confirmation, diff approval, or session-level
revocation for destructive filesystem operations. A prompt injection can thus
create a payload, mark it executable, remove files, and invoke later operations
within one approved session.

**Recommendation:** Require confirmation for destructive operations, show a
reviewable diff/summary for writes, and make the permission explicit and
revocable per session. Add a second confirmation before executing files created
or changed during the same session.

### S4. Persistent execution approvals are writable by the agent

**Severity: High**  
**References:** `autoload/ollama/edit.vim:673-696`, `autoload/ollama/edit.vim:804-822`, `python/CodeEditor.py:1146-1225`

The non-sandboxed `execute` "Allow Always" decision is stored in
`<cwd>/.ollama-execute.json`. The workspace file tools can read, create, or
replace that file. A model can therefore write an `always` entry for a payload
and then execute that payload without reaching the confirmation dialog.

**Recommendation:** Store approvals outside the workspace in a user-private
state directory. Bind approvals to the real executable path, arguments, and a
content hash; invalidate them when the file changes. Exclude approval state
from agent filesystem tools.

### S5. Project instructions are injected as trusted-looking system text

**Severity: Medium to High when combined with S1-S3**  
**References:** `python/CodeEditor.py:1426-1449`, `python/CodeEditor.py:1520-1527`

`AGENTS.md` and `CLAUDE.md` files are loaded from every ancestor up to the
filesystem root and appended as `Instructions from ...` to the system prompt.
They are not marked as untrusted data, there is no total size/count limit, and
they are included in modes where the prompt says the model is read-only.

A cloned repository can therefore supply authoritative-looking instructions
that steer web requests, file changes, or execution. The risk is amplified by
the unrestricted web tool and unsandboxed make path.

**Recommendation:** Stop discovery at the Git/workspace root, cap total files
and bytes, and clearly frame all project-provided text as untrusted content
that cannot grant permissions or override mode/tool restrictions.

### S6. Debug logs expose full prompts, source, and tool results in `/tmp`

**Severity: Medium**  
**References:** `python/CodeEditor.py:597-600`, `python/OllamaLogger.py:18-39`, `python/CodeEditor.py:1782-1824`, `python/complete.py:177-186`

The default logger writes to `/tmp/logs`. `RotatingFileHandler` uses normal
process umask, commonly creating world-readable files, and the directory is
shared. Debug paths log complete message histories, prompts, source text, tool
arguments, and responses. Completion logging also records request and response
content. Prompts can contain credentials or proprietary source.

**Recommendation:** Use a user-private state directory with mode `0700` and
files mode `0600`; only create file logging when explicitly enabled; redact
authorization material and avoid logging complete request/response bodies.

### S7. Password-store lookup is unbounded and uses a PATH-resolved executable

**Severity: Medium**  
**References:** `python/OllamaCredentials.py:51-64`

`communicate()` has no timeout. A GPG agent or pinentry can block the Vim worker
indefinitely, making cancellation ineffective. The code checks `/usr/bin/pass`
but executes the unqualified `pass` from `PATH`, so a manipulated environment
can select a different executable. Credential names are also passed without
option separation or validation.

**Recommendation:** Execute `/usr/bin/pass` (or a configured absolute path),
validate names and reject leading `-`, use `--` where supported, disable
interactive prompting, and enforce a short subprocess timeout with cleanup.

### S8. Completion HTTP requests have no timeout

**Severity: Medium**  
**References:** `python/complete.py:179`

The completion request calls `requests.post` without a timeout. A stalled Ollama
or proxy connection can block the completion worker indefinitely and make Vim
appear hung. Other provider helpers have similar inconsistent timeout handling.

**Recommendation:** Set bounded connect/read timeouts centrally and handle
`requests` timeout exceptions with a cancellable failure path.

## Logic Bugs

### L1. FIM prompt ordering is selected using an unrelated substring test

**Severity: Medium**  
**Reference:** `python/complete.py:90-105`

`fill_in_the_middle` chooses its prompt order based on whether the literal
substring `"suffix"` occurs in `config["pre"]`. That does not identify a model's
FIM ordering. All shipped configurations normally take the `else` branch, and
a future configuration can silently select the wrong ordering merely because
its prefix token contains that word.

**Recommendation:** Represent ordering explicitly in the configuration, or use
a documented per-model format, and test both orderings with synthetic configs.

### L2. Make-target validation accepts path-shaped values contrary to its contract

**Severity: Medium**  
**References:** `python/CodeEditor.py:645-661`, `autoload/ollama/edit.vim:583-588`, `tests/test_codeeditor_tools.py:821-826`

Both validators allow `.` and `/`, even though the tool says it accepts target
names rather than commands or paths. Values such as `./run` and `a/b` pass both
checks and are then appended to the configured make command. `../x` is rejected
by the parent-component check, but the broader path-shaped input remains outside
the documented contract. The tests cover shell metacharacters and options but
not path-shaped inputs.

**Recommendation:** Define the accepted target grammar once, likely without
`.` and `/`, enforce it in one shared layer, and test `./evil`, `a/b`, and
`../x` explicitly.

### L3. Setup completion clears a misspelled variable

**Severity: Low**  
**Reference:** `autoload/ollama/setup.vim:336-349`

The setup task list is stored as `s:setup_tasks`, but completion assigns
`s:setup_taks`. The current length check masks the defect, but the task list is
never actually reset and future setup re-entry or guards can observe stale
state.

**Recommendation:** Correct the spelling and reset `s:current_task` when the
task sequence finishes. Add a small Vimscript test or manual re-entry check.

## Maintainability And Quality Improvements

### M1. Security policy is duplicated across Python and Vimscript

Path, target, execution, sandbox, and mode policy is implemented independently
in `CodeEditor.py` and `autoload/ollama/edit.vim`. The accepted make grammar is
already duplicated at `CodeEditor.py:658` and `edit.vim:584`, which allows the
two layers to drift. Centralize validation or generate both interfaces from a
single policy definition, and test the Vim/Python boundary.

### M2. The tool runner is a large stateful module with global mutable session state

`python/CodeEditor.py:569-579` stores the active thread, cancellation state,
progress, make results, messages, and operations in module globals. This makes
concurrent sessions, stale callbacks, and test isolation difficult. A session
object containing state, cancellation, transport, and tool dispatch would make
lifetimes explicit and reduce cross-request leakage.

### M3. Error handling is broad and often loses structured context

The dispatcher catches every `Exception` at `CodeEditor.py:1872-1886`, while
provider/setup code also uses broad catches. This makes programmer errors look
like ordinary model tool failures and can leak raw paths, request arguments, or
remote response text into user-facing output. Introduce typed errors for
validation, cancellation, transport, and tool execution; preserve structured
error codes and redact sensitive fields.

### M4. Tests do not cover the Vimscript and external-process trust boundaries

The current suite is useful for Python filesystem/tool behavior, but it does not
exercise `RunMake`, `RunExecute`, sandbox decisions, approval-file tampering,
prompt-instruction trust framing, `pass` hangs, SSRF URL policy, or completion
timeouts. Add unit tests around pure validators and subprocess wrappers, plus
small Vim integration tests for mode/tool exposure and confirmation behavior.

### M5. Network behavior should be centralized and consistently bounded

Requests are made directly from several modules with different timeout and
logging behavior (`complete.py`, `chat.py`, `pull_model.py`, `load_model.py`,
`CodeEditor.py`, and `list_models.py`). A shared client should enforce timeouts,
redirect policy, TLS/host policy, response-size limits, and redaction uniformly.

### M6. Setup uses shell strings where argument-list APIs are available

`autoload/ollama/setup.vim:19-26` and `:378-394` construct shell command strings,
while other paths use list-form `job_start`. Current inputs are mostly
configuration-derived, but the mixed approach complicates quoting and auditing.
Use list-form process APIs consistently and validate executable/config paths.

## Positive Controls Observed

- `_safe_path` rejects absolute paths, parent components, and resolved escapes.
- Inspection and archive operations have file-count, size, and traversal limits.
- Git operations use argument lists and `--` before user/model paths.
- `execute` uses argument-list process startup, timeouts, and a separate sandbox
  path for system tools.
- The existing tests cover several symlink, archive traversal, and workspace
  boundary cases.
