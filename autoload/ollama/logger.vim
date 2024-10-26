" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
" SPDX-CopyrightTdxt: Copyright (C) 2023 GitHub, Inc. - All Rights Reserved
" This file is based on the code of copilot.vim, but was modified to fit
" vim-ollams's needs.
if !exists('g:ollama_logfile')
    let g:ollama_logfile = tempname() . '-ollama.log'
endif
if !exists('g:ollama_debug')
    let g:ollama_debug = 0
endif
let s:logs = []

function! ollama#logger#CreateFile() abort
  try
    "echom 'created log file '.g:ollama_logfile
    call writefile([], g:ollama_logfile)
  catch
  endtry
endfunction

function! ollama#logger#BufReadCmd() abort
  try
    setlocal modifiable noreadonly
    call deletebufline('', 1, '$')
    if !empty(s:logs)
      call setline(1, s:logs)
    endif
  finally
    setlocal buftype=nofile bufhidden=wipe nobuflisted nomodified nomodifiable
  endtry
endfunction

let s:level_prefixes = ['', '[ERROR] ', '[WARN] ', '[INFO] ', '[DEBUG] ', '[DEBUG] ']

function! ollama#logger#Raw(level, message) abort
  if a:level > g:ollama_debug
     return
  endif
  let lines = type(a:message) == v:t_list ? copy(a:message) : split(a:message, "\n", 1)
  let lines[0] = strftime('[%Y-%m-%d %H:%M:%S] ') . get(s:level_prefixes, a:level, '[UNKNOWN] ') . get(lines, 0, '')
  try
    if filewritable(g:ollama_logfile)
      call writefile(lines, g:ollama_logfile, 'a')
      return
    endif
    call map(lines, { k, L -> type(L) == v:t_func ? call(L, []) : L })
    call extend(s:logs, lines)
    let overflow = len(s:logs) - get(g:, 'ollama_log_history', 10000)
    if overflow > 0
      call remove(s:logs, 0, overflow - 1)
    endif
    let bufnr = bufnr('ollama:///log')
    if bufnr > 0 && bufloaded(bufnr)
      call setbufvar(bufnr, '&modifiable', 1)
      call setbufline(bufnr, 1, s:logs)
      call setbufvar(bufnr, '&modifiable', 0)
      for winid in win_findbuf(bufnr)
        if has('nvim') && winid != win_getid()
          call nvim_win_set_cursor(winid, [len(s:logs), 0])
        endif
      endfor
    endif
  catch
  endtry
endfunction

function! ollama#logger#Debug(...) abort
  if empty(get(g:, 'ollama_debug'))
    return
  endif
  call ollama#logger#Raw(4, a:000)
endfunction

function! ollama#logger#Info(...) abort
  call ollama#logger#Raw(3, a:000)
endfunction

function! ollama#logger#Warn(...) abort
  call ollama#logger#Raw(2, a:000)
endfunction

function! ollama#logger#Error(...) abort
  call ollama#logger#Raw(1, a:000)
endfunction

function! ollama#logger#Bare(...) abort
  call ollama#logger#Raw(0, a:000)
endfunction

if !exists('s:log_open')
    " Create file if it does not exist yet
    call ollama#logger#CreateFile()
    let s:log_open = 1
endif
