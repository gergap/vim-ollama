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

    operations, _messages = CodeEditor._run_edit("change it", ["old"], "text", {"provider": "ollama"})

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


def test_read_file_and_search_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.c").write_text("int main(void) {\n    return 0;\n}\n")
    (source / "notes.txt").write_text("main is documented here\n")

    read_result = apply_tool([], "read_file", {"path": "src/main.c"}, str(tmp_path))
    search_result = apply_tool([], "search_files", {"pattern": r"main", "path": "."}, str(tmp_path))

    assert "int main" in read_result["content"]
    assert "src/main.c:1" in search_result["content"]
    assert "src/notes.txt:1" in search_result["content"]


def test_list_files_supports_non_recursive_and_recursive_modes(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir()
    (tmp_path / "README.md").write_text("readme")
    (source / "main.c").write_text("main")
    (nested / "detail.txt").write_text("detail")

    immediate = apply_tool([], "list_files", {"path": "."}, str(tmp_path))
    recursive = apply_tool([], "list_files", {"path": ".", "recursive": True}, str(tmp_path))

    assert immediate["content"] == "README.md"
    assert recursive["content"].splitlines() == ["README.md", "src/main.c", "src/nested/detail.txt"]


def test_inspection_tools_reject_paths_outside_workspace(tmp_path):
    with pytest.raises(ValueError):
        apply_tool([], "read_file", {"path": "../outside.txt"}, str(tmp_path))
    with pytest.raises(ValueError):
        apply_tool([], "search_files", {"pattern": "x", "path": "../"}, str(tmp_path))
    with pytest.raises(ValueError):
        apply_tool([], "list_files", {"path": "../"}, str(tmp_path))


def test_make_result_is_returned_to_model_without_becoming_buffer_operation(monkeypatch):
    responses = iter([
        {"tool_calls": [{"id": "make-1", "function": {"name": "make", "arguments": {"arguments": ""}}}]},
        {"tool_calls": []},
    ])
    monkeypatch.setattr(CodeEditor, "_ollama_request", lambda messages, settings, tools: next(responses))
    monkeypatch.setattr(CodeEditor, "_request_make", lambda arguments: {
        "ok": False,
        "message": "Vim :make returned diagnostics",
        "diagnostics": [{"filename": "main.cpp", "lnum": 4, "text": "error"}],
    })

    operations, messages = CodeEditor._run_edit("build it", ["code"], "cpp", {"provider": "ollama"})

    assert operations == []
    tool_result = next(message for message in messages if message.get("role") == "tool")
    assert "diagnostics" in tool_result["content"]


@pytest.mark.parametrize("arguments", ["all && touch hacked", "-f Makefile", "all; clean"])
def test_make_rejects_command_arguments(arguments):
    result = CodeEditor._request_make({"arguments": arguments})

    assert result["ok"] is False
    assert "only make target names" in result["error"]
