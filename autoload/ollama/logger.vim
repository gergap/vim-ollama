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

let s:level_prefixes =
      \ ['', '[ERROR] ', '[WARN] ', '[INFO] ', '[DEBUG] ', '[DEBUG] ']

" Raw logging function used by all log levels
function! s:LogMessages(level, messages) abort
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
    elseif type(l:message) == v:t_func
      " Evaluate deferred log lines.
      " TODO When does this happen?
      call add(l:lines, call(l:message, []))
    else
      call add(l:lines, string(l:message))
    endif
  endfor

  " Add logging prefix with timestamp and log level
  let l:lines[0] = strftime('[%Y-%m-%d %H:%M:%S] ')
        \ .. get(s:level_prefixes, a:level, '[UNKNOWN] ')
        \ .. get(l:lines, 0, '')

  try
    if filewritable(g:ollama_logfile)
      call writefile(l:lines, g:ollama_logfile, 'a')
    endif
  catch
    " there is nothing we could do here
  endtry

  let l:overflow = s:UpdateInMemoryLog(l:lines)
  call s:UpdateLogBuffer(l:overflow, len(l:lines))
endfunction

function! ollama#logger#Debug(...) abort
  if empty(get(g:, 'ollama_debug'))
    return
  endif
  call s:LogMessages(4, a:000)
endfunction

function! ollama#logger#Info(...) abort
  call s:LogMessages(3, a:000)
endfunction

function! ollama#logger#Warn(...) abort
  call s:LogMessages(2, a:000)
endfunction

function! ollama#logger#Error(...) abort
  call s:LogMessages(1, a:000)
endfunction

function! ollama#logger#Bare(...) abort
  call s:LogMessages(0, a:000)
endfunction

function! s:SetLogLevel(level)
  if a:level =~# '^[0-4]$'
    let g:ollama_debug = a:level + 0
    return v:true
  endif

  let l:level_names = ['bare', 'error', 'warn', 'info', 'debug']

  if a:level ==? 'bare'
    let g:ollama_debug = 0
    return v:true
  endif

  if a:level ==? 'error'
    let g:ollama_debug = 1
    return v:true
  endif

  if a:level =~? '^warn\%[ing]$'
    let g:ollama_debug = 2
    return v:true
  endif

  if a:level ==? 'info'
    let g:ollama_debug = 3
    return v:true
  endif

  if a:level ==? 'debug'
    let g:ollama_debug = 4
    return v:true
  endif

  echoerr "ERROR: Unknown debug level name:" a:level
  return v:false
endfunction

function! s:UpdateInMemoryLog(lines)
  let overflow =
        \ len(s:logs) + len(a:lines) - get(g:, 'ollama_log_history', 10000)
  if overflow > 0
    call remove(s:logs, 0, overflow - 1)
  else
    let overflow = 0
  endif

  call extend(s:logs, a:lines)

  return overflow
endfunction

function! s:UpdateLogBuffer(overflow, new_lines)
  let bufnr = bufnr('ollama:///log')
  if bufnr == -1 || !bufloaded(bufnr)
    return
  endif

  " We are going to preserve cursor position in all windows that show the log
  " buffer.  As a special case, if the cursor is on the last line, it will keep
  " moving along with the log, staying in the last line.
  "
  " We do this for all windows, regardless of if they are in the current tab or
  " not.
  let current_winid = win_getid()
  let new_cursor_positions = []
  for winid in win_findbuf(bufnr)
    let [_, lnum, _, _, _] = getcurpos(winid)
    " Was cursor was on the last line before a:new_lines were added.
    if lnum == len(s:logs) + a:overflow - a:new_lines
      let lnum = lnum + a:new_lines - a:overflow
    else
      let lnum = max([1, lnum - a:overflow])
    endif
    call add(new_cursor_positions, (winid, lnum))
  endfor

  call setbufvar(bufnr, '&modifiable', 1)
  " Optimize the buffer update a bit.
  " Rewriting the whole buffer content is slow.  But even writing just the
  " difference can also be slow, if it happens on each key stroke.
  " Further optimization would require an async update?  Which is probably too
  " much work.
  if a:overflow > 0
    call deletebufline(bufnr, 1, a:overflow)
  endif
  if a:new_lines > 0
    call appendbufline(bufnr, '$', s:logs[-a:new_lines:])
  endif
  call setbufvar(bufnr, '&modifiable', 0)
  call setbufvar(bufnr, '&modified', 0)

  for [winid, lnum] in new_cursor_positions
    call win_gotoid(winid)
    call winrestview({ 'lnum': lnum })
  endfor

  call win_gotoid(current_winid)
endfunction

function! ollama#logger#ShowLogBuffer(mods, ...) abort
  if len(a:0) > 1
    echoerr "ERROR: OllamaDebug accepts a maximum of 1 optional argument"
    return
  endif

  let l:bufnr = bufnr('ollama:///log')

  " Set the log level, or process the "stop" command.
  if len(a:0) == 1
    let l:level = a:1
    if l:level =~? 'stop'
      if l:bufnr != -1
        execute l:bufnr .. 'bwipe'
      endif
      let g:ollama_debug = 1
      return
    endif

    if !s:SetLogLevel(l:level)
      return
    endif
  endif

  " If the buffer is already visible in the current tab, then we are done.
  if l:bufnr != -1 && bufloaded(l:bufnr)
    for l:winnr in range(1, winnr('$'))
      if winbufnr(l:winnr) == l:bufnr
        return
      endif
    endfor
  endif

  " Create new window and show the log buffer in there.

  let current_win = winnr()
  silent execute a:mods 'new'

  if l:bufnr == -1 || !bufloaded(l:bufnr)
      setlocal buftype=nofile
      setlocal bufhidden=hide
      setlocal nobuflisted
      setlocal noswapfile
      silent 0file
      silent keepalt file 'ollama:///log'
      set filetype=log
      let l:bufnr = bufnr('ollama:///log')
      call setbufline(l:bufnr, 1, s:logs)
      setlocal nomodified nomodifiable

      " Move cursor to the last line, which would cause the log to keep showing
      " the last line.
      call setpos('.', [0, len(s:logs), 1, 0, 1])
  else
      " Show the existing buffer.
      execute 'buffer' l:bufnr
  endif

  " Keep the focused window as is, as it is unlikely that the user wants to
  " focus the log?
  execute current_win .. 'wincmd w'
endfunction

if !exists('s:log_open')
    " Create file if it does not exist yet
    call ollama#logger#CreateFile()
    let s:log_open = 1
endif
