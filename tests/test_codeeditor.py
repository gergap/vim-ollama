#!/usr/bin/env python3
import sys, os, types, pytest

# -----------------------------------------------------------------------------
# Fake vim + VimHelper setup
# -----------------------------------------------------------------------------
class FakeBuffer(list):
    def __init__(self, lines=None):
        super().__init__(lines or [])
        self.number = 1

class FakeVim:
    def __init__(self):
        self.current = types.SimpleNamespace(buffer=FakeBuffer())
        self._vars = {"&filetype": "python", "g:ollama_use_inline_diff": "0"}
        self.commands = []

    def eval(self, expr):
        return self._vars.get(expr, "")

    def command(self, cmd):
        self.commands.append(cmd)

class FakeVimHelper:
    calls = []

    @classmethod
    def reset(cls):
        cls.calls.clear()

    @classmethod
    def InsertLine(cls, lineno, content, buf):
        cls.calls.append(("InsertLine", lineno, content))
        buf.insert(lineno, content)

    @classmethod
    def DeleteLine(cls, lineno, buf):
        cls.calls.append(("DeleteLine", lineno))
        if 0 <= lineno < len(buf):
            return buf.pop(lineno)

    @classmethod
    def GetLine(cls, lineno, buf):
        return buf[lineno]

    @classmethod
    def SignClear(cls, *a, **kw):
        cls.calls.append(("SignClear",))

# -----------------------------------------------------------------------------
# Prepare sys.modules for CodeEditor import
# -----------------------------------------------------------------------------

sys.modules['vim'] = FakeVim()
sys.modules['VimHelper'] = FakeVimHelper

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))
import CodeEditor

# -----------------------------------------------------------------------------
# Test cases for CodeEditor diff logic
# -----------------------------------------------------------------------------

def test_no_changes():
    old = ["a", "b", "c"]
    new = ["a", "b", "c"]
    diff = CodeEditor.compute_diff(old, new)
    assert diff == [] or all(line.startswith(' ') for line in diff)
    buf = FakeBuffer(old.copy())
    CodeEditor.apply_change(diff, buf)
    assert buf == old

def test_single_line_addition():
    buf = FakeBuffer(["a", "b"])
    diff = ["  a", "+ c", "  b"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf)
    assert "c" in buf
    assert any(call[0] == "InsertLine" for call in FakeVimHelper.calls)

def test_single_line_deletion():
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["  a", "- b", "  c"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf)
    assert buf == ["a", "c"]
    assert any(call[0] == "DeleteLine" for call in FakeVimHelper.calls)

def test_single_line_change():
    buf = FakeBuffer(["x", "y", "z"])
    diff = ["  x", "- y", "+ Y", "  z"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf)
    assert buf == ["x", "Y", "z"]

def test_change_first_line():
    buf = FakeBuffer(["old", "b", "c"])
    diff = ["- old", "+ new", "  b", "  c"]
    CodeEditor.apply_change(diff, buf)
    assert buf[0] == "new"

def test_change_last_line():
    buf = FakeBuffer(["a", "b", "end"])
    diff = ["  a", "  b", "- end", "+ END"]
    CodeEditor.apply_change(diff, buf)
    assert buf[-1] == "END"

def test_multiple_groups_in_diff():
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "x", "c", "d", "y", "f"]
    diff = CodeEditor.compute_diff(old, new)
    groups = CodeEditor.group_diff(diff, starting_line=1)

    # Expect at least two groups separated by unchanged lines
    assert len(groups) >= 2
    for g in groups:
        assert 'changes' in g and g['changes']

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
