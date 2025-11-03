#!/usr/bin/env python3
import sys, os, types, pytest

g_log = None

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


    @classmethod
    def SetLogger(cls, log):
        global g_log
        g_log = log

    @classmethod
    def debug_log(cls, msg):
        if g_log == None:
            return
        g_log.debug(msg)

    # ---------------------------------------------------------------------
    # Basic VimHelper methods
    # ---------------------------------------------------------------------
    ###############################
    # Buffer edit functions
    ###############################

    @classmethod
    def GetLine(cls, lineno, buf):
        return buf[lineno-1]

    @classmethod
    def InsertLine(cls, lineno, content, buf):
        cls.calls.append(("InsertLine", lineno, content))
        buf.insert(lineno-1, content)

    @classmethod
    def ReplaceLine(cls, lineno, content, buf):
        cls.calls.append(("ReplaceLine", lineno, content))
        oldcontent = buf[lineno-1]
        buf[lineno-1] = content
        return oldcontent

    @classmethod
    def DeleteLine(cls, lineno, buf):
        cls.calls.append(("DeleteLine", lineno))
        if 1 <= lineno <= len(buf):
            return buf.pop(lineno-1)

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
    def HighlightLine(cls, lineno, propId, propname, length, buf):
        cls.highlights[lineno] = propname
        cls.calls.append(("HighlightLine", lineno, length))

    @classmethod
    def ClearHighlights(cls, propId, propname, buf):
        pass

    @classmethod
    def ClearAllHighlights(cls, propname, buf):
        pass

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
import vim

# initialize logger before using it
CodeEditor.CreateLogger()
CodeEditor.SetLogLevel(10)

# -----------------------------------------------------------------------------
# Test cases for CodeEditor diff logic
# -----------------------------------------------------------------------------

def test_no_changes():
    old = ["a", "b", "c"]
    new = ["a", "b", "c"]
    diff = CodeEditor.compute_diff(old, new)
    assert diff == [] or all(line.startswith(' ') for line in diff)
    buf = FakeBuffer(old.copy())
    CodeEditor.apply_change(diff, buf, 1)
    assert buf == old

def test_single_line_addition():
    diff = ["+ c"]
    buf = FakeBuffer(["a", "b"])
    FakeVimHelper.reset()
    # apply at start of buffer
    CodeEditor.apply_change(diff, buf, 1)
    assert buf == ["c", "a", "b"]
    assert any(call[0] == "InsertLine" for call in FakeVimHelper.calls)
    # apply in the middle
    buf = FakeBuffer(["a", "b"])
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 2)
    assert buf == ["a", "c", "b"]
    assert any(call[0] == "InsertLine" for call in FakeVimHelper.calls)
    # apply at end of buffer
    buf = FakeBuffer(["a", "b"])
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 3)
    assert buf == ["a", "b", "c"]
    assert any(call[0] == "InsertLine" for call in FakeVimHelper.calls)
    # apply on empty buffer
    buf = FakeBuffer([])
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 3)
    assert buf == ["c"]
    assert any(call[0] == "InsertLine" for call in FakeVimHelper.calls)

def test_single_line_deletion():
    # delete first line
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["- a"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 1)
    assert buf == ["b", "c"]
    assert any(call[0] == "DeleteLine" for call in FakeVimHelper.calls)
    # delete middle line
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["- b"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 2)
    assert buf == ["a", "c"]
    assert any(call[0] == "DeleteLine" for call in FakeVimHelper.calls)
    # delete middle line with unchanged context
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["  a", "- b", "  c"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 1)
    assert buf == ["a", "c"]
    assert any(call[0] == "DeleteLine" for call in FakeVimHelper.calls)
    # delete last line
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["- c"]
    FakeVimHelper.reset()
    CodeEditor.apply_change(diff, buf, 3)
    assert buf == ["a", "b"]
    assert any(call[0] == "DeleteLine" for call in FakeVimHelper.calls)
    # test not matching diff
    buf = FakeBuffer(["a", "b", "c"])
    diff = ["- d"]
    FakeVimHelper.reset()
    try:
        CodeEditor.apply_change(diff, buf, 3)
    except Exception as e:
        assert str(e).startswith("error: diff does not apply at deleted line 3:")

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

