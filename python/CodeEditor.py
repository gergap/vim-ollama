#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
"""Tool-driven code editing for vim-ollama.

The worker operates exclusively on a Python snapshot.  Vim is touched only by
the polling callback in the main thread after all requested operations have
been validated.
"""

import json
import ntpath
import os
import shutil
import threading

import requests

from OllamaCredentials import OllamaCredentials
from OllamaLogger import OllamaLogger

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


DEFAULT_PROVIDER = "ollama"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:14b"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPTIONS = {"temperature": 0, "top_p": 0.95, "num_predict": 4096}
MAX_TOOL_CALLS = 64

BUFFER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "insert_lines",
            "description": "Insert one or more lines before a 1-based line number. Use line number length+1 to append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer", "minimum": 1},
                    "content": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["line", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_lines",
            "description": "Delete an exact inclusive range of lines. The expected text must match exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "expected": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_line", "end_line", "expected"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_lines",
            "description": "Replace an exact inclusive range of lines with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "expected": {"type": "array", "items": {"type": "string"}},
                    "replacement": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_line", "end_line", "expected", "replacement"],
                "additionalProperties": False,
            },
        },
    },
]

FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new UTF-8 text file below the current directory. The relative path must not already exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path below the current directory."},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Create a new folder below the current directory. The relative path must not already exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path below the current directory."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete an existing file below the current directory. Never use this for folders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path below the current directory."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_folder",
            "description": "Delete an existing folder below the current directory. Set recursive only when all contents should be removed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path below the current directory."},
                    "recursive": {"type": "boolean"},
                },
                "required": ["path", "recursive"],
                "additionalProperties": False,
            },
        },
    },
]

TOOLS = BUFFER_TOOLS + FILE_TOOLS
FILE_TOOL_NAMES = {tool["function"]["name"] for tool in FILE_TOOLS}

log = None
g_thread_lock = threading.Lock()
g_editing_thread = None
g_result = None
g_operations = []
g_errormsg = ""
g_progress_events = []


def CreateLogger():
    global log
    log = OllamaLogger("/tmp/logs", "edit.log")
    log.setLevel(0)


def SetLogLevel(level):
    if log is None:
        CreateLogger()
    log.setLevel(level)


def _progress(text, **details):
    with g_thread_lock:
        event = {"text": text}
        event.update(details)
        g_progress_events.append(event)


def _check_range(document, start_line, end_line, expected):
    if start_line < 1 or end_line < start_line or end_line > len(document):
        raise ValueError("line range is outside the editable snapshot")
    actual = document[start_line - 1:end_line]
    if actual != expected:
        raise ValueError("expected text does not match the editable snapshot")


