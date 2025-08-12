" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
" SPDX-CopyrightTdxt: Copyright (C) 2023 GitHub, Inc. - All Rights Reserved
" This file is based on the code of copilot.vim, but was modified to fit
" vim-ollams's needs.
if !exists('g:ollama_logfile')
    let g:ollama_logfile = tempname() .. '-ollama.log'
endif
if !exists('g:ollama_debug')
    let g:ollama_debug = 0
endif
let s:logs = []

function! ollama#logger#PythonLogLevel(level) abort
  " Map plugin's log levels to Python numeric logging levels
  let l:mapping = {
        \ 0: 0,
        \ 1: 40,
        \ 2: 30,
        \ 3: 20,
        \ 4: 10
        \ }

  if has_key(l:mapping, a:level)
    return l:mapping[a:level]
  else
    return 10 " default to debug level
  endif
endfunction

function! ollama#logger#CreateFile() abort
  try
    "echom 'created log file ' .. g:ollama_logfile
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

function! OllamaOpenLogBuffer() abort
  " Check if the buffer already exists
  let l:bufnr = bufnr('ollama:///log')

  if l:bufnr <= 0
    " Create a new buffer with that name and setup BufReadCmd autocommand
    execute 'edit ollama:///log'
  else
    " Just switch to it
    execute 'buffer' l:bufnr
  endif

  " Mark it as special (readonly, unlisted, etc.) if not already
  setlocal buftype=nofile bufhidden=wipe nobuflisted nomodifiable
endfunction

command! OllamaLog call OllamaOpenLogBuffer()

" Fallback function to log to a Vim buffer if writing to file fails.
function! ollama#logger#ToBuffer(lines) abort
  " Evaluate deferred log lines (functions)
  call map(a:lines, { k, L -> type(L) == v:t_func ? call(L, []) : L })

  " Extend log history
  call extend(s:logs, a:lines)

  " Enforce log history limit
  let l:overflow = len(s:logs) - get(g:, 'ollama_log_history', 10000)
  if l:overflow > 0
    call remove(s:logs, 0, l:overflow - 1)
  endif

  " If log buffer is open and loaded, update it
  let l:bufnr = bufnr('ollama:///log')
  if l:bufnr > 0 && bufloaded(l:bufnr)
    call setbufvar(l:bufnr, '&modifiable', 1)
    call setbufline(l:bufnr, 1, s:logs)
    call setbufvar(l:bufnr, '&modifiable', 0)

    " Scroll other windows showing the log buffer
    for l:winid in win_findbuf(l:bufnr)
      if has('nvim') && l:winid != win_getid()
        call nvim_win_set_cursor(l:winid, [len(s:logs), 0])
      endif
    endfor
  endif
endfunction

" Raw logging function used by all log levels
function! ollama#logger#Raw(level, messages) abort
  if a:level > g:ollama_debug
     return
  endif

  " Allow `a:messages` to be a string.  Though all the `ollama#logger#*`
  " functions pass a list in.
  let l:messages = type(a:messages) == v:t_list ? a:messages : [a:messages]

  " `writefile()` will replace all new lines with NUL character, so in order to
  " preserve new lines we need to split all messages on the "\n" character.
  let l:lines = []
  for l:message in l:messages
    if type(l:message) == v:t_list
      let l:lines += l:message
    elseif type(l:message) == v:t_string
      let l:lines += split(l:message, "\n", 1)
    else
      call add(l:lines, string(l:message))
    endif
  endfor

  " Add logging prefix with timestamp and log level
  let l:lines[0] = strftime('[%Y-%m-%d %H:%M:%S] ')
        \ .. get(s:level_prefixes, a:level, '[UNKNOWN] ')
        \ .. get(l:lines, 0, '')

  try
    " write to file
    if filewritable(g:ollama_logfile)
      call writefile(l:lines, g:ollama_logfile, 'a')
      return
    endif

    " of fall back to logging to a Vim buffer
    call ollama#logger#ToBuffer(l:lines)
  catch
    " there is nothing we could do here
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
