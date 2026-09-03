#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
"""Tool-driven code editing for vim-ollama.

The worker operates exclusively on a Python snapshot.  Vim is touched only by
the polling callback in the main thread after all requested operations have
been validated.
"""

import json
import glob as glob_module
import ntpath
import os
import re
import shutil
import stat
import subprocess
import threading
import uuid

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
            "name": "buf_insert_lines",
            "description": "Insert one or more lines before a 1-based line number relative to the editable buffer range. Use range length+1 to append.",
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
            "name": "buf_delete_lines",
            "description": "Delete an exact inclusive range of lines from the editable buffer range. Line numbers are relative to that range and expected text must match exactly.",
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
            "name": "buf_replace_lines",
            "description": "Replace an exact inclusive range of lines in the editable buffer range. Line numbers are relative to that range.",
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

FILE_LINE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "insert_lines",
            "description": "Insert one or more lines into a project file before an absolute 1-based line number. Use line number length+1 to append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path below the current directory."},
                    "line": {"type": "integer", "minimum": 1},
                    "content": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path", "line", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_lines",
            "description": "Delete an exact inclusive range of lines from a project file using absolute 1-based line numbers. The expected text must match exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path below the current directory."},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "expected": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path", "start_line", "end_line", "expected"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_lines",
            "description": "Replace an exact inclusive range of lines in a project file using absolute 1-based line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path below the current directory."},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "expected": {"type": "array", "items": {"type": "string"}},
                    "replacement": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path", "start_line", "end_line", "expected", "replacement"],
                "additionalProperties": False,
            },
        },
    },
]

FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "chmod",
            "description": "Make an existing regular file below the current directory executable without changing its read/write permissions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path below the current directory."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
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

INSPECTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file below the current directory. Use this to inspect existing project files before editing them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path below the current directory."},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Search for filenames in a directory using wildcards. Use ** in the pattern for recursive searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Wildcard filename pattern, for example '*.c'."},
                    "path": {"type": "string", "description": "Relative directory below the current directory."},
                },
                "required": ["pattern", "path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents using a regular expression. Path may be a file or directory; directory recursion is controlled by recursive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regular expression to search for."},
                    "path": {"type": "string", "description": "Relative file or directory below the current directory."},
                    "recursive": {"type": "boolean", "default": False},
                },
                "required": ["pattern", "path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files below a directory. Use recursive=true to include files in nested directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory below the current directory, or '.'."},
                    "recursive": {"type": "boolean"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]

MAKE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "vim-make",
            "description": "Builds the project using Vim's configured makeprg and inspect its compiler errors and warnings. Optional arguments are whitespace-separated make target names only. Use it after changing code and before finishing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arguments": {"type": "string", "description": "Optional whitespace-separated make target names, for example 'all', 'clean', or 'distclean'. Shell commands and options are not allowed."},
                },
                "required": ["arguments"],
                "additionalProperties": False,
            },
        },
    },
]

CHECK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "vim-check",
            "description": "Run the configured language checker and inspect its diagnostics. Use after changing script-language files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional project-relative file path. If omitted, check the current buffer file."},
                },
                "additionalProperties": False,
            },
        },
    },
]

EXECUTE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": "Execute an existing executable file below the current directory for testing. User confirmation is required before execution. Timeout values are in seconds. NEVER invoke system tools!",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to an executable file below the current directory."},
                    "arguments": {"type": "array", "items": {"type": "string"}, "description": "Arguments passed to the executable without a shell."},
                    "timeout": {"type": "number", "minimum": 0, "default": 30, "description": "Seconds before sending SIGTERM."},
                    "kill_timeout": {"type": "number", "minimum": 0, "default": 3, "description": "Seconds after SIGTERM before sending SIGKILL."},
                },
                "required": ["path", "arguments"],
                "additionalProperties": False,
            },
        },
    },
]

