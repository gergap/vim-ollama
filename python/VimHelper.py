#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
import json
import vim

g_log = None

def SetLogger(log):
    global g_log
    g_log = log

def debug_log(msg):
    if g_log == None:
        return
    g_log.debug(msg)

###############################
# Buffer edit functions
###############################

def GetLine(lineno, buffer = vim.current.buffer):
    return buffer[lineno - 1]

def InsertLine(lineno, content, buffer = vim.current.buffer):
    debug_log(f'InsertLine {lineno}: "{content}"')
    # Clamp lineno in valid range
    if lineno < 1:
        lineno = 1
    elif lineno > len(buffer) + 1:
        lineno = len(buffer) + 1

     # Vim buffer behaves oddly with slicing at end — use append explicitly
    if lineno == len(buffer) + 1:
        buffer.append(content)
    else:
        buffer[lineno - 1:lineno - 1] = [content]

def ReplaceLine(lineno, content, buffer = vim.current.buffer):
    debug_log(f'ReplaceLine {lineno}: "{content}"')
    oldcontent = buffer[lineno - 1]
    buffer[lineno - 1] = content
    return oldcontent

def DeleteLine(lineno, buffer = vim.current.buffer):
    debug_log(f'DeleteLine {lineno}')
    oldcontent = buffer[lineno - 1]
    del buffer[lineno - 1]
    return oldcontent

###############################
# Line property edit functions
###############################

def PropertyTypeAdd(name, options):
    json_options = json.dumps(options)
    vim.command(f'call prop_type_add("{name}", {json_options})')

def HighlightLine(lineno, propId, propname, length, buf):
    debug_log(f'HighlightLine {lineno}, {propId}, {propname}')
    bufno = buf.number
    vim.command(f'call prop_add({lineno}, 1, {{"type": "{propname}", "id": {propId}, "length": {length}, "bufnr": {bufno} }})')

def ClearHighlights(propId, propname, buf):
    debug_log(f'ClearHighlights: prop_remove {propname}, {propId}')
    bufno = buf.number
    # remove all properties of given type AND id
    vim.command(f'call prop_remove({{"type": "{propname}", "id": {propId}, "bufnr": {bufno}, "both": 1 }})')

def ClearAllHighlights(propname, buf):
    debug_log(f'ClearAllHighlights: prop_remove {propname}')
    bufno = buf.number
    # remove all properties of given type
    vim.command(f'call prop_remove({{"type": "{propname}", "bufnr": {bufno}}})')

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

def ShowTextBelow(lineno, propname, text, buf):
    """
    Show text below the given line with specified property type.
    """
    bufno = buf.number
    # Escape for insertion as a literal single quotes string.
    escaped_text = text.replace("'", "''")
    vim.command(
        f"call prop_add({lineno}, 0, {{'type': '{propname}', 'text': '{escaped_text}', 'text_align': 'below', 'bufnr': {bufno}}})"
    )

