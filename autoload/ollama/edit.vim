" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>

let s:popup = 0
let s:timer = 0
let s:bufnr = -1
let s:source_winid = -1
let s:conversation_bufnr = -1
let s:conversation_winid = -1
let s:firstline = 0
let s:lastline = 0
let s:session_range_mode = v:true
let s:session_explain_mode = v:false
let s:sandbox_session_approvals = {}
let g:edit_in_progress = 0

if empty(sign_getdefined('OllamaEditChange'))
    call sign_define('OllamaEditChange', {'text': '>', 'texthl': 'DiffChange'})
endif

function! s:CloseProgress() abort
    if s:timer != 0
        call timer_stop(s:timer)
        let s:timer = 0
    endif
endfunction

function! s:OpenConversation(request) abort
    let s:source_winid = win_getid()
    botright new
    setlocal buftype=prompt bufhidden=hide noswapfile
    setlocal filetype=markdown
    " avoid showing _ as errors in Markdown
    silent! syntax clear markdownError
    setlocal wrap
    setlocal modifiable
    setlocal foldmethod=expr
    setlocal foldexpr=ollama#edit#ConversationFold(v:lnum)
    setlocal foldtext=ollama#edit#ConversationFoldText()
    setlocal foldlevel=0
    let b:ollama_edit_conversation = v:true
    let b:ollama_stick_to_bottom = v:true
    augroup OllamaEditConversation
        autocmd! * <buffer>
        autocmd BufWinEnter,BufWritePost,InsertEnter,InsertLeave,CursorHold,CursorHoldI <buffer>
                    \ call ollama#edit#SetupConversationFolding()
        autocmd CursorMoved,CursorMovedI <buffer> call ollama#edit#UpdateStickScroll()
        autocmd WinLeave <buffer> let b:ollama_stick_to_bottom = v:true
    augroup END
    let s:conversation_bufnr = bufnr('%')
    let s:conversation_winid = win_getid()
    call setline(1, ['OllamaEdit', '=========', ''] + split('Request: ' .. a:request, "\n", v:true) + [''])
    call prompt_setcallback(s:conversation_bufnr, function('ollama#edit#PromptEntered'))
    call prompt_setprompt(s:conversation_bufnr, '>>> ')
endfunction

function! ollama#edit#UpdateStickScroll() abort
    if get(b:, 'ollama_internal_update', v:false)
        return
    endif
    let b:ollama_stick_to_bottom = line('.') == line('$')
endfunction

function! ollama#edit#ConversationFoldText() abort
    let l:start = getline(v:foldstart)
    let l:label = substitute(l:start, '^#StartDiagnostic\s*', '', '')
    let l:end = getline(v:foldend)
    let l:status = substitute(l:end, '^#EndDiagnostic\s*', '', '')
    if empty(l:label)
        let l:label = 'diagnostic'
    endif
    let l:line_count = v:foldend - v:foldstart + 1
    let l:prefix = '+-- ' .. l:line_count .. ' lines: '
    if empty(l:status)
        return l:prefix .. l:label
    endif
    return l:prefix .. l:label .. '  ' .. l:status
endfunction

function! ollama#edit#ConversationFold(lnum) abort
    let l:line = getline(a:lnum)
    if l:line =~# '^#StartDiagnostic\>'
        return 'a1'
    endif
    if l:line =~# '^#EndDiagnostic\>'
        return 's1'
    endif
    let l:index = a:lnum - 1
    while l:index >= 1
        let l:previous = getline(l:index)
        if l:previous =~# '^#EndDiagnostic\>'
            return 0
        endif
        if l:previous =~# '^#StartDiagnostic\>'
            return '='
        endif
        let l:index -= 1
    endwhile
    return 0
endfunction

function! ollama#edit#SetupConversationFolding() abort
    if get(b:, 'ollama_edit_conversation', v:false)
        if &l:foldmethod !=# 'expr'
            setlocal foldmethod=expr
        endif
        if &l:foldexpr !=# 'ollama#edit#ConversationFold(v:lnum)'
            setlocal foldexpr=ollama#edit#ConversationFold(v:lnum)
        endif
    endif
endfunction

function! s:PrepareConversation(request) abort
    if !bufexists(s:conversation_bufnr) || !win_gotoid(s:conversation_winid)
        call s:OpenConversation(a:request)
        return
    endif
    let l:line_count = getbufinfo(s:conversation_bufnr)[0].linecount
    call appendbufline(s:conversation_bufnr, l:line_count - 1,
                \ [''] + split('Follow-up: ' .. a:request, "\n", v:true) + [''])
    if getbufvar(s:conversation_bufnr, 'ollama_stick_to_bottom', v:true)
        call win_execute(s:conversation_winid, 'silent! normal! G')
    endif
endfunction

function! ollama#edit#AppendProgress(text) abort
    if bufexists(s:conversation_bufnr)
        let l:stick = getbufvar(s:conversation_bufnr, 'ollama_stick_to_bottom', v:true)
        let l:internal_update = getbufvar(s:conversation_bufnr, 'ollama_internal_update', v:false)
        call setbufvar(s:conversation_bufnr, 'ollama_internal_update', v:true)
        try
        let l:line_count = getbufinfo(s:conversation_bufnr)[0].linecount
        call appendbufline(s:conversation_bufnr, l:line_count - 1, split(a:text, "\n", v:true))
        if l:stick && s:conversation_winid != -1 && win_id2win(s:conversation_winid) != 0
            call win_execute(s:conversation_winid, 'silent! normal! G')
        endif
        finally
            call setbufvar(s:conversation_bufnr, 'ollama_internal_update', l:internal_update)
        endtry
    endif