def test_group_diff_line_numbers():
    """ This test computes grouped diffs and checks the expected line numbers of the changes """
    # Insert two groups
    diff ="""
  line1
+ foo
+ bar
  line2
+ bla
  line4
    """
    diff = diff.strip().splitlines()
    groups = CodeEditor.group_diff(diff, starting_line=1)
    assert len(groups) == 2
    groups[0].start_line == 2
    groups[0].end_line == 3
    groups[1].start_line == 5
    groups[1].end_line == 5
    # Delete two groups
    diff ="""
  line1
- line2
  line3
- line4
- line5
    """
    diff = diff.strip().splitlines()
    groups = CodeEditor.group_diff(diff, starting_line=1)
    assert len(groups) == 2
    groups[0].start_line == 2
    groups[0].end_line == 2
    groups[1].start_line == 3
    groups[1].end_line == 3
    # Insert and delete
    diff ="""
  line1
+ foo
  line2
- line3
- line4
  line5
    """
    diff = diff.strip().splitlines()
    groups = CodeEditor.group_diff(diff, starting_line=1)
    assert len(groups) == 2
    groups[0].start_line == 2
    groups[0].end_line == 2
    groups[1].start_line == 4
    groups[1].end_line == 4
    # Delete and insert
    diff ="""
  line1
- line2
  line3
  line4
+ foo
  line5
    """
    diff = diff.strip().splitlines()
    groups = CodeEditor.group_diff(diff, starting_line=1)
    assert len(groups) == 2
    groups[0].start_line == 2
    groups[0].end_line == 2
    groups[1].start_line == 4
    groups[1].end_line == 4
    # Change lines
    diff ="""
  line1
- line2
+ foo
  line3
- line4
+ foo
  line5
    """
    diff = diff.strip().splitlines()
    groups = CodeEditor.group_diff(diff, starting_line=1)
    assert len(groups) == 2
    groups[0].start_line == 2
    groups[0].end_line == 2
    groups[1].start_line == 4
    groups[1].end_line == 4

# When computing diff groups each group contains a start- and end_line number of the change.
# These numbers are the numbers after the changes are applied.
# When rejecting changes these numbers must be corrected.
# When using RejectChangeLine this implicitly also tests index based RejectChange,
# because the *Line functions are just wrappers.
def test_apply_and_reject_forward():
    # create a diff with 3 inserts of different lengths
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "1", "b", "2", "3", "c", "d", "4", "5", "6", "e", "f"]

    # prepare fake buffer
    buf = FakeBuffer(old.copy())
    FakeVimHelper.reset()

    # compute the diff
    diff = CodeEditor.compute_diff(old, new)
    # compute groups
    groups = CodeEditor.group_diff(diff, starting_line=1)
    # we need to save this in CodeEditor to make things working
    CodeEditor.g_groups = groups
    vim.current.buffer = buf
    # apply as inline diff
    CodeEditor.apply_diff_groups(groups, buf)

    # Check for expected diff
    assert len(groups) == 3
    # reject first change on line 2
    CodeEditor.RejectChangeLine(2)
    # reject second change on line 4 -> 3 after previous reject
    CodeEditor.RejectChangeLine(3)
    # reject third change on line 8 -> 5 after previous rejects
    CodeEditor.RejectChangeLine(5)

    assert buf == old

# When rejecting in reverse order it's actually easier because no line number correction is required
def test_apply_and_reject_reverse():
    # create a diff with 3 inserts of different lengths
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "1", "b", "2", "3", "c", "d", "4", "5", "6", "e", "f"]

    # prepare fake buffer
    buf = FakeBuffer(old.copy())
    FakeVimHelper.reset()

    # compute the diff
    diff = CodeEditor.compute_diff(old, new)
    # compute groups
    groups = CodeEditor.group_diff(diff, starting_line=1)
    # we need to save this in CodeEditor to make things working
    CodeEditor.g_groups = groups
    vim.current.buffer = buf
    # apply as inline diff
    CodeEditor.apply_diff_groups(groups, buf)

    # Check for expected diff
    assert len(groups) == 3
    # reject third change on line 8
    CodeEditor.RejectChangeLine(8)
    # reject second change on line 4
    CodeEditor.RejectChangeLine(4)
    # reject first change on line 2
    CodeEditor.RejectChangeLine(2)

    assert buf == old

# Just in case. If the above two tests works,this should work too.
def test_apply_and_reject_mixed_order():
    # create a diff with 3 inserts of different lengths
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "1", "b", "2", "3", "c", "d", "4", "5", "6", "e", "f"]

    # prepare fake buffer
    buf = FakeBuffer(old.copy())
    FakeVimHelper.reset()

    # compute the diff
    diff = CodeEditor.compute_diff(old, new)
    # compute groups
    groups = CodeEditor.group_diff(diff, starting_line=1)
    # we need to save this in CodeEditor to make things working
    CodeEditor.g_groups = groups
    vim.current.buffer = buf
    # apply as inline diff
    CodeEditor.apply_diff_groups(groups, buf)

    # Check for expected diff
    assert len(groups) == 3
    # reject second change on line 4
    CodeEditor.RejectChangeLine(4)
    # reject third change on line 8 -> 6
    CodeEditor.RejectChangeLine(6)
    # reject first change on line 2
    CodeEditor.RejectChangeLine(2)

    assert buf == old

