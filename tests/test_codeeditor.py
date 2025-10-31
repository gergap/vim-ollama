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

def test_real_code():
    # Add missing include at start of file
    before="""int main(int argc, char *argv[])
{
    printf("Hello, World\\n");
    return 0;
}
"""
    after="""#include <stdio>

int main(int argc, char *argv[])
{
    printf("Hello, World\\n");
    return 0;
}
"""
    # expected diff
    exp_diff="""\
+ #include <stdio>
+ """
    old = before.split("\n")
    new = after.split("\n")
    diff = CodeEditor.compute_diff(old, new)
    groups = CodeEditor.group_diff(diff, starting_line=1)

    # Check for expected diff
    assert len(groups) == 1
    for g in groups:
        assert g['changes']
        cur_diff = "\n".join(g['changes'])
        assert cur_diff == exp_diff

# -----------------------------------------------------------------------------
# Real code examples from external files
# -----------------------------------------------------------------------------
EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "examples")
if os.path.isdir(EXAMPLES_DIR):
    for fname in os.listdir(EXAMPLES_DIR):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(EXAMPLES_DIR, fname)
        with open(path, 'r') as f:
            content = f.read()
        if '---' not in content:
            continue
        before_text, after_text = content.split('---', 1)
        before_lines = before_text.strip().splitlines()
        after_lines = after_text.strip().splitlines()

        # Create pytest case dynamically
        def make_test(before, after, name=fname):
            def _test():
                diff = CodeEditor.compute_diff(before, after)
                buf = FakeBuffer(before.copy())
                FakeVimHelper.reset()
                CodeEditor.apply_change(diff, buf)
                assert buf == after
                groups = CodeEditor.group_diff(diff, starting_line=1)
                assert all('changes' in g and g['changes'] for g in groups)
            _test.__name__ = f"test_example_{name.replace('.', '_')}"
            return _test

        globals()[f"test_example_{fname.replace('.', '_')}"] = make_test(before_lines, after_lines)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