endfunction

function! ollama#edit#AppendDiagnostic(title, content, ...) abort
    if !bufexists(s:conversation_bufnr) || empty(a:content)
        return
    endif
    let l:append = a:0 > 0 && a:1
    let l:status = a:0 > 1 ? a:2 : ''
    let l:internal_update = getbufvar(s:conversation_bufnr, 'ollama_internal_update', v:false)
    let l:stick = getbufvar(s:conversation_bufnr, 'ollama_stick_to_bottom', v:true)
    call setbufvar(s:conversation_bufnr, 'ollama_internal_update', v:true)
    try
    let l:line_count = getbufinfo(s:conversation_bufnr)[0].linecount
    let l:end_line = -1
    if l:append
        let l:insert_at = -1
        for l:idx in range(l:line_count, 1, -1)
            if getbufline(s:conversation_bufnr, l:idx)[0] =~# '^#EndDiagnostic\>'
                let l:insert_at = l:idx - 1
                let l:end_line = l:idx
                break
            endif
        endfor
    else
        let l:insert_at = l:line_count - 1
    endif
    if l:insert_at < 0
        return
    endif
    let l:lines = l:append ? split(a:content, "\n", v:true) : ['#StartDiagnostic ' .. a:title] + split(a:content, "\n", v:true) + ['#EndDiagnostic']
    call appendbufline(s:conversation_bufnr, l:insert_at, l:lines)
    if l:append && !empty(l:status) && l:end_line >= 0
        let l:n = len(l:lines)
        for l:i in range(l:end_line, l:end_line + l:n)
            if l:i > 0 && getbufline(s:conversation_bufnr, l:i)[0] =~# '^#EndDiagnostic\>'
                call setbufline(s:conversation_bufnr, l:i, '#EndDiagnostic ' .. l:status)
                break
            endif
        endfor
    endif
    if l:stick && s:conversation_winid != -1 && win_id2win(s:conversation_winid) != 0
        " Keep diagnostic folds closed without toggling the fold under the cursor.
        call win_execute(s:conversation_winid, 'silent! setlocal foldlevel=0')
        call win_execute(s:conversation_winid, 'silent! normal! G')
    endif
    finally
        call setbufvar(s:conversation_bufnr, 'ollama_internal_update', l:internal_update)
    endtry
endfunction

function! ollama#edit#RefreshNERDTree() abort
    if !exists('*NERDTreeRefreshRoot') && exists(':NERDTreeRefreshRoot') != 2
        return
    endif
    for l:window in getwininfo()
        if getbufvar(l:window.bufnr, '&filetype') !=# 'nerdtree'
            continue
        endif
        if exists('*NERDTreeRefreshRoot')
            call win_execute(l:window.winid, 'silent call NERDTreeRefreshRoot()')
        else
            call win_execute(l:window.winid, 'silent NERDTreeRefreshRoot')
        endif
    endfor
endfunction

function! ollama#edit#ShowFile(path) abort
    let l:path = simplify(g:ollama_edit_cwd .. '/' .. a:path)
    if !filereadable(l:path)
        return
    endif

    let l:target_path = simplify(fnamemodify(l:path, ':p'))
    let l:target_bufnr = bufnr(l:target_path)
    let l:target_winid = -1

    " Reuse a visible window already showing the tool-created file first.
    if l:target_bufnr > 0
        for l:winid in win_findbuf(l:target_bufnr)
            if getbufvar(winbufnr(l:winid), '&filetype') !=# 'nerdtree'
                let l:target_winid = l:winid
                break
            endif
        endfor
    endif

    " Otherwise reuse an unmodified normal code window, never a NERDTree or
    " conversation window. This avoids losing unrelated user edits.
    if l:target_winid == -1
        for l:window in getwininfo()
            let l:bufnr = l:window.bufnr
            if getbufvar(l:bufnr, '&buftype') ==# ''
                        \ && getbufvar(l:bufnr, '&filetype') !=# 'nerdtree'
                        \ && !getbufvar(l:bufnr, '&modified')
                let l:target_winid = l:window.winid
                break
            endif
        endfor
    endif

    " Open a split only if no reusable code window is available.
    if l:target_winid == -1
        botright new
        let l:target_winid = win_getid()
    endif

    if !win_gotoid(l:target_winid)
        return
    endif
    " The worker may have written the file since Vim last loaded it. An
    " unmodified buffer can be refreshed safely; a modified one is preserved.
    if expand('%:p') !=# l:target_path
        execute 'edit! ' .. fnameescape(l:path)
    elseif !&modified
        execute 'edit! ' .. fnameescape(l:path)
    endif
    " Tool operations can update this file outside Vim while the buffer is open.
    setlocal autoread
    normal! gg
endfunction

function! ollama#edit#ShowChanges(ranges) abort
    if s:source_winid == -1 || !win_gotoid(s:source_winid)
        return
    endif
    if bufnr('%') != s:bufnr
        execute 'buffer ' .. s:bufnr
    endif
    call sign_unplace('OllamaEdit', {'buffer': s:bufnr})
    let l:seen = {}
    for l:range in a:ranges
        for l:line in range(l:range[0], l:range[1])
            if !has_key(l:seen, l:line)
                call sign_place(0, 'OllamaEdit', 'OllamaEditChange', s:bufnr, {'lnum': l:line, 'priority': 10})
                let l:seen[l:line] = v:true
            endif
        endfor
    endfor
    if !empty(l:seen)
        call cursor(a:ranges[0][0], 1)
        normal! zz
    endif