# Just in case. If the above two tests works,this should work too.
def test_apply_and_reject_different_types():
    # create a diff with inserts, changes and deletetions
    # insert 1
    # change cd -> CD
    # delete f, g, h
    old = ["a", "b", "c", "d", "e", "f", "g", "h"]
    new = ["a", "1", "b", "C", "D", "e"]

    # prepare fake buffer
    buf = FakeBuffer(old.copy())
    FakeVimHelper.reset()

    # compute the diff
    diff = CodeEditor.compute_diff(old, new)
    # compute groups
    groups = CodeEditor.group_diff(diff, starting_line=1)
    # we need to save this in CodeEditor to make things working
    CodeEditor.g_groups = groups
    vim.current.buffer = buf
    # apply as inline diff
    CodeEditor.apply_diff_groups(groups, buf)

    # Check for expected diff
    assert len(groups) == 3
    # reject first change on line 2
    CodeEditor.RejectChangeLine(2)
    # reject second change on line 4 -> 3 (-1 due to reject insert 1)
    CodeEditor.RejectChangeLine(3) # rejecting changes does not modify the line numbers
    # reject third change on line 7 -> 6 (due to -1 of 1st change)
    CodeEditor.RejectChangeLine(6)

    assert buf == old

def test_grouping_diff_only_inserts():
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]
    diff = CodeEditor.compute_diff(old, new)
    groups = CodeEditor.group_diff(diff, starting_line=1)

    # Expect one group with inserts
    assert len(groups) == 1
    assert groups[0].changes

def test_grouping_diff_only_deletes():
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "b", "c"]
    diff = CodeEditor.compute_diff(old, new)
    groups = CodeEditor.group_diff(diff, starting_line=1)

    # Expect one group with deletes
    assert len(groups) == 1
    assert groups[0].changes

def test_multiple_groups_in_diff():
    old = ["a", "b", "c", "d", "e", "f"]
    new = ["a", "x", "c", "d", "y", "f"]
    diff = CodeEditor.compute_diff(old, new)
    groups = CodeEditor.group_diff(diff, starting_line=1)

    # Expect two groups with inserts
    assert len(groups) == 2
    for g in groups:
        assert g.changes

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
        assert g.changes
        cur_diff = "\n".join(g.changes)
        assert cur_diff == exp_diff

#def test_apply_accept_and_reject():
#    # buffer state before change
#    before="""line1
#line2
#line3
#line4
#line5
#line6
#"""
#    # AI suggestions
#    after="""line1
#line2 foo
#line3
#line4 bar
#line5
#line6
#"""
#    # Expected result when accepting 1st change and rejecting 2nd change
#    exp_result="""line1
#line2 foo
#line3
#line4
#line5
#line6
#"""
#    old = before.strip().splitlines()
#    new = after.strip().splitlines()
#    exp = exp_result.strip().splitlines()
#    # prepare fake buffer
#    buf = FakeBuffer(old.copy())
#    FakeVimHelper.reset()
#
#    # compute the diff
#    diff = CodeEditor.compute_diff(old, new)
#    # apply as inline diff
#    CodeEditor.apply_diff(diff, buf)
#    # compute groups
#    groups = CodeEditor.group_diff(diff, starting_line=1)
#    # we need to save this in CodeEditor to make things working
#    CodeEditor.g_groups = groups
#    vim.current.buffer = buf
#
#    # Check for expected diff
#    assert len(groups) == 2
#    # accept first change on line 2
#    CodeEditor.AcceptChangeLine(2)
#    # reject second change on line 4
#    CodeEditor.RejectChangeLine(4)
#
#    # create output dir
#    os.makedirs("output", exist_ok=True)
#    # debug output
#    text = FakeVimHelper.render_state(buf)
#    with open(f"output/test_accept_and_reject.state", 'w') as f:
#        f.write(text)
#    html = FakeVimHelper.render_html(buf)
#    # save html to file
#    with open(f"output/test_accept_and_reject.html", 'w') as f:
#        f.write(html)
#
#    assert buf == exp

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
                groups = CodeEditor.group_diff(diff, starting_line=1)
                assert len(groups) > 0
                buf = FakeBuffer(before.copy())
                FakeVimHelper.reset()
                CodeEditor.apply_diff_groups(groups, buf)
                assert buf == after
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
