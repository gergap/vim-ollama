#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import json
import vim

###############################
# Buffer edit functions
###############################

def GetLine(lineno, buffer = vim.current.buffer):
    return buffer[lineno - 1]

def InsertLine(lineno, content, buffer = vim.current.buffer):
    if lineno == len(buffer) + 1:
        buffer.append(content)
    else:
        buffer[lineno - 1:lineno - 1] = [content]

def ReplaceLine(lineno, content, buffer = vim.current.buffer):
    oldcontent = buffer[lineno - 1]
    buffer[lineno - 1] = content
    return oldcontent

def DeleteLine(lineno, buffer = vim.current.buffer):
    oldcontent = buffer[lineno - 1]
    del buffer[lineno - 1]
    return oldcontent

###############################
# Sign edit functions
###############################
def PlaceSign(lineno, signname, buf):
    sign_id=lineno
    bufno = buf.number
    vim.command(f'sign place {sign_id} line={lineno} name={signname} buffer={bufno}')

def UnplaceSign(lineno, buf):
    sign_id=lineno
    bufno = buf.number
    vim.command(f'sign unplace {sign_id} buffer={bufno}')

def SignClear(buf):
    bufno = buf.number
    vim.command(f'sign unplace * buffer={bufno}')

###############################
# Line property edit functions
###############################

def PropertyTypeAdd(name, options):
    json_options = json.dumps(options)
    vim.command(f'call prop_type_add("{name}", {json_options})')

def HighlightLine(lineno, propname, length, buf):
    bufno = buf.number
    vim.command(f'call prop_add({lineno}, 1, {{"type": "{propname}", "length": {length}, "bufnr": {bufno} }})')

def ShowTextAbove(lineno, propname, text, buf):
    """
    Show text above the given line with specified property type.
    """
    bufno = buf.number
    # Escape for insertion as a literal single quotes string.
    escaped_text = text.replace("'", "''")
    vim.command(
        f"call prop_add({lineno}, 0, {{'type': '{propname}', 'text': '{escaped_text}', 'text_align': 'above', 'bufnr': {bufno}}})"
    )

def ApplyInlineDiff(change, offset, buf):
    lineno = offset + change['line_number']
    status = change['type']
    content = change['line']
    content_len = len(content)

    if status == 'added':
        InsertLine(lineno, content, buf)
        HighlightLine(lineno, 'OllamaDiffAdd', len(content), buf)
        PlaceSign(lineno, 'NewLine', buf)

    elif status == 'changed':
        oldcontent = ReplaceLine(lineno, content, buf)
        # JSON encode old content to avoid escaping issues
        oldcontent = json.dumps(oldcontent)
        HighlightLine(lineno, 'OllamaDiffAdd', len(content), buf)
        ShowTextAbove(lineno, 'OllamaDiffDel', oldcontent, buf)
        PlaceSign(lineno, 'ChangedLine', buf)

    elif status == 'deleted':
        oldcontent = DeleteLine(lineno, buf)
        # JSON encode old content to avoid escaping issues
        oldcontent = json.dumps(oldcontent)
        ShowTextAbove(lineno, 'OllamaDiffDel', oldcontent, buf)
        PlaceSign(lineno, 'DeletedLine', buf)