endfunction

function! ollama#edit#StripTrailingWhitespace(bufnr, ranges) abort
    for l:range in a:ranges
        for l:line_number in range(l:range[0], l:range[1])
            let l:line = getbufline(a:bufnr, l:line_number)
            if empty(l:line)
                continue
            endif
            let l:clean = substitute(l:line[0], '\s\+$', '', '')
            if l:clean !=# l:line[0]
                call setbufline(a:bufnr, l:line_number, l:clean)
            endif
        endfor
    endfor
endfunction

function! s:SubmitMakeResult(request_id, result) abort
    let l:result_json = json_encode(a:result)
    python3 << EOF
import json
import vim
CodeEditor.submit_make_result(vim.eval('a:request_id'), json.loads(vim.eval('l:result_json')))
EOF
endfunction

function! s:CollectMakeOutput(state, channel, message) abort
    if !empty(a:message)
        call add(a:state.output, a:message)
    endif
endfunction

function! s:SandboxWrap(command, write_paths) abort
    if !get(g:, 'ollama_bwrap_enabled', v:false)
        return a:command
    endif
    let l:bwrap = get(g:, 'ollama_bwrap_command', 'bwrap')
    if type(l:bwrap) != v:t_string || empty(l:bwrap) || !executable(l:bwrap)
        throw 'bubblewrap is enabled but was not found: ' .. string(l:bwrap)
    endif
    let l:root = simplify(fnamemodify(g:ollama_edit_cwd, ':p'))
    let l:command = [l:bwrap, '--die-with-parent', '--new-session', '--unshare-all',
                \ '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    if get(g:, 'ollama_bwrap_network', v:false)
        call filter(l:command, 'v:val !=# "--unshare-all"')
    endif
    for l:directory in ['/usr', '/usr/local', '/bin', '/sbin', '/lib', '/lib64', '/etc']
        if isdirectory(l:directory)
            call extend(l:command, ['--ro-bind', l:directory, l:directory])
        endif
    endfor
    call extend(l:command, ['--ro-bind', l:root, l:root])
    for l:relative in a:write_paths
        if type(l:relative) != v:t_string || empty(l:relative)
            throw 'bubblewrap write paths must be non-empty strings'
        endif
        let l:path = simplify(fnamemodify(l:root .. '/' .. l:relative, ':p'))
        if l:path !=# l:root && strpart(l:path, 0, strlen(l:root) + 1) !=# l:root .. '/'
                    \ || getftype(l:path) ==# 'link' || !isdirectory(l:path)
            throw 'bubblewrap write path must be an existing project directory: ' .. l:relative
        endif
        call extend(l:command, ['--bind', l:path, l:path])
    endfor
    call extend(l:command, ['--chdir', l:root, '--'] + a:command)
    return l:command
endfunction

function! s:ConfirmSandbox(tool, command) abort
    if !get(g:, 'ollama_bwrap_enabled', v:false)
        return v:true
    endif
    if !get(g:, 'ollama_bwrap_confirm', v:true)
        return v:true
    endif
    let l:key = a:tool .. "\n" .. join(a:command, "\n")
    if get(s:sandbox_session_approvals, l:key, v:false)
        return v:true
    endif
    let l:summary = a:tool ==# 'execute'
                \ ? 'Run the selected executable with project files read-only and network access disabled?'
                \ : 'Run the configured checker with project files read-only and network access disabled?'
    let l:choice = confirm(l:summary,
                \ "Allow &Once\nAllow for &Session\n&Cancel", 3)
    if l:choice == 2
        let s:sandbox_session_approvals[l:key] = v:true
        return v:true
    endif
    return l:choice == 1
endfunction

function! s:FinishMake(request_id, state, job, status) abort
    try
        let l:output = join(a:state.output, "\n")
        call setqflist([], 'r', {'lines': a:state.output, 'efm': a:state.errorformat})
        let l:diagnostics = []
        let l:error_count = 0
        let l:warning_count = 0
        for l:item in getqflist()
            let l:type = toupper(get(l:item, 'type', ''))
            let l:text = get(l:item, 'text', '')
            let l:is_error = l:type ==# 'E' || l:text =~? '\<\(error\|fatal\)\>'
            let l:is_warning = l:type ==# 'W' || l:text =~? '\<warning\>'
            if l:is_error
                let l:error_count += 1
            elseif l:is_warning
                let l:warning_count += 1
            elseif a:status != 0
                let l:error_count += 1
            endif
            if !l:is_error && !l:is_warning && a:status == 0
                continue
            endif
            call add(l:diagnostics, {
                        \ 'filename': get(l:item, 'filename', ''),
                        \ 'lnum': get(l:item, 'lnum', 0),
                        \ 'col': get(l:item, 'col', 0),
                        \ 'type': get(l:item, 'type', ''),
                        \ 'text': get(l:item, 'text', ''),
                        \ })
        endfor
        if empty(l:diagnostics) && a:status != 0
            let l:error_count = 1
        endif
        let l:ok = a:status == 0
        let l:result = {
                    \ 'ok': l:ok,
                    \ 'message': l:ok ? (l:warning_count > 0 ? printf('Vim makeprg completed with warnings (%d)', l:warning_count) : 'Vim makeprg completed successfully') : printf('Vim makeprg failed (errors: %d, warnings: %d)', l:error_count, l:warning_count),
                    \ 'output': l:output,
                    \ 'diagnostics': l:diagnostics,
                    \ }
    catch
        let l:result = {'ok': v:false, 'message': 'Vim makeprg failed: ' .. v:exception, 'output': join(a:state.output, "\n"), 'diagnostics': []}
    endtry
    call s:SubmitMakeResult(a:request_id, l:result)
endfunction

function! ollama#edit#RunMake(request_id, arguments) abort
    try
        for l:buffer in getbufinfo({'bufloaded': 1})
            call setbufvar(l:buffer.bufnr, '&autoread', 1)
        endfor
        let l:state = {
                    \ 'output': [],
                    \ 'errorformat': getbufvar(s:bufnr, '&errorformat'),
                    \ }
        let l:options = {
                    \ 'cwd': g:ollama_edit_cwd,
                    \ 'out_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'err_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'exit_cb': function('s:FinishMake', [a:request_id, l:state]),
                    \ }
        if type(a:arguments) != v:t_string && type(a:arguments) != v:t_list
            throw 'make arguments must be a string or list of target names'
        endif
        let l:targets = type(a:arguments) == v:t_list ? a:arguments : split(a:arguments)
        let l:command = getbufvar(s:bufnr, '&makeprg')
        if type(l:command) != v:t_string
            throw 'makeprg must be a string, got ' .. typename(l:command)
        endif
        for l:target in l:targets
            if type(l:target) != v:t_string || l:target =~# '^-' || l:target !~# '^[A-Za-z0-9_./:+-]\+$'
                throw 'make tool accepts only make target names; shell commands and options are not allowed'
            endif
            let l:command .= ' ' .. shellescape(l:target)
        endfor
        " makeprg may point to the secure scripts/mk helper, which provides
        " its own bubblewrap sandbox and lives outside the project directory.
        let l:job = job_start(['/bin/sh', '-c', l:command], l:options)
        if type(l:job) == v:t_number && l:job == -1
            throw 'failed to start configured makeprg'
        endif
    catch
        call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'Vim makeprg failed: ' .. v:exception .. ' (' .. v:throwpoint .. ')', 'output': '', 'diagnostics': []})
    endtry
