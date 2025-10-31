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
        self._vars = {"&filetype": "python", "g:ollama_use_inline_diff": "1"}
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
        cls._reset_state()

    @classmethod
    def _reset_state(cls):
        cls.signs = {}
        cls.above_text = {}
        cls.below_text = {}
        cls.highlights = {}

    # ---------------------------------------------------------------------
    # Basic VimHelper methods
    # ---------------------------------------------------------------------
    ###############################
    # Buffer edit functions
    ###############################

    @classmethod
    def GetLine(cls, lineno, buf):
        return buf[lineno]

    @classmethod
    def InsertLine(cls, lineno, content, buf):
        cls.calls.append(("InsertLine", lineno, content))
        buf.insert(lineno, content)

    @classmethod
    def ReplaceLine(cls, lineno, content, buf):
        cls.calls.append(("ReplaceLine", lineno, content))
        oldcontent = buf[lineno]
        buf[lineno] = content
        return oldcontent

    @classmethod
    def DeleteLine(cls, lineno, buf):
        cls.calls.append(("DeleteLine", lineno))
        if 0 <= lineno < len(buf):
            return buf.pop(lineno)

    ###############################
    # Sign edit functions
    ###############################
    @classmethod
    def PlaceSign(cls, lineno, signname, buf):
        cls.signs[lineno] = signname
        cls.calls.append(("PlaceSign", lineno, signname))

    @classmethod
    def UnplaceSign(cls, lineno, buf):
        cls.signs[lineno] = ''
        cls.calls.append(("UnpaceSign", lineno))

    @classmethod
    def SignClear(cls, *a, **kw):
        cls.signs = {}
        cls.calls.append(("SignClear",))

    ###############################
    # Line property edit functions
    ###############################
    @classmethod
    def ShowTextAbove(cls, lineno, propname, text, buf):
        if lineno not in cls.above_text:
            cls.above_text[lineno] = text
        else:
            cls.above_text[lineno] += "\n"+text
        cls.calls.append(("ShowTextAbove", lineno, text))

    @classmethod
    def ShowTextBelow(cls, lineno, propname, text, buf):
        if lineno not in cls.below_text:
            cls.below_text[lineno] = text
        else:
            cls.below_text[lineno] += "\n"+text
        cls.calls.append(("ShowTextBelow", lineno, text))

    @classmethod
    def HighlightLine(cls, lineno, propname, length, buf):
        cls.highlights[lineno] = propname
        cls.calls.append(("HighlightLine", lineno, length))

    # ---------------------------------------------------------------------
    # Render functions
    # ---------------------------------------------------------------------
    @classmethod
    def render_state(cls, buf):
        """
        Render buffer as simple text with markers:
        D = deleted line above this line
        A = added line
        """
        out = []
        for i, line in enumerate(buf, 0):
            marker = ' '
            if i in cls.signs:
                if cls.signs[i] == 'DeletedLine': marker = '-'
                elif cls.signs[i] == 'NewLine': marker = '+'
                elif cls.signs[i] == 'ChangedLine': marker = '~'
            if i in cls.above_text:
                out.append(f'A {i} {cls.above_text[i]}')
            out.append(f'{marker} {i} {line}')
            if i in cls.below_text:
                out.append(f'B {i} {cls.below_text[i]}')
        return '\n'.join(out)

    @classmethod
    def render_html(cls, buf, title="Buffer Render"):
        """
        Render buffer as HTML with line numbers, added lines green, deleted lines red.
        """
        html = ['<html><head><meta charset="utf-8"><title>{}</title>'.format(title),
                '<style>',
                '.line { font-family: monospace; white-space: pre; }',
                '.added { background-color: #d0f0c0; }',
                '.deleted { background-color: #f0d0d0; }',
                '.changed { background-color: #f0f0d0; }',
                '.normal {}',
                '</style></head><body>']

        for i, line in enumerate(buf, 0):
            cls_sign = cls.signs.get(i, None)
            cls_above = cls.above_text.get(i, '')
            cls_below = cls.below_text.get(i, '')

            # Show above text
            if cls_above:
                html.append('<div class="line deleted">{}</div>'.format(cls_above))

            # Show line
            css_class = 'normal'
            if cls_sign == 'DeletedLine': css_class = 'deleted'
            elif cls_sign == 'NewLine': css_class = 'added'
            elif cls_sign == 'ChangedLine': css_class = 'changed'

            html.append('<div class="line {}">{:3d} {}</div>'.format(css_class, i, line))

            # Show below text
            if cls_below:
                html.append('<div class="line deleted">{}</div>'.format(cls_below))

        html.append('</body></html>')
        return '\n'.join(html)

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
                CodeEditor.apply_diff(diff, buf)
                assert buf == after
                groups = CodeEditor.group_diff(diff, starting_line=1)
                assert all('changes' in g and g['changes'] for g in groups)
                text = FakeVimHelper.render_state(buf)
                # create output dir
                os.makedirs("output", exist_ok=True)
                with open(f"output/test_{name}.state", 'w') as f:
                    f.write(text)
                html = FakeVimHelper.render_html(buf)
                # save html to file
                with open(f"output/test_{name}.html", 'w') as f:
                    f.write(html)

            _test.__name__ = f"test_example_{name.replace('.', '_')}"
            return _test

        globals()[f"test_example_{fname.replace('.', '_')}"] = make_test(before_lines, after_lines)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
