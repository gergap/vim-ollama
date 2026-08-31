import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

import CodeEditor
from CodeEditor import apply_tool


def test_insert_lines():
    document = ["one", "three"]

    result = apply_tool(document, "insert_lines", {"line": 2, "content": ["two"]})

    assert result["ok"]
    assert document == ["one", "two", "three"]


def test_replace_lines_requires_exact_expected_text():
    document = ["one", "two", "three"]

    with pytest.raises(ValueError):
        apply_tool(
            document,
            "replace_lines",
            {"start_line": 2, "end_line": 2, "expected": ["wrong"], "replacement": ["new"]},
        )

    assert document == ["one", "two", "three"]


def test_delete_and_replace_lines():
    document = ["one", "two", "three", "four"]

    apply_tool(document, "delete_lines", {"start_line": 2, "end_line": 2, "expected": ["two"]})
    apply_tool(
        document,
        "replace_lines",
        {"start_line": 2, "end_line": 3, "expected": ["three", "four"], "replacement": ["3", "4"]},
    )

    assert document == ["one", "3", "4"]


def test_insert_at_end():
    document = ["one"]

    apply_tool(document, "insert_lines", {"line": 2, "content": ["two", "three"]})

    assert document == ["one", "two", "three"]


def test_tool_loop_returns_validated_operations(monkeypatch):
    responses = iter(
        [
            {"tool_calls": [{"id": "call-1", "function": {"name": "replace_lines", "arguments": {
                "start_line": 1,
                "end_line": 1,
                "expected": ["old"],
                "replacement": ["new"],
            }}}]},
            {"tool_calls": []},
        ]
    )
    monkeypatch.setattr(CodeEditor, "_ollama_request", lambda messages, settings, tools: next(responses))

    operations = CodeEditor._run_edit("change it", ["old"], "text", {"provider": "ollama"})

    assert operations == [{
        "tool": "replace_lines",
        "arguments": {
            "start_line": 1,
            "end_line": 1,
            "expected": ["old"],
            "replacement": ["new"],
        },
    }]


def test_filesystem_tools_are_limited_to_current_directory(tmp_path):
    apply_tool([], "create_folder", {"path": "new"}, str(tmp_path))
    apply_tool([], "create_file", {"path": "new/file.txt", "content": "hello"}, str(tmp_path))

    assert (tmp_path / "new" / "file.txt").read_text() == "hello"

    with pytest.raises(ValueError):
        apply_tool([], "create_file", {"path": "../outside.txt", "content": "nope"}, str(tmp_path))
    with pytest.raises(ValueError):
        apply_tool([], "create_file", {"path": str(tmp_path / "absolute.txt"), "content": "nope"}, str(tmp_path))


def test_filesystem_delete_tools(tmp_path):
    folder = tmp_path / "remove"
    folder.mkdir()
    (folder / "file.txt").write_text("content")

    apply_tool([], "delete_file", {"path": "remove/file.txt"}, str(tmp_path))
    with pytest.raises(OSError):
        apply_tool([], "delete_file", {"path": "remove/file.txt"}, str(tmp_path))

    apply_tool([], "delete_folder", {"path": "remove", "recursive": False}, str(tmp_path))
    assert not folder.exists()


def test_filesystem_tools_reject_symlink_escape(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            apply_tool([], "create_file", {"path": "link/file.txt", "content": "nope"}, str(tmp_path))
    finally:
        outside.rmdir()