endfunction

function! s:FinishCheck(request_id, state, job, status) abort
    let l:output = join(a:state.output, "\n")
    call setqflist([], 'r', {'lines': a:state.output, 'efm': a:state.errorformat})
    let l:diagnostics = []
    for l:item in getqflist()
        call add(l:diagnostics, {
                    \ 'filename': get(l:item, 'filename', ''),
                    \ 'lnum': get(l:item, 'lnum', 0),
                    \ 'col': get(l:item, 'col', 0),
                    \ 'type': get(l:item, 'type', ''),
                    \ 'text': get(l:item, 'text', ''),
                    \ })
    endfor
    let l:result = {
                \ 'ok': a:status == 0 && empty(l:diagnostics),
                \ 'message': a:status == 0 && empty(l:diagnostics) ? 'checker completed without diagnostics' : 'checker returned diagnostics',
                \ 'output': l:output,
                \ 'diagnostics': l:diagnostics,
                \ }
    call s:SubmitMakeResult(a:request_id, l:result)
endfunction

function! ollama#edit#RunCheck(request_id, ...) abort
    try
        let l:checker = get(g:, 'ollama_edit_checker', {})
        if type(l:checker) != v:t_dict || type(get(l:checker, 'command', v:null)) != v:t_list
            throw 'no valid checker is configured for this filetype'
        endif
        for l:argument in l:checker.command
            if type(l:argument) != v:t_string || empty(l:argument)
                throw 'checker command must be a list of non-empty strings'
            endif
        endfor
        let l:arguments = a:0 > 0 && type(a:1) == v:t_dict ? a:1 : {}
        let l:relative = get(l:arguments, 'path', '')
        if empty(l:relative)
            let l:relative = fnamemodify(bufname(s:bufnr), ':.')
        endif
        if empty(l:relative) || l:relative =~# '^\.\.[\\/]\|[\\/]\.\.[\\/]\|[\\/]\.\.$' || l:relative =~# '^/' || l:relative =~# '^[A-Za-z]:[\\/]'
            throw 'checker path must be a project-relative file path'
        endif
        let l:path = simplify(g:ollama_edit_cwd .. '/' .. l:relative)
        if getftype(l:path) ==# 'link' || !filereadable(l:path) || isdirectory(l:path)
            throw 'checker path must be an existing regular file'
        endif
        let l:command = []
        for l:argument in l:checker.command
            call add(l:command, substitute(l:argument, '{path}', escape(l:relative, '\&'), 'g'))
        endfor
        if !executable(l:command[0])
            throw 'checker executable was not found: ' .. l:command[0]
        endif
        let l:state = {'output': [], 'errorformat': get(l:checker, 'errorformat', '%f:%l:%c: %m')}
        let l:options = {
                    \ 'cwd': g:ollama_edit_cwd,
                    \ 'out_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'err_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'exit_cb': function('s:FinishCheck', [a:request_id, l:state]),
                    \ }
        let l:wrapped = s:SandboxWrap(l:command, [])
        if !s:ConfirmSandbox('vim-check', l:wrapped)
            call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'sandboxed vim-check cancelled by user', 'output': '', 'diagnostics': []})
            return
        endif
        let l:job = job_start(l:wrapped, l:options)
        if type(l:job) == v:t_number && l:job == -1
            throw 'failed to start configured checker'
        endif
    catch
        call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'checker failed: ' .. v:exception, 'output': '', 'diagnostics': []})
    endtry
endfunction

function! s:ExecuteDecisionFile() abort
    return g:ollama_edit_cwd .. '/.ollama-execute.json'
