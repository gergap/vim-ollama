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
    setlocal wrap
    setlocal modifiable
    let s:conversation_bufnr = bufnr('%')
    let s:conversation_winid = win_getid()
    call setline(1, ['OllamaEdit', '=========', '', 'Request: ' .. a:request, ''])
    call prompt_setcallback(s:conversation_bufnr, function('ollama#edit#PromptEntered'))
    call prompt_setprompt(s:conversation_bufnr, '>>> ')
endfunction

function! s:PrepareConversation(request) abort
    if !bufexists(s:conversation_bufnr) || !win_gotoid(s:conversation_winid)
        call s:OpenConversation(a:request)
        return
    endif
    let l:line_count = getbufinfo(s:conversation_bufnr)[0].linecount
    call appendbufline(s:conversation_bufnr, l:line_count - 1, ['', 'Follow-up: ' .. a:request, ''])
endfunction

function! ollama#edit#AppendProgress(text) abort
    if bufexists(s:conversation_bufnr)
        let l:line_count = getbufinfo(s:conversation_bufnr)[0].linecount
        call appendbufline(s:conversation_bufnr, l:line_count - 1, split(a:text, "\n", v:true))
        if s:conversation_winid != -1 && win_id2win(s:conversation_winid) != 0
            call win_execute(s:conversation_winid, 'silent! normal! G')
        endif
    endif
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
    if s:source_winid == -1 || !win_gotoid(s:source_winid)
        return
    endif
    let l:path = simplify(g:ollama_edit_cwd .. '/' .. a:path)
    if filereadable(l:path)
        " The worker may have written this file since Vim last loaded it.
        " Never discard unrelated unsaved edits in the source window.
        if &modified && expand('%:p') !=# simplify(fnamemodify(l:path, ':p'))
            botright new
        endif
        execute 'edit! ' .. fnameescape(l:path)
        normal! gg
    endif
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

function! s:FinishMake(request_id, state, job, status) abort
    try
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
                    \ 'ok': empty(l:diagnostics) && a:status == 0,
                    \ 'message': empty(l:diagnostics) && a:status == 0 ? 'Vim makeprg completed without diagnostics' : 'Vim makeprg returned diagnostics',
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
        let l:command = getbufvar(s:bufnr, '&makeprg')
        for l:target in split(a:arguments)
            if l:target =~# '^-' || l:target !~# '^[A-Za-z0-9_./:+-]\+$'
                throw 'make tool accepts only make target names; shell commands and options are not allowed'
            endif
            let l:command .= ' ' .. shellescape(l:target)
        endfor
        let l:job = job_start(l:command, l:options)
        if type(l:job) == v:t_number && l:job == -1
            throw 'failed to start configured makeprg'
        endif
    catch
        call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'Vim makeprg failed: ' .. v:exception, 'output': '', 'diagnostics': []})
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
    let l:output = join(a:state.output, "\n")
    let l:result = {
                \ 'ok': a:status == 0,
                \ 'message': a:status == 0 ? 'execution completed successfully' : 'execution failed',
                \ 'output': l:output,
                \ 'exit_code': a:status,
                \ }
    call s:SubmitMakeResult(a:request_id, l:result)
endfunction