GIT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "git_init",
            "description": "Initialize a Git repository in the current project directory.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_add",
            "description": "Stage the specified project-relative paths with Git.",
            "parameters": {
                "type": "object",
                "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                "required": ["paths"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_rm",
            "description": "Remove the specified project-relative paths from Git and the working tree.",
            "parameters": {
                "type": "object",
                "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                "required": ["paths"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_restore",
            "description": "Restore specified project-relative paths from Git. This discards working-tree changes unless staged=true, which restores the index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "staged": {"type": "boolean"},
                },
                "required": ["paths"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a Git commit with the supplied commit message.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show the current Git branch and working-tree status.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent Git commits from the current project.",
            "parameters": {
                "type": "object",
                "properties": {"max_count": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show Git changes in the current project. Set staged=true to show staged changes.",
            "parameters": {
                "type": "object",
                "properties": {"staged": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
    },
]

FILE_TOOLS = FILE_LINE_TOOLS + FILE_TOOLS
TOOLS = BUFFER_TOOLS + FILE_TOOLS + INSPECTION_TOOLS + MAKE_TOOLS + CHECK_TOOLS + EXECUTE_TOOLS + GIT_TOOLS
BUFFER_TOOL_NAMES = {tool["function"]["name"] for tool in BUFFER_TOOLS}
FILE_LINE_TOOL_NAMES = {tool["function"]["name"] for tool in FILE_LINE_TOOLS}
FILE_TOOL_NAMES = {tool["function"]["name"] for tool in FILE_TOOLS}
INSPECTION_TOOL_NAMES = {tool["function"]["name"] for tool in INSPECTION_TOOLS}
MAKE_TOOL_NAMES = {tool["function"]["name"] for tool in MAKE_TOOLS}
CHECK_TOOL_NAMES = {tool["function"]["name"] for tool in CHECK_TOOLS}
EXECUTE_TOOL_NAMES = {tool["function"]["name"] for tool in EXECUTE_TOOLS}
GIT_TOOL_NAMES = {tool["function"]["name"] for tool in GIT_TOOLS}
GIT_READ_TOOL_NAMES = {"git_status", "git_log", "git_diff"}
RANGE_TOOLS = BUFFER_TOOLS + INSPECTION_TOOLS + MAKE_TOOLS + EXECUTE_TOOLS
RANGE_TOOLS += [tool for tool in GIT_TOOLS if tool["function"]["name"] in GIT_READ_TOOL_NAMES]
WORKSPACE_TOOLS = FILE_TOOLS + INSPECTION_TOOLS + MAKE_TOOLS + CHECK_TOOLS + EXECUTE_TOOLS + GIT_TOOLS

log = None
g_thread_lock = threading.Lock()
g_editing_thread = None
g_result = None
g_operations = []
g_errormsg = ""
g_progress_events = []
g_messages = []
g_make_condition = threading.Condition()
g_make_results = {}


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

def _info(text, **details):
    with g_thread_lock:
        event = {"text": text}
        event.update(details)
        g_progress_events.append(event)

def submit_make_result(request_id, result):
    """Deliver a main-thread Vim :make result to the waiting worker."""
    with g_make_condition:
        if request_id in g_make_results:
            g_make_results[request_id] = result
            g_make_condition.notify_all()


def _request_make(arguments):
    if not isinstance(arguments, dict):
        error = "make tool requires make target arguments"
        _progress(f"Tool error: {error}", tool="make")
        return {"ok": False, "message": error, "error": error, "diagnostics": []}
    requested = arguments.get("arguments", "")
    if requested in (None, ""):
        requested = ""
    if not isinstance(requested, str):
        error = "make targets must be provided as a string"
        _progress(f"Tool error: {error}", tool="make")
        return {"ok": False, "message": error, "error": error, "diagnostics": []}
    targets = requested.split()
    if any(not re.fullmatch(r"[A-Za-z0-9_./:+-]+", target) or target.startswith("-") for target in targets):
        error = "make tool accepts only make target names; shell commands and options are not allowed"
        _progress(f"Tool error: {error}", tool="make")
        return {"ok": False, "message": error, "error": error, "diagnostics": []}
    request_id = str(uuid.uuid4())
    with g_make_condition:
        g_make_results[request_id] = None
    _progress("Running configured makeprg", type="make_request", request_id=request_id, arguments={"arguments": " ".join(targets)})
    with g_make_condition:
        while g_make_results[request_id] is None:
            g_make_condition.wait()
        return g_make_results.pop(request_id)


def _request_check(arguments):
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("vim-check requires an argument object")
    path = arguments.get("path")
    if path is not None and (not isinstance(path, str) or not path or "\x00" in path):
        raise ValueError("vim-check path must be a non-empty string")
    if isinstance(path, str) and (os.path.isabs(path) or ntpath.isabs(path) or any(part == ".." for part in path.replace("\\", "/").split("/"))):
        raise ValueError("vim-check path must remain below the current directory")
    arguments = {"path": path} if path is not None else {}
    request_id = str(uuid.uuid4())
    with g_make_condition:
        g_make_results[request_id] = None
    _progress("Running configured checker", type="check_request", request_id=request_id, arguments=arguments)
    with g_make_condition:
        while g_make_results[request_id] is None:
            g_make_condition.wait()
        return g_make_results.pop(request_id)


def _request_execute(arguments):
    if not isinstance(arguments, dict):
        error = "execute tool requires a path and argument list"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    path = arguments.get("path")
    requested_arguments = arguments.get("arguments")
    if not isinstance(path, str) or not path or "\x00" in path:
        error = "execute path must be a non-empty string"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    if os.path.isabs(path) or ntpath.isabs(path) or any(part == ".." for part in path.replace("\\", "/").split("/")):
        error = "execute path must be relative and remain below the current directory"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    if not isinstance(requested_arguments, list) or not all(isinstance(item, str) and "\x00" not in item for item in requested_arguments):
        error = "execute arguments must be a list of strings"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    timeout = arguments.get("timeout", 30)
    kill_timeout = arguments.get("kill_timeout", 3)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
        error = "execute timeout must be a non-negative number of seconds"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    if isinstance(kill_timeout, bool) or not isinstance(kill_timeout, (int, float)) or kill_timeout < 0:
        error = "execute kill_timeout must be a non-negative number of seconds"
        _progress(f"Tool error: {error}", tool="execute")
        return {"ok": False, "message": error, "error": error}
    arguments = dict(arguments)
    arguments["timeout"] = timeout
    arguments["kill_timeout"] = kill_timeout
    request_id = str(uuid.uuid4())
    with g_make_condition:
        g_make_results[request_id] = None
    _progress("Waiting for execution confirmation", type="execute_request", request_id=request_id, arguments=arguments)
    with g_make_condition:
        while g_make_results[request_id] is None:
            g_make_condition.wait()
        return g_make_results.pop(request_id)


def _run_git_tool(cwd, name, arguments):
    if not isinstance(arguments, dict):
        raise ValueError(f"{name} requires an argument object")

    command = ["git"]
    if name == "git_init":
        command += ["init", "."]
    elif name in ("git_add", "git_rm", "git_restore"):
        paths = arguments.get("paths")
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"{name} requires a non-empty list of paths")
        for path in paths:
            if not isinstance(path, str) or not path or "\x00" in path:
                raise ValueError(f"{name} paths must be non-empty strings")
            if os.path.isabs(path) or ntpath.isabs(path) or any(part == ".." for part in path.replace("\\", "/").split("/")):
                raise ValueError(f"{name} paths must stay below the current directory")
        if name == "git_add":
            command += ["add", "--"] + paths
        elif name == "git_rm":
            command += ["rm", "--"] + paths
        else:
            staged = arguments.get("staged", False)
            if not isinstance(staged, bool):
                raise ValueError("git_restore staged must be boolean")
            command += ["restore"]
            if staged:
                command.append("--staged")
            command += ["--"] + paths
    elif name == "git_commit":
        message = arguments.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("git_commit requires a non-empty commit message")
        command += ["commit", "-m", message]
    elif name == "git_status":
        command += ["status", "--short", "--branch"]
    elif name == "git_log":
        max_count = arguments.get("max_count", 10)
        if isinstance(max_count, bool) or not isinstance(max_count, int) or not 1 <= max_count <= 100:
            raise ValueError("git_log max_count must be an integer from 1 to 100")
        command += ["log", "--oneline", f"--max-count={max_count}"]
    elif name == "git_diff":
        staged = arguments.get("staged", False)
        if not isinstance(staged, bool):
            raise ValueError("git_diff staged must be boolean")
        command += ["diff"]
        if staged:
            command.append("--cached")
    else:
        raise ValueError(f"unknown Git tool: {name}")

    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
    output = "\n".join(part for part in (completed.stdout.rstrip(), completed.stderr.rstrip()) if part)
    return {
        "ok": completed.returncode == 0,
        "message": f"{name} completed" if completed.returncode == 0 else f"{name} failed",
        "output": output,
        "exit_code": completed.returncode,
    }


def _check_range(document, start_line, end_line, expected):
    if start_line < 1 or end_line < start_line or end_line > len(document):
        raise ValueError("line range is outside the editable snapshot")
    actual = document[start_line - 1:end_line]
    if actual != expected:
        raise ValueError("expected text does not match the editable snapshot")


def _normalize_expected(document, start_line, end_line, expected):
    """Allow omitted trailing blank lines without relaxing content checks."""
    if start_line < 1 or end_line < start_line or end_line > len(document):
        raise ValueError("line range is outside the editable snapshot")

    actual = document[start_line - 1:end_line]
    if len(expected) < len(actual):
        missing = actual[len(expected):]
        if expected == actual[:len(expected)] and all(line == "" for line in missing):
            return expected + missing
    elif len(expected) > len(actual):
        extra = expected[len(actual):]
        if expected[:len(actual)] == actual and all(line == "" for line in extra):
            return expected[:len(actual)]
    return expected


def _safe_path(cwd, value, allow_root=False):
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
    if not inside or (candidate == root and not allow_root):
        raise ValueError("path must stay below the current directory")
    return candidate


def _read_file(cwd, arguments):
    path = _safe_path(cwd, arguments.get("path"))
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError("path is not a regular file")
    if os.path.getsize(path) > 1024 * 1024:
        raise ValueError("file is larger than the 1 MiB inspection limit")
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    start = arguments.get("start_line", 1)
    end = arguments.get("end_line", max(len(lines), 1))
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        raise ValueError("invalid line range")
    content = "".join(lines[start - 1:end])
    return {"ok": True, "message": f"read {arguments['path']} lines {start}-{min(end, len(lines))}", "content": content}


def _inspection_files(root, recursive):
    if os.path.isfile(root):
        yield root
        return

    directories = [root]
    while directories:
        directory = directories.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file(follow_symlinks=False):
                yield entry.path
            elif recursive and entry.is_dir(follow_symlinks=False):
                directories.append(entry.path)


def _glob_files(cwd, arguments):
    root = _safe_path(cwd, arguments.get("path"), allow_root=True)
    if os.path.islink(root) or not os.path.isdir(root):
        raise ValueError("glob path is not a regular directory")
    pattern = arguments.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("glob pattern must be a non-empty string")
    if os.path.isabs(pattern) or ntpath.isabs(pattern) or any(part == ".." for part in pattern.replace("\\", "/").split("/")):
        raise ValueError("glob pattern must remain below the search directory")

    matches = []
    for path in glob_module.iglob(os.path.join(root, pattern), recursive=True):
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        matches.append(os.path.relpath(path, cwd))
        if len(matches) >= 1000:
            return {"ok": True, "message": "glob reached the 1000 match limit", "content": "\n".join(matches)}
    content = "\n".join(matches) if matches else "No matches found."
    return {"ok": True, "message": f"found {len(matches)} match(es)", "content": content}


def _grep_files(cwd, arguments):
    root = _safe_path(cwd, arguments.get("path"), allow_root=True)
    if os.path.islink(root) or not (os.path.isfile(root) or os.path.isdir(root)):
        raise ValueError("grep path is not a regular file or directory")
    try:
        pattern = re.compile(arguments.get("pattern", ""))
    except re.error as error:
        raise ValueError(f"invalid regular expression: {error}") from error
    recursive = arguments.get("recursive", False)
    if not isinstance(recursive, bool):
        raise ValueError("grep recursive must be boolean")

    matches = []
    for path in _inspection_files(root, recursive):
        if os.path.getsize(path) > 1024 * 1024:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if pattern.search(line):
                        relative = os.path.relpath(path, cwd)
                        matches.append(f"{relative}:{line_number}:{line.rstrip()}")
                        if len(matches) >= 100:
                            return {"ok": True, "message": "grep reached the 100 match limit", "content": "\n".join(matches)}
        except (UnicodeDecodeError, OSError):
            continue
    content = "\n".join(matches) if matches else "No matches found."
    return {"ok": True, "message": f"found {len(matches)} match(es)", "content": content}


def _list_files(cwd, arguments):
    root = _safe_path(cwd, arguments.get("path"), allow_root=True)
    if not os.path.isdir(root) or os.path.islink(root):
        raise ValueError("list path is not a regular directory")
    recursive = arguments.get("recursive", False)
    if not isinstance(recursive, bool):
        raise ValueError("recursive must be boolean")

    files = []
    directories = [root]
    while directories:
        directory = directories.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            if entry.is_file(follow_symlinks=False):
                files.append(os.path.relpath(entry.path, cwd))
                if len(files) >= 1000:
                    files.sort()
                    content = "\n".join(files)
                    return {"ok": True, "message": "file listing reached the 1000 file limit", "content": content}
            elif recursive and entry.name != ".git" and entry.is_dir(follow_symlinks=False):
                directories.append(entry.path)

    files.sort()
    content = "\n".join(files) if files else "No files found."
    return {"ok": True, "message": f"listed {len(files)} file(s)", "content": content}


def apply_filesystem_tool(cwd, name, arguments):
    """Apply one explicitly requested filesystem operation inside cwd."""
    path = _safe_path(cwd, arguments.get("path"))
    if os.path.lexists(path):
        if os.path.islink(path):
            raise ValueError("symbolic links are not allowed")
        exists = True
    else:
        exists = False

    if name in FILE_LINE_TOOL_NAMES:
        if not exists or not os.path.isfile(path):
            raise FileNotFoundError(f"file does not exist: {arguments['path']}")
        if os.path.getsize(path) > 1024 * 1024:
            raise ValueError("file is larger than the 1 MiB editing limit")

        with open(path, "r", encoding="utf-8", newline="") as handle:
            original_text = handle.read()
        newline = "\r\n" if "\r\n" in original_text else "\n"
        document = original_text.splitlines()

        if name == "insert_lines":
            line = arguments.get("line")
            content = arguments.get("content")
            if not isinstance(line, int) or not isinstance(content, list):
                raise ValueError("insert_lines has invalid file arguments")
            if line < 1 or line > len(document) + 1:
                raise ValueError("insert line is outside the file")
            if not all(isinstance(item, str) for item in content):
                raise ValueError("insert content must contain strings")
            document[line - 1:line - 1] = content
        else:
            start = arguments.get("start_line")
            end = arguments.get("end_line")
            expected = arguments.get("expected")
            if not all(isinstance(value, int) for value in (start, end)):
                raise ValueError(f"{name} has invalid file line range")
            if not isinstance(expected, list):
                raise ValueError(f"{name}: expected must be a list of strings, got {type(expected).__name__}")
            if not all(isinstance(item, str) for item in expected):
                raise ValueError(f"{name}: every expected item must be a string")
            expected = _normalize_expected(document, start, end, expected)
            if end - start + 1 != len(expected):
                raise ValueError(f"{name} expected length does not match file line range")
            _check_range(document, start, end, expected)

            replacement = [] if name == "delete_lines" else arguments.get("replacement")
            if not isinstance(replacement, list):
                raise ValueError(f"{name}: replacement must be a list of strings, got {type(replacement).__name__}")
            if not all(isinstance(item, str) for item in replacement):
                raise ValueError(f"{name}: every replacement item must be a string")
            document[start - 1:end] = replacement

        updated_text = newline.join(document)
        if document and original_text.endswith(("\n", "\r")):
            updated_text += newline
        if updated_text != original_text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated_text)
        return {"ok": True, "message": f"{name} applied to file {arguments['path']}"}

    if name == "chmod":
        if not exists or not os.path.isfile(path):
            raise FileNotFoundError(f"file does not exist: {arguments['path']}")
        mode = os.stat(path, follow_symlinks=False).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH, follow_symlinks=False)
        return {"ok": True, "message": f"made file executable {arguments['path']}"}

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
    """Validate and apply one tool call using 1-based snapshot line numbers.

    In range-edit mode, ``document`` is only the selected Vim range, so all
    buffer-tool line arguments are relative to that range rather than the full
    Vim buffer.
    """
    if name == "read_file":
        if cwd is None:
            raise ValueError("read_file requires a current directory")
        return _read_file(cwd, arguments)
    if name == "glob":
        if cwd is None:
            raise ValueError("glob requires a current directory")
        return _glob_files(cwd, arguments)
    if name == "grep":
        if cwd is None:
            raise ValueError("grep requires a current directory")
        return _grep_files(cwd, arguments)
    if name == "list_files":
        if cwd is None:
            raise ValueError("list_files requires a current directory")
        return _list_files(cwd, arguments)
    if name in MAKE_TOOL_NAMES:
        raise ValueError("make must be executed by Vim's main thread")
    if name in CHECK_TOOL_NAMES:
        raise ValueError("vim-check must be executed by Vim's main thread")
    if name in FILE_TOOL_NAMES:
        if cwd is None:
            raise ValueError("filesystem tools require a current directory")
        return apply_filesystem_tool(cwd, name, arguments)

    if name == "buf_insert_lines":
        line = arguments.get("line")
        content = arguments.get("content")
        if not isinstance(line, int) or not isinstance(content, list):
            raise ValueError("buf_insert_lines has invalid arguments")
        if line < 1 or line > len(document) + 1:
            raise ValueError("insert line is outside the editable snapshot")
        if not all(isinstance(item, str) for item in content):
            raise ValueError("insert content must contain strings")
        document[line - 1:line - 1] = content
        return {"ok": True, "message": f"inserted {len(content)} line(s) at {line}"}

    if name in ("buf_delete_lines", "buf_replace_lines"):
        start = arguments.get("start_line")
        end = arguments.get("end_line")
        expected = arguments.get("expected")
        if not all(isinstance(value, int) for value in (start, end)):
            raise ValueError(f"{name} has invalid line range")
        if not isinstance(expected, list):
            raise ValueError(f"{name}: expected must be a list of strings, got {type(expected).__name__}")
        if not all(isinstance(item, str) for item in expected):
            raise ValueError(f"{name}: every expected item must be a string")
        expected = _normalize_expected(document, start, end, expected)
        if end - start + 1 != len(expected):
            raise ValueError(f"{name} expected length does not match line range")
        _check_range(document, start, end, expected)

        if name == "buf_delete_lines":
            replacement = []
        else:
            replacement = arguments.get("replacement")
            if not isinstance(replacement, list):
                raise ValueError(f"{name}: replacement must be a list of strings, got {type(replacement).__name__}")
            if not all(isinstance(item, str) for item in replacement):
                raise ValueError(f"{name}: every replacement item must be a string")
        document[start - 1:end] = replacement
        return {"ok": True, "message": f"{name} applied to lines {start}-{end}"}

    raise ValueError(f"unknown edit tool: {name}")


def _load_project_instructions(cwd):
    instructions = []
    current = os.path.realpath(cwd)
    while True:
        for filename in ("AGENTS.md", "CLAUDE.md"):
            path = os.path.join(current, filename)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            try:
                if os.path.getsize(path) <= 128 * 1024:
                    with open(path, "r", encoding="utf-8") as handle:
                        instructions.append((os.path.relpath(path, cwd), handle.read()))
            except (OSError, UnicodeDecodeError):
                continue
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return list(reversed(instructions))


def _system_prompt(settings):
    cwd = settings.get("cwd") or os.getcwd()
    provider = settings.get("provider", DEFAULT_PROVIDER)
    model = settings.get("model") or (DEFAULT_MODEL if provider == "ollama" else DEFAULT_OPENAI_MODEL)
    lines = [
        "You are a precise coding agent operating inside Vim.",
        f"Provider: {provider}; model: {model}.",
        f"Working directory: {cwd}",
        f"Operating system: {os.name}",
        "Use only the supplied tools for changes and execution. Do not return rewritten files as a substitute for tool calls.",
        "Use tools only through the provided tool-calling interface.",
        "Never write or imitate tool-call markup in normal response text.",
        "Do not manually emit <tool_call>, <function=...>, <parameter=...>,",
        "JSON tool calls, or similar syntax.",
        "When a tool is required, invoke the supplied tool directly.",
        "Build only with the supplied vim-make tool. Never run a compiler, shell, or custom build command through another tool.",
        "Only build compiled languages like C/C++, don't use vim-make for scripting languages like Python.",
        "Use the supplied Git tools for repository tracking; never use execute to invoke Git.",
        "Use buf_replace_lines instead of calling sed for the current buffer range.",
    ]
    if settings.get("explain_mode", False):
        lines.extend([
            "This is a read-only code explanation request.",
            "Use only the supplied inspection tools to inspect the selected code or related files.",
            "Do not modify buffers or files and do not call tools that are not supplied.",
        ])
    elif settings.get("range_mode", True):
        lines.extend([
            "This is a range edit inside the current Vim buffer.",
            "Modify only the specified buffer range with the buffer edit tools. Do not create, delete, or modify files.",
            "Reading and searching other files is allowed for context.",
        ])
    else:
        lines.extend([
            "This is a workspace edit. You may read and modify project files below the working directory with the filesystem tools.",
            "Keep all paths relative to the working directory and never use absolute paths or '..'.",
            "Use insert_lines, delete_lines, and replace_lines for files; their line numbers are absolute 1-based file line numbers.",
            "When a language checker is configured, use vim-check after changes instead of vim-make.",
        ])
    configured = settings.get("instructions")
    if configured:
        lines.append("Configured instructions:\n" + configured)
    for filename, content in _load_project_instructions(cwd):
        lines.append(f"Instructions from {filename}:\n{content}")
    return "\n\n".join(lines)


def _edit_prompt(request, code, filetype, settings):
    if not settings.get("range_mode", True):
        return (
            f"User request:\n{request}\n\n"
            "Work across the project as needed using the filesystem and inspection tools. "
            "Validate changes with vim-make before finishing."
        )

    start_line = settings.get("start_line", 1)
    # The model sees absolute Vim numbers for context, but tool arguments use
    # positions relative to the editable snapshot passed in as ``code``.
    numbered = "\n".join(
        f"{index}|{line}" for index, line in enumerate(code, start_line)
    )

    filename = settings.get("filename") or "[No filename]"
    end_line = settings.get("end_line", len(code))

    if settings.get("explain_mode", False):
        return (
            f"Explain the following {filetype or 'text'} code in detail.\n\n"
            "Describe its purpose, important control flow, dependencies, and any relevant issues. "
            "Do not call tools if not necessary."
            "Do not modify any buffers or files.\n\n"
            f"Current Vim buffer: {filename}\n"
            f"Selected range: lines {start_line}-{end_line}\n\n"
            f"{numbered}"
        )

    return (
        f"User request:\n{request}\n\n"
        f"Current Vim buffer: {filename}\n"
        f"Filetype: {filetype or 'text'}\n"
        f"Editable range: lines {start_line}-{end_line}\n\n"

        "Modify only this range in the current Vim buffer with the buffer edit tools. "
        "Do not create, delete, or modify any files. "
        "Reading and searching other files is allowed.\n\n"

        "The buffer snapshot below uses this format:\n"
        "<vim-line-number>|<exact-buffer-content>\n\n"
        "The line number and '|' separator are metadata and are not part of the buffer. "
        "Everything after '|' is the exact buffer content. "
        "Preserve it exactly when constructing expected text, including leading whitespace, "
        "tabs, trailing whitespace, and empty lines.\n\n"

        "Buffer edit tool line numbers are relative to the editable range: "
        f"tool line 1 is Vim line {start_line}, "
        f"tool line 2 is Vim line {start_line + 1}, and so on. "
        "Do not use the displayed Vim line numbers as tool line arguments.\n\n"

        "For buf_delete_lines and buf_replace_lines, expected must match the current buffer text exactly. "
        "Prefer the smallest possible edit and avoid including unchanged surrounding lines "
        "unless necessary. "
        "Validate changes with vim-make when appropriate, then stop.\n\n"

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
    payload = response.json()
    message = dict(payload.get("message") or {})
    usage = {
        key: payload[key]
        for key in ("prompt_eval_count", "eval_count")
        if isinstance(payload.get(key), int) and not isinstance(payload.get(key), bool)
    }
    if usage:
        message["_ollama_usage"] = usage
    return message


def _context_usage(message, settings):
    usage = message.get("_ollama_usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_eval_count")
    response_tokens = usage.get("eval_count")
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
               for value in (prompt_tokens, response_tokens)):
        return None
    options = settings.get("options") or DEFAULT_OPTIONS
    if isinstance(options, str):
        options = json.loads(options)
    num_ctx = options.get("num_ctx") if isinstance(options, dict) else None
    if not isinstance(num_ctx, int) or isinstance(num_ctx, bool) or num_ctx <= 0:
        return None
    used = prompt_tokens + response_tokens

    def format_tokens(value):
        return f"{value / 1000:.1f}k" if value >= 1000 else str(value)

    percentage = round(used * 100 / num_ctx)
    return f"Context: {format_tokens(used)} / {format_tokens(num_ctx)} ({percentage}%)"


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

    previous_messages = settings.get("messages")
    range_mode = settings.get("range_mode", True)
    if settings.get("explain_mode", False):
        tools = INSPECTION_TOOLS
        # it seems to work smoother without tools, and unless very complicated stuff it should not
        # be necessary to inspect other files. Maybe add an option later.
        tools = []
    else:
        tools = RANGE_TOOLS if range_mode else WORKSPACE_TOOLS
        if settings.get("quickfix_checker", False):
            tools = [tool for tool in tools if tool["function"]["name"] != "vim-make"]
        elif settings.get("quickfix_mode", False):
            tools = [tool for tool in tools if tool["function"]["name"] != "vim-check"]
    if previous_messages:
        messages = list(previous_messages)
        messages.append({"role": "user", "content": _edit_prompt(request, code, filetype, settings)})
    else:
        messages = [
            {"role": "system", "content": _system_prompt(settings)},
            {"role": "user", "content": _edit_prompt(request, code, filetype, settings)},
        ]
    # Keep tool coordinates relative to this range while the model is editing.
    document = list(code)
    operations = []
    _progress(f"Starting {provider} request with {settings.get('model') or DEFAULT_MODEL}")
    _info(f"range_mode: {range_mode}")

    tool_names = [tool["function"]["name"] for tool in tools]
    _info(f"available tools: {tool_names}")

    for call_number in range(MAX_TOOL_CALLS):
        _progress(f"Waiting for model response ({call_number + 1}/{MAX_TOOL_CALLS})")
        if log is not None:
            log.debug("Complete edit prompt:\n" + json.dumps({"messages": messages, "tools": tools}, indent=2))
        message = _ollama_request(messages, settings, tools) if provider == "ollama" else _openai_request(messages, settings, tools)
        context = _context_usage(message, settings)
        if context:
            _progress(context, diagnostic={"title": "Context", "content": context})
        tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else (message.tool_calls or [])
        if isinstance(message, dict):
            messages.append({key: value for key, value in message.items() if key != "_ollama_usage"})
        else:
            messages.append(message.model_dump(exclude_none=True))
        if not tool_calls:
            content = message.get("content", "") if isinstance(message, dict) else (message.content or "")
            _progress("Model finished" if not content else f"Model: {content.strip()}")
            return operations, messages

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
            original_arguments = arguments
            if name in ("buf_insert_lines", "insert_lines") and isinstance(arguments, dict) and isinstance(arguments.get("content"), str):
                arguments = dict(arguments)
                arguments["content"] = arguments["content"].splitlines()
            if name in ("buf_delete_lines", "buf_replace_lines", "delete_lines", "replace_lines") and isinstance(arguments, dict):
                arguments = dict(arguments)
                for key in ("expected", "replacement"):
                    if isinstance(arguments.get(key), str):
                        arguments[key] = arguments[key].splitlines()
            if log is not None:
                log.debug(f"Tool call: {name} {json.dumps(arguments)}")
            display_arguments = dict(arguments) if isinstance(arguments, dict) else arguments
            if isinstance(original_arguments, dict) and isinstance(original_arguments.get("content"), str):
                display_arguments = dict(display_arguments)
                display_arguments["content"] = f"<{len(original_arguments['content'])} characters>"
            _progress(f"Tool call: {name} {json.dumps(display_arguments)}", tool=name, arguments=arguments)
            try:
                if settings.get("range_mode", True) and name in FILE_TOOL_NAMES:
                    raise ValueError("filesystem tools are not allowed during a range edit")
                if not settings.get("range_mode", True) and name in BUFFER_TOOL_NAMES:
                    raise ValueError("buffer edit tools require an editable range")
                if settings.get("range_mode", True) and name in GIT_TOOL_NAMES - GIT_READ_TOOL_NAMES:
                    raise ValueError("Git write tools are not allowed during a range edit")
                if name in MAKE_TOOL_NAMES:
                    result = _request_make(arguments)
                elif name in CHECK_TOOL_NAMES:
                    result = _request_check(arguments)
                elif name in EXECUTE_TOOL_NAMES:
                    result = _request_execute(arguments)
                elif name in GIT_TOOL_NAMES:
                    result = _run_git_tool(settings.get("cwd"), name, arguments)
                else:
                    result = apply_tool(document, name, arguments, settings.get("cwd"))
                if name not in INSPECTION_TOOL_NAMES and name not in MAKE_TOOL_NAMES and name not in CHECK_TOOL_NAMES and name not in EXECUTE_TOOL_NAMES and name not in GIT_TOOL_NAMES:
                    operation = {"tool": name, "arguments": arguments}
                    operations.append(operation)
                diagnostic = result.get("content") or result.get("output")
                details = {"tool": name, "path": arguments.get("path")}
                if diagnostic:
                    details["diagnostic"] = {"title": name, "content": diagnostic}
                _progress(result["message"], **details)
            except Exception as error:
                result = {"ok": False, "error": str(error)}
                _progress(f"Tool error: {error}; request: {json.dumps(arguments)}", tool=name, arguments=arguments)
                if settings.get("stop_on_error", False):
                    raise ValueError(f"{name} failed: {error}") from error
            if provider == "ollama":
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result)})
            else:
                messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)})
    raise ValueError(f"model exceeded the {MAX_TOOL_CALLS}-operation limit")