endfunction

function! s:LoadExecuteDecisions() abort
    let l:file = s:ExecuteDecisionFile()
    if !filereadable(l:file) || getftype(l:file) ==# 'link'
        return {}
    endif
    try
        let l:decisions = json_decode(join(readfile(l:file), "\n"))
        return type(l:decisions) == v:t_dict ? l:decisions : {}
    catch
        return {}
    endtry
endfunction

function! s:SaveExecuteDecisions(decisions) abort
    let l:file = s:ExecuteDecisionFile()
    if getftype(l:file) ==# 'link'
        throw 'execute decision file must not be a symbolic link'
    endif
    call writefile([json_encode(a:decisions)], l:file, 's')
endfunction

function! s:FinishExecute(request_id, state, job, status) abort
    let a:state.finished = v:true
    if a:state.timeout_timer != -1
        call timer_stop(a:state.timeout_timer)
    endif
    if a:state.kill_timer != -1
        call timer_stop(a:state.kill_timer)
    endif
    let l:output = join(a:state.output, "\n")
    let l:timed_out = get(a:state, 'timed_out', v:false)
    let l:label = get(a:state, 'sandboxed', v:false) ? 'Sandboxed execution' : 'Execution'
    let l:result = {
                \ 'ok': a:status == 0 && !l:timed_out,
                \ 'message': l:timed_out ? tolower(l:label) .. ' timed out and was terminated' : a:status == 0 ? tolower(l:label) .. ' completed successfully' : tolower(l:label) .. ' failed',
                \ 'output': l:output,
                \ 'exit_code': a:status,
                \ 'decision': get(a:state, 'decision', 'allowed'),
                \ }
    call s:SubmitMakeResult(a:request_id, l:result)
endfunction

function! ollama#edit#RunExecute(request_id, arguments) abort
    try
        if type(a:arguments) != v:t_dict || type(get(a:arguments, 'path', v:null)) != v:t_string || type(get(a:arguments, 'arguments', v:null)) != v:t_list
            throw 'execute tool requires a path and argument list'
        endif
        let l:relative = a:arguments.path
        let l:timeout = get(a:arguments, 'timeout', 30)
        let l:kill_timeout = get(a:arguments, 'kill_timeout', 3)
        if type(l:timeout) != v:t_number || l:timeout < 0
            throw 'execute timeout must be a non-negative number of seconds'
        endif
        if type(l:kill_timeout) != v:t_number || l:kill_timeout < 0
            throw 'execute kill_timeout must be a non-negative number of seconds'
        endif
        if empty(l:relative) || l:relative =~# '^\.\.[\\/]\|[\\/]\.\.[\\/]\|[\\/]\.\.$' || l:relative =~# '^[A-Za-z]:[\\/]'
            throw 'execute path must be relative and remain below the current directory'
        endif
        if l:relative =~# '^/' && !get(g:, 'ollama_bwrap_enabled', v:false)
            throw 'absolute system paths require bubblewrap'
        endif
        let l:is_absolute = l:relative =~# '^/'
        let l:path = l:is_absolute ? simplify(l:relative) : simplify(g:ollama_edit_cwd .. '/' .. l:relative)
        if get(g:, 'ollama_bwrap_enabled', v:false) && (l:is_absolute || l:relative !~# '[\\/]')
                    \ && (l:is_absolute || getftype(l:path) !=# 'file' || !executable(l:path))
            let l:path = l:is_absolute ? resolve(l:path) : exepath(l:relative)
        endif
        if get(g:, 'ollama_bwrap_enabled', v:false) && l:is_absolute
                    \ && l:path !~# '^/usr/\|^/bin/\|^/sbin/\|^/lib/\|^/lib64/'
            throw 'absolute path is outside the sandbox system paths'
        endif
        if empty(l:path) || getftype(l:path) ==# 'link' || !filereadable(l:path) || !executable(l:path) || isdirectory(l:path)
            throw 'execute path must be an executable regular file'
        endif
        for l:argument in a:arguments.arguments
            if type(l:argument) != v:t_string
                throw 'execute arguments must be a list of strings'
            endif
        endfor

        let l:key = fnamemodify(l:path, ':.')
        let l:decisions = s:LoadExecuteDecisions()
        let l:decision = 'allowed'
        if get(l:decisions, l:key, '') !=# 'always'
            let l:choice = confirm('Execute ' .. l:key .. '?', "Allow &Once\nAllow &Always\n&Cancel", 3)
            if l:choice == 3 || l:choice == 0
                call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'execution cancelled by user', 'cancelled': v:true, 'decision': 'canceled', 'output': []})
                return
            endif
            if l:choice == 1
                let l:decision = 'allowed_once'
            elseif l:choice == 2
                let l:decision = 'allowed_always'
                let l:decisions[l:key] = 'always'
                call s:SaveExecuteDecisions(l:decisions)
            endif
        else
            let l:decision = 'allowed_always'
        endif
        let l:state = {
                    \ 'output': [],
                    \ 'sandboxed': get(g:, 'ollama_bwrap_enabled', v:false),
                    \ 'finished': v:false,
                    \ 'timed_out': v:false,
                    \ 'timeout_timer': -1,
                    \ 'kill_timer': -1,
                    \ 'kill_timeout': l:kill_timeout,
                    \ 'decision': l:decision,
                    \ }
        let l:options = {
                    \ 'cwd': g:ollama_edit_cwd,
                    \ 'out_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'err_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'exit_cb': function('s:FinishExecute', [a:request_id, l:state]),
                    \ }
        let l:wrapped = s:SandboxWrap([l:path] + a:arguments.arguments, [])
        if !s:ConfirmSandbox('execute', l:wrapped)
            call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'sandboxed execute cancelled by user', 'output': '', 'decision': 'canceled'})
            return
        endif
        let l:job = job_start(l:wrapped, l:options)
        if type(l:job) == v:t_number && l:job == -1
            throw 'failed to start executable'
        endif
        let l:state.timeout_timer = timer_start(float2nr(l:timeout * 1000),
                    \ {-> s:TimeoutExecute(a:request_id, l:state, l:job)})
    catch
        call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'execute failed: ' .. v:exception, 'output': []})
    endtry