function! ollama#edit#RunExecute(request_id, arguments) abort
    try
        if type(a:arguments) != v:t_dict || type(get(a:arguments, 'path', v:null)) != v:t_string || type(get(a:arguments, 'arguments', v:null)) != v:t_list
            throw 'execute tool requires a path and argument list'
        endif
        let l:relative = a:arguments.path
        if empty(l:relative) || l:relative =~# '^\.\.[\\/]\|[\\/]\.\.[\\/]\|[\\/]\.\.$' || l:relative =~# '^/' || l:relative =~# '^[A-Za-z]:[\\/]'
            throw 'execute path must be relative and remain below the current directory'
        endif
        let l:path = simplify(g:ollama_edit_cwd .. '/' .. l:relative)
        if getftype(l:path) ==# 'link' || !filereadable(l:path) || !executable(l:path) || isdirectory(l:path)
            throw 'execute path must be an executable regular file'
        endif
        for l:argument in a:arguments.arguments
            if type(l:argument) != v:t_string || stridx(l:argument, "\x00") != -1
                throw 'execute arguments must be a list of strings'
            endif
        endfor

        let l:key = fnamemodify(l:path, ':.')
        let l:decisions = s:LoadExecuteDecisions()
        if get(l:decisions, l:key, '') !=# 'always'
            let l:choice = confirm('Execute ' .. l:key .. '?', "Allow &Once\nAllow &Always\n&Cancel", 3)
            if l:choice == 3 || l:choice == 0
                call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'execution cancelled by user', 'cancelled': v:true, 'output': []})
                return
            endif
            if l:choice == 2
                let l:decisions[l:key] = 'always'
                call s:SaveExecuteDecisions(l:decisions)
            endif
        endif

        let l:state = {'output': []}
        let l:options = {
                    \ 'cwd': g:ollama_edit_cwd,
                    \ 'out_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'err_cb': function('s:CollectMakeOutput', [l:state]),
                    \ 'exit_cb': function('s:FinishExecute', [a:request_id, l:state]),
                    \ }
        let l:job = job_start([l:path] + a:arguments.arguments, l:options)
        if type(l:job) == v:t_number && l:job == -1
            throw 'failed to start executable'
        endif
    catch
        call s:SubmitMakeResult(a:request_id, {'ok': v:false, 'message': 'execute failed: ' .. v:exception, 'output': []})
    endtry
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
    if g:edit_in_progress
        call ollama#edit#AppendProgress('An OllamaEdit request is already running.')
        return
    endif
    if !win_gotoid(s:source_winid) || !bufexists(s:bufnr)
        echoerr 'OllamaEdit: source buffer is no longer available'
        return
    endif
    call s:EditCodeRange(a:text, 1, line('$'), v:true)
endfunction

function! ollama#edit#UpdateProgress(timer) abort
    python3 << EOF
import json
import vim

try:
    events = CodeEditor.get_progress_events()
    start = int(vim.eval('g:ollama_edit_progress_index'))
    for event in events[start:]:
        vim.command('call ollama#edit#AppendProgress(' + json.dumps(event.get('text', '')) + ')')
        if event.get('type') == 'make_request':
            arguments = event.get('arguments', {}).get('arguments', '')
            vim.command('call ollama#edit#RunMake(' + json.dumps(event['request_id']) + ', ' + json.dumps(arguments) + ')')
        if event.get('type') == 'execute_request':
            vim.command('call ollama#edit#RunExecute(' + json.dumps(event['request_id']) + ', ' + json.dumps(event.get('arguments', {})) + ')')
        if event.get('tool') in ('create_file', 'create_folder', 'delete_file', 'delete_folder') and event.get('path'):
            vim.command('call ollama#edit#RefreshNERDTree()')
        if event.get('tool') == 'create_file' and event.get('path'):
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
    let g:ollama_edit_bufnr = s:bufnr
    let g:ollama_edit_firstline = s:firstline
    let g:ollama_edit_lastline = s:lastline
    let g:ollama_edit_changedtick = b:changedtick
    let g:ollama_edit_cwd = getcwd()

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
    call s:StartEditSession(a:request, [], '', l:settings)
endfunction

function! ollama#edit#EditCode(request) range abort
    call s:EditCodeRange(a:request, a:firstline, a:lastline)
endfunction

function! ollama#edit#EditCommand(request, start_line, end_line, range_count) abort
    if a:range_count == 0
        call s:EditWorkspace(a:request)
    else
        call s:EditCodeRange(a:request, a:start_line, a:end_line)
    endif
endfunction

function! ollama#edit#QuickFix() abort
    call s:EditWorkspace(
                \ 'Build the project with vim-make, inspect all compiler errors and warnings, and fix them. '
                \ .. 'Repeat the build, diagnosis, and fix cycle until the build succeeds. '
                \ .. 'Use the supplied OllamaEdit tools for every change. '
                \ .. 'Never use the execute tool for compiling, use vim-make instead. '
                \ .. 'At the end, provide a concise summary of the changes made and the final build status.')
endfunction

function! ollama#edit#EditPrompt() range abort
    let l:prompt = input('Enter prompt: ', '', 'file')
    if !empty(l:prompt)
        call s:EditCodeRange(l:prompt, a:firstline, a:lastline)
    endif
endfunction