def _safe_path(cwd, value):
    """Resolve a workspace-relative path without allowing traversal or links out."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("path must be a non-empty string")
    if os.path.isabs(value) or ntpath.isabs(value):
        raise ValueError("absolute paths are not allowed")
    if any(part == ".." for part in value.replace("\\", "/").split("/")):
        raise ValueError("parent-directory components are not allowed")

    root = os.path.realpath(cwd)
    candidate = os.path.realpath(os.path.join(root, value))
    try:
        inside = os.path.commonpath([root, candidate]) == root
    except ValueError:
        inside = False
    if not inside or candidate == root:
        raise ValueError("path must stay below the current directory")
    return candidate


def apply_filesystem_tool(cwd, name, arguments):
    """Apply one explicitly requested filesystem operation inside cwd."""
    path = _safe_path(cwd, arguments.get("path"))
    if os.path.lexists(path):
        if os.path.islink(path):
            raise ValueError("symbolic links are not allowed")
        exists = True
    else:
        exists = False

    if name == "create_file":
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ValueError("file content must be a string")
        if exists:
            raise FileExistsError(f"path already exists: {arguments['path']}")
        parent = os.path.dirname(path)
        if not os.path.isdir(parent) or os.path.islink(parent):
            raise ValueError("file parent folder does not exist or is a symbolic link")
        with open(path, "x", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return {"ok": True, "message": f"created file {arguments['path']}"}

    if name == "create_folder":
        if exists:
            raise FileExistsError(f"path already exists: {arguments['path']}")
        parent = os.path.dirname(path)
        if not os.path.isdir(parent) or os.path.islink(parent):
            raise ValueError("parent folder does not exist or is a symbolic link")
        os.mkdir(path)
        return {"ok": True, "message": f"created folder {arguments['path']}"}

    if name == "delete_file":
        if not exists or not os.path.isfile(path):
            raise FileNotFoundError(f"file does not exist: {arguments['path']}")
        os.remove(path)
        return {"ok": True, "message": f"deleted file {arguments['path']}"}

    if name == "delete_folder":
        recursive = arguments.get("recursive")
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be boolean")
        if not exists or not os.path.isdir(path):
            raise FileNotFoundError(f"folder does not exist: {arguments['path']}")
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)
        return {"ok": True, "message": f"deleted folder {arguments['path']}"}

    raise ValueError(f"unknown filesystem tool: {name}")


def apply_tool(document, name, arguments, cwd=None):
    """Validate and apply one tool call to a document snapshot."""
    if name in FILE_TOOL_NAMES:
        if cwd is None:
            raise ValueError("filesystem tools require a current directory")
        return apply_filesystem_tool(cwd, name, arguments)

    if name == "insert_lines":
        line = arguments.get("line")
        content = arguments.get("content")
        if not isinstance(line, int) or not isinstance(content, list):
            raise ValueError("insert_lines has invalid arguments")
        if line < 1 or line > len(document) + 1:
            raise ValueError("insert line is outside the editable snapshot")
        if not all(isinstance(item, str) for item in content):
            raise ValueError("insert content must contain strings")
        document[line - 1:line - 1] = content
        return {"ok": True, "message": f"inserted {len(content)} line(s) at {line}"}

    if name in ("delete_lines", "replace_lines"):
        start = arguments.get("start_line")
        end = arguments.get("end_line")
        expected = arguments.get("expected")
        if not all(isinstance(value, int) for value in (start, end)):
            raise ValueError(f"{name} has invalid line range")
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"{name} expected must contain strings")
        if end - start + 1 != len(expected):
            raise ValueError(f"{name} expected length does not match line range")
        _check_range(document, start, end, expected)

        if name == "delete_lines":
            replacement = []
        else:
            replacement = arguments.get("replacement")
            if not isinstance(replacement, list) or not all(isinstance(item, str) for item in replacement):
                raise ValueError("replacement must contain strings")
        document[start - 1:end] = replacement
        return {"ok": True, "message": f"{name} applied to lines {start}-{end}"}

    raise ValueError(f"unknown edit tool: {name}")


def _edit_prompt(request, code, filetype):
    numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(code, 1))
    return (
        f"Edit this {filetype or 'text'} according to the request: {request}\n\n"
        "The editable region is shown below with 1-based line numbers. "
        "Use the provided tools for every change. Never return rewritten code. "
        "Use exact expected text for delete_lines and replace_lines. "
        "If the request asks for a project, create its folders and files with the filesystem tools. "
        "Put project files in a new child folder when appropriate, and provide complete file contents. "
        "File paths must be relative to the current directory; never use absolute paths or '..'. "
        "Make the smallest correct set of operations, then stop.\n\n"
        f"{numbered}"
    )


def _ollama_request(messages, settings, tools):
    baseurl = settings.get("url") or DEFAULT_HOST
    endpoint = baseurl.rstrip("/") + "/api/chat"
    model = settings.get("model") or DEFAULT_MODEL
    options = settings.get("options") or DEFAULT_OPTIONS
    if isinstance(options, str):
        options = json.loads(options)
    headers = {"Content-Type": "application/json"}
    credentialname = settings.get("credentialname")
    api_key = OllamaCredentials().GetApiKey("ollama", credentialname)
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    response = requests.post(
        endpoint,
        headers=headers,
        json={"model": model, "messages": messages, "tools": tools, "stream": False, "options": options},
        timeout=settings.get("timeout", 300),
    )
    response.raise_for_status()
    return response.json().get("message", {})


def _openai_request(messages, settings, tools):
    if OpenAI is None:
        raise ImportError("OpenAI package not found. Install it with pip install openai.")
    credentialname = settings.get("credentialname")
    api_key = OllamaCredentials().GetApiKey("openai", credentialname)
    client_options = {"api_key": api_key}
    if settings.get("url"):
        client_options["base_url"] = settings["url"]
    client = OpenAI(**client_options)
    options = settings.get("options") or DEFAULT_OPTIONS
    if isinstance(options, str):
        options = json.loads(options)
    request = {
        "model": settings.get("model") or DEFAULT_OPENAI_MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": options.get("temperature", 0),
        "max_tokens": options.get("max_tokens", 5000),
    }
    message = client.chat.completions.create(**request).choices[0].message
    return message


def _run_edit(request, code, filetype, settings):
    provider = settings.get("provider", DEFAULT_PROVIDER)
    if provider != "ollama" and not provider.startswith("openai"):
        raise ValueError(f"Tool-based editing is not supported for provider '{provider}'")

    messages = [
        {"role": "system", "content": "You are a precise code editing agent. Modify code only through the supplied tools."},
        {"role": "user", "content": _edit_prompt(request, code, filetype)},
    ]
    document = list(code)
    operations = []
    _progress(f"Starting {provider} request with {settings.get('model') or DEFAULT_MODEL}")

    for call_number in range(MAX_TOOL_CALLS):
        _progress(f"Waiting for model response ({call_number + 1}/{MAX_TOOL_CALLS})")
        message = _ollama_request(messages, settings, TOOLS) if provider == "ollama" else _openai_request(messages, settings, TOOLS)
        tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else (message.tool_calls or [])
        if not tool_calls:
            content = message.get("content", "") if isinstance(message, dict) else (message.content or "")
            _progress("Model finished" if not content else f"Model: {content.strip()[:240]}")
            return operations

        if isinstance(message, dict):
            messages.append(message)
        else:
            messages.append(message.model_dump(exclude_none=True))

        for call in tool_calls:
            if isinstance(call, dict):
                name = call.get("function", {}).get("name")
                raw_arguments = call.get("function", {}).get("arguments", "{}")
                call_id = call.get("id", "")
            else:
                name = call.function.name
                raw_arguments = call.function.arguments
                call_id = call.id
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            display_arguments = dict(arguments)
            if isinstance(display_arguments.get("content"), str):
                display_arguments["content"] = f"<{len(arguments['content'])} characters>"
            _progress(f"Tool call: {name} {json.dumps(display_arguments)}", tool=name, arguments=arguments)
            try:
                result = apply_tool(document, name, arguments, settings.get("cwd"))
                operation = {"tool": name, "arguments": arguments}
                operations.append(operation)
                _progress(result["message"], tool=name, path=arguments.get("path"))
            except Exception as error:
                result = {"ok": False, "error": str(error)}
                _progress(f"Tool error: {error}", tool=name)
            if provider == "ollama":
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result)})
            else:
                messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)})
    raise ValueError(f"model exceeded the {MAX_TOOL_CALLS}-operation limit")


def _worker(request, code, filetype, settings):
    global g_result, g_operations, g_errormsg
    try:
        operations = _run_edit(request, code, filetype, settings)
        _progress(f"Validated {len(operations)} operation(s)")
        with g_thread_lock:
            g_operations = operations
            g_result = "Done"
    except Exception as error:
        log.error(f"Error in tool-based edit: {error}")
        _progress(f"Error: {error}")
        with g_thread_lock:
            g_operations = []
            g_errormsg = str(error)
            g_result = "Error"


def start_vim_edit_code(request, code, filetype, settings):
    global g_editing_thread, g_result, g_operations, g_errormsg, g_progress_events
    if log is None:
        CreateLogger()
    settings = dict(settings)
    with g_thread_lock:
        g_result = "InProgress"
        g_operations = []
        g_errormsg = ""
        g_progress_events = []
    g_editing_thread = threading.Thread(target=_worker, args=(request, list(code), filetype, settings), daemon=True)
    g_editing_thread.start()


def get_job_status():
    with g_thread_lock:
        if g_editing_thread and g_editing_thread.is_alive():
            return "InProgress", [], ""
        return g_result, list(g_operations), g_errormsg


def get_progress_events():
    with g_thread_lock:
        return list(g_progress_events)


def apply_operations(bufnr, firstline, lastline, operations):
    """Apply the already validated operation sequence to a Vim buffer."""
    import vim

    buffer = vim.buffers[bufnr]
    original = list(buffer[firstline - 1:lastline])
    document = list(original)
    changed_ranges = []
    for operation in operations:
        if operation["tool"] not in FILE_TOOL_NAMES:
            arguments = operation["arguments"]
            if operation["tool"] == "insert_lines":
                start = firstline + arguments["line"] - 1
                end = start + max(len(arguments["content"]) - 1, 0)
            else:
                start = firstline + arguments["start_line"] - 1
                replacement = arguments.get("replacement", [])
                end = start + max(len(replacement) - 1, 0)
            changed_ranges.append([start, end])
            apply_tool(document, operation["tool"], operation["arguments"])
    if document != original:
        buffer[firstline - 1:lastline] = document
    return changed_ranges