endfunction

function! s:TimeoutExecute(request_id, state, job) abort
    if a:state.finished
        return
    endif
    let a:state.timed_out = v:true
    call job_stop(a:job, 'term')
    let a:state.kill_timer = timer_start(float2nr(a:state.kill_timeout * 1000),
                \ {-> s:KillExecute(a:request_id, a:state, a:job)})
endfunction

function! s:KillExecute(request_id, state, job) abort
    if !a:state.finished
        call job_stop(a:job, 'kill')
    endif
endfunction

function! ollama#edit#EditCodeDone(status, ...) abort
    call s:CloseProgress()
    let g:edit_in_progress = 0

    if a:status ==# 'Done'
        echo 'OllamaEdit completed.'
    else
        let l:error = a:0 > 0 && !empty(a:1) ? a:1 : 'Unknown editing error'
        echohl ErrorMsg
        echom 'OllamaEdit: ' .. l:error
        echohl None
    endif
    redraw!
endfunction

function! ollama#edit#PromptEntered(text) abort
    if empty(a:text)
        return
    endif
    if get(b:, 'ollama_internal_update', v:false)
        return
    endif
    if g:edit_in_progress
        call ollama#edit#AppendProgress('An OllamaEdit request is already running.')
        return
    endif
    if !win_gotoid(s:source_winid) || !bufexists(s:bufnr)
        echoerr 'OllamaEdit: source buffer is no longer available'
        return
    endif
    if s:session_explain_mode
        call ollama#edit#ExplainCode(s:firstline, s:lastline, v:true, a:text)
    elseif s:session_range_mode
        call s:EditCodeRange(a:text, s:firstline, s:lastline, v:true)
    else
        call s:EditWorkspace(a:text, v:true)
    endif
endfunction

function! ollama#edit#UpdateProgress(timer) abort
    python3 << EOF
import json
import vim

try:
    events = CodeEditor.get_progress_events()
    start = int(vim.eval('g:ollama_edit_progress_index'))
    for event in events[start:]:
        if not event.get('diagnostic') and not event.get('fold') and not event.get('fold_append'):
            vim.command('call ollama#edit#AppendProgress(' + json.dumps(event.get('text', '')) + ')')
        if event.get('type') == 'make_request':
            arguments = event.get('arguments', {}).get('arguments', '')
            vim.command('call ollama#edit#RunMake(' + json.dumps(event['request_id']) + ', ' + json.dumps(arguments) + ')')
        if event.get('type') == 'check_request':
            vim.command('call ollama#edit#RunCheck(' + json.dumps(event['request_id']) + ', ' + json.dumps(event.get('arguments', {})) + ')')
        if event.get('type') == 'execute_request':
            vim.command('call ollama#edit#RunExecute(' + json.dumps(event['request_id']) + ', ' + json.dumps(event.get('arguments', {})) + ')')
        if event.get('fold'):
            vim.command('call ollama#edit#AppendDiagnostic(' + json.dumps(event.get('fold_title', event.get('tool', 'tool'))) + ', ' + json.dumps(event.get('text', '')) + ')')
        if event.get('fold_append'):
            vim.command('call ollama#edit#AppendDiagnostic(' + json.dumps(event.get('fold_title', event['fold_append'])) + ', ' + json.dumps(event.get('fold_content', event.get('text', ''))) + ', 1, ' + json.dumps(event.get('fold_status', '')) + ')')
        if event.get('diagnostic'):
            diagnostic = event['diagnostic']
            vim.command('call ollama#edit#AppendDiagnostic(' + json.dumps(diagnostic.get('title', 'tool output')) + ', ' + json.dumps(diagnostic.get('content', '')) + ')')
        if event.get('tool') in ('create_file', 'create_folder', 'delete_file', 'delete_folder') and event.get('path'):
            vim.command('call ollama#edit#RefreshNERDTree()')
        if event.get('tool') in ('create_file', 'insert_lines', 'delete_lines', 'replace_lines', 'write_file', 'chmod') and event.get('path'):
            vim.command('call ollama#edit#ShowFile(' + json.dumps(event['path']) + ')')
    vim.command('let g:ollama_edit_progress_index = ' + str(len(events)))

    result, operations, error = CodeEditor.get_job_status()
    if result != 'InProgress':
        if result == 'Done' and operations:
            bufnr = int(vim.eval('g:ollama_edit_bufnr'))
            firstline = int(vim.eval('g:ollama_edit_firstline'))
            lastline = int(vim.eval('g:ollama_edit_lastline'))
            expected_tick = int(vim.eval('g:ollama_edit_changedtick'))
            current_tick = int(vim.eval(f'getbufvar({bufnr}, "changedtick")'))
            if current_tick != expected_tick:
                result = 'Error'
                error = 'buffer changed while OllamaEdit was running'
            else:
                changed_ranges = CodeEditor.apply_operations(bufnr, firstline, lastline, operations)
                vim.command('call ollama#edit#StripTrailingWhitespace(' + str(bufnr) + ', ' + json.dumps(changed_ranges) + ')')
                vim.command('call ollama#edit#ShowChanges(' + json.dumps(changed_ranges) + ')')
        vim.command('call ollama#edit#EditCodeDone(' + json.dumps(result) + ', ' + json.dumps(error or '') + ')')