def _worker(request, code, filetype, settings):
    global g_result, g_operations, g_errormsg, g_messages
    try:
        operations, messages = _run_edit(request, code, filetype, settings)
        _progress(f"Validated {len(operations)} operation(s)")
        with g_thread_lock:
            g_operations = operations
            g_messages = messages
            g_result = "Done"
    except Exception as error:
        log.error(f"Error in tool-based edit: {error}")
        _progress(f"Error: {error}")
        with g_thread_lock:
            g_operations = []
            g_errormsg = str(error)
            g_result = "Error"


def start_vim_edit_code(request, code, filetype, settings):
    global g_editing_thread, g_result, g_operations, g_errormsg, g_progress_events, g_messages
    if log is None:
        CreateLogger()
    settings = dict(settings)
    with g_thread_lock:
        if settings.get("continue_history") and g_messages:
            settings["messages"] = list(g_messages)
        elif not settings.get("continue_history"):
            g_messages = []
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
    """Apply validated relative-range operations to the actual Vim buffer."""
    import vim

    buffer = vim.buffers[bufnr]
    original = list(buffer[firstline - 1:lastline])
    document = list(original)
    changed_ranges = []
    for operation in operations:
        if operation["tool"] not in FILE_TOOL_NAMES:
            arguments = operation["arguments"]
            if operation["tool"] == "buf_insert_lines":
                start = firstline + arguments["line"] - 1
                end = start + max(len(arguments["content"]) - 1, 0)
            else:
                # Tool arguments address the sliced document; changed signs
                # must use the corresponding absolute Vim line numbers.
                start = firstline + arguments["start_line"] - 1
                replacement = arguments.get("replacement", [])
                end = start + max(len(replacement) - 1, 0)
            changed_ranges.append([start, end])
            apply_tool(document, operation["tool"], operation["arguments"])
    if document != original:
        buffer[firstline - 1:lastline] = document
    return changed_ranges