except Exception as exception:
    vim.command('call ollama#edit#EditCodeDone("Error", ' + json.dumps(str(exception)) + ')')
EOF
endfunction

function! s:StartEditSession(request, code, filetype, settings) abort
    if g:edit_in_progress
        echo 'An OllamaEdit request is already running.'
        return
    endif

    let s:bufnr = bufnr('%')
    let s:firstline = get(a:settings, 'start_line', 1)
    let s:lastline = get(a:settings, 'end_line', line('$'))
    let s:session_range_mode = get(a:settings, 'range_mode', v:true)
    let s:session_explain_mode = get(a:settings, 'explain_mode', v:false)
    let g:ollama_edit_bufnr = s:bufnr
    let g:ollama_edit_firstline = s:firstline
    let g:ollama_edit_lastline = s:lastline
    let g:ollama_edit_changedtick = b:changedtick
    let g:ollama_edit_cwd = getcwd()
    let g:ollama_edit_checker = get(a:settings, 'checker', {})

    let l:is_openai = g:ollama_edit_provider =~# '^openai'
    let l:session_settings = {
                \ 'url': l:is_openai ? g:ollama_openai_baseurl : g:ollama_host,
                \ 'provider': g:ollama_edit_provider,
                \ 'model': g:ollama_edit_model,
                \ 'options': g:ollama_edit_options,
                \ 'credentialname': l:is_openai ? g:ollama_openai_credentialname : g:ollama_ollama_credentialname,
                \ 'cwd': getcwd(),
                \ 'continue_history': get(a:settings, 'continue_history', v:false),
                \ 'instructions': get(g:, 'ollama_edit_instructions', ''),
                \ 'stop_on_error': get(g:, 'ollama_stop_on_error', v:false),
                \ 'show_llm_request': get(g:, 'ollama_show_llm_request', v:false),
                \ 'max_operations': get(g:, 'ollama_edit_max_operations', 64),
                \ 'sandbox_system_tools': get(g:, 'ollama_bwrap_enabled', v:false),
                \ }
    let l:session_settings = extend(l:session_settings, a:settings)
    let l:code_json = json_encode(a:code)
    let l:settings_json = json_encode(l:session_settings)
    let l:request_json = json_encode(a:request)
    let l:filetype_json = json_encode(a:filetype)
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    let g:edit_in_progress = 1
    let g:ollama_edit_progress_index = 0
    let s:source_winid = win_getid()
    call s:PrepareConversation(a:request)

    python3 << EOF
import json
import vim

request = json.loads(vim.eval('l:request_json'))
code = json.loads(vim.eval('l:code_json'))
filetype = json.loads(vim.eval('l:filetype_json'))
settings = json.loads(vim.eval('l:settings_json'))
CodeEditor.SetLogLevel(int(vim.eval('l:log_level')))
CodeEditor.start_vim_edit_code(request, code, filetype, settings)
EOF

    let s:timer = timer_start(100, {-> ollama#edit#UpdateProgress(0)}, {'repeat': -1})
endfunction

function! s:EditCodeRange(request, start_line, end_line, ...) abort
    let l:settings = {
                \ 'range_mode': v:true,
                \ 'filename': fnamemodify(expand('%:p'), ':.') ,
                \ 'start_line': a:start_line,
                \ 'end_line': a:end_line,
                \ 'continue_history': a:0 > 0 ? a:1 : v:false,
                \ }
    call s:StartEditSession(a:request, getline(a:start_line, a:end_line), &filetype, l:settings)
endfunction

function! s:EditWorkspace(request, ...) abort
    let l:settings = {'range_mode': v:false, 'continue_history': a:0 > 0 ? a:1 : v:false}
    if a:0 > 0 && type(a:1) == v:t_dict
        let l:settings = extend(l:settings, a:1)
    endif
    call s:StartEditSession(a:request, [], '', l:settings)
endfunction

function! ollama#edit#EditCode(request) range abort
    call s:EditCodeRange(a:request, a:firstline, a:lastline)
endfunction

function! ollama#edit#ExplainCode(start_line, end_line, ...) abort
    let l:request = a:0 > 1 ? a:2 : 'Explain the selected code. You can inspect related files when relevant, but avoid this if not needed.'
    let l:settings = {
                \ 'range_mode': v:true,
                \ 'explain_mode': v:true,
                \ 'filename': fnamemodify(expand('%:p'), ':.'),
                \ 'start_line': a:start_line,
                \ 'end_line': a:end_line,
                \ 'continue_history': a:0 > 0 ? a:1 : v:false,
                \ }
    call s:StartEditSession(
                \ l:request,
                \ getline(a:start_line, a:end_line), &filetype, l:settings)
endfunction

function! ollama#edit#EditCommand(request, start_line, end_line, range_count) abort
    if a:range_count == 0
        call s:EditWorkspace(a:request)
    else
        call s:EditCodeRange(a:request, a:start_line, a:end_line)
    endif
endfunction

function! ollama#edit#QuickFix() abort
    let l:filetype = &filetype
    let l:compiled = index(['c', 'cpp', 'objc', 'objcpp', 'rust'], l:filetype) >= 0
    let l:checker = get(get(g:, 'ollama_quickfix_checkers', {}), l:filetype, {})
    let l:build_output = ''
    let l:check_status = -1
    if l:compiled
        try
            " Run the initial build before starting the worker so its first prompt
            " already contains the current diagnostics.
            call execute('silent make!')
            let l:diagnostics = []
            for l:item in getqflist()
                let l:type = toupper(get(l:item, 'type', ''))
                let l:text = get(l:item, 'text', '')
                if l:type !~# '^[EW]$' && l:text !~? '\<\(error\|fatal\|warning\)\>'
                    continue
                endif
                let l:filename = get(l:item, 'filename', '')
                if empty(l:filename) && get(l:item, 'bufnr', 0) > 0
                    let l:filename = bufname(l:item.bufnr)
                endif
                let l:location = l:filename
                if get(l:item, 'lnum', 0) > 0
                    let l:location ..= ':' .. l:item.lnum
                    if get(l:item, 'col', 0) > 0
                        let l:location ..= ':' .. l:item.col
                    endif
                endif
                let l:diagnostic = get(l:item, 'text', '')
                if !empty(l:location)
                    let l:diagnostic = l:location .. ': ' .. l:diagnostic
                endif
                if !empty(l:diagnostic)
                    call add(l:diagnostics, l:diagnostic)
                endif
            endfor
            let l:build_output = join(l:diagnostics, "\n")
            let l:check_status = empty(l:diagnostics) ? 0 : 1
            redraw!
        catch
            let l:build_output = 'Vim :make failed: ' .. v:exception
        endtry
    elseif type(l:checker) == v:t_dict && type(get(l:checker, 'command', v:null)) == v:t_list
        try
            let l:relative = fnamemodify(expand('%:p'), ':.')
            if empty(l:relative) || l:relative =~# '^\.\.[\\/]\|[\\/]\.\.[\\/]\|[\\/]\.\.$'
                throw 'current buffer is outside the checker workspace'
            endif
            let l:checker_command = []
            for l:argument in l:checker.command
                call add(l:checker_command, substitute(l:argument, '{path}', escape(l:relative, '\&'), 'g'))
            endfor
            if empty(l:checker_command) || !executable(l:checker_command[0])
                throw 'checker executable was not found: ' .. (empty(l:checker_command) ? '[none]' : l:checker_command[0])
            endif
            let l:build_output = join(systemlist(l:checker_command), "\n")
            let l:check_status = v:shell_error
            call setqflist([], 'r', {'lines': split(l:build_output, "\n", v:true), 'efm': get(l:checker, 'errorformat', '%f:%l:%c: %m')})
            redraw!
        catch
            let l:build_output = 'Checker failed: ' .. v:exception
            let l:check_status = -1
        endtry
        if l:check_status == -1
            echo l:build_output
            redraw!
            return
        endif
    else
        let l:build_output = 'No checker is configured for filetype ' .. (empty(l:filetype) ? '[unknown]' : l:filetype) .. '.'
    endif

    if l:check_status == 0
        call s:OpenConversation('No errors, nothing to fix.')
        return
    endif

    let l:report = l:build_output
    if empty(l:report)
        let l:report = l:compiled ? 'Vim :make completed without diagnostics.' : 'Checker completed without diagnostics.'
    endif
    let l:report = substitute(l:report, '\%x00', "\n", 'g')
    if l:compiled
        let l:prompt = "We are in Vim-Ollama AI assisted QuickFix mode to fix build issues.\n\n"
                    \ .. "Current build results from Vim :make:\n```\n" .. l:report .. "\n```\n\n"
                    \ .. 'Fix all reported errors and warnings using the supplied OllamaEdit tools. '
                    \ .. 'Repeat the build, diagnosis, and fix cycle until the build succeeds. '
                    \ .. 'Use `vim-make` tool to verify after making changes. '
                    \ .. 'Never use the execute tool for compiling. '
                    \ .. 'At the end, provide a concise summary of the changes made and the final build status.'
        call s:EditWorkspace(l:prompt, {'quickfix_mode': v:true})
    else
        let l:checker_name = type(l:checker) == v:t_dict && type(get(l:checker, 'command', v:null)) == v:t_list ? join(l:checker.command, ' ') : '[none]'
        let l:prompt = "We are in Vim-Ollama AI assisted QuickFix mode to fix script-language issues.\n\n"
                    \ .. "Current checker results from " .. l:checker_name .. ":\n```\n" .. l:report .. "\n```\n\n"
                    \ .. 'Fix all reported errors and warnings using the supplied OllamaEdit tools. '
                    \ .. 'Repeat the checker, diagnosis, and fix cycle until the checker succeeds. '
                    \ .. 'Use the `vim-check` tool after making changes. Do not use vim-make. '
                    \ .. 'At the end, provide a concise summary of the changes made and the final checker status.'
        call s:EditWorkspace(l:prompt, {'checker': l:checker, 'quickfix_checker': v:true})
    endif
endfunction

function! ollama#edit#InitAgents() abort
    let l:prompt_file = g:ollama_plugin_dir .. '/agents_prompt.md'
    if !filereadable(l:prompt_file)
        echoerr 'OllamaInitAgents: agents_prompt.md was not found'
        return
    endif
    call s:EditWorkspace(join(readfile(l:prompt_file), "\n"))
endfunction

function! ollama#edit#EditPrompt() range abort
    let l:prompt = input('Enter prompt: ', '', 'file')
    if !empty(l:prompt)
        call s:EditCodeRange(l:prompt, a:firstline, a:lastline)
    endif
endfunction
