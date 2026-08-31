" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>

let s:popup = 0
let s:timer = 0
let s:bufnr = -1
let s:source_winid = -1
let s:conversation_bufnr = -1
let s:change_match = -1
let s:firstline = 0
let s:lastline = 0
let g:edit_in_progress = 0

function! s:CloseProgress() abort
    if s:timer != 0
        call timer_stop(s:timer)
        let s:timer = 0
    endif
endfunction

function! s:OpenConversation(request) abort
    let s:source_winid = win_getid()
    botright new
    setlocal buftype=nofile bufhidden=hide noswapfile
    setlocal filetype=markdown
    let s:conversation_bufnr = bufnr('%')
    call setline(1, ['OllamaEdit', '=========', '', 'Request: ' .. a:request, ''])
endfunction

function! ollama#edit#AppendProgress(text) abort
    if bufexists(s:conversation_bufnr)
        call appendbufline(s:conversation_bufnr, '$', a:text)
    endif
endfunction

function! ollama#edit#ShowFile(path) abort
    if s:source_winid == -1 || !win_gotoid(s:source_winid)
        return
    endif
    let l:path = simplify(g:ollama_edit_cwd .. '/' .. a:path)
    if filereadable(l:path)
        execute 'edit ' .. fnameescape(l:path)
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
    if s:change_match != -1
        call matchdelete(s:change_match)
        let s:change_match = -1
    endif
    let l:positions = []
    for l:range in a:ranges
        for l:line in range(l:range[0], l:range[1])
            call add(l:positions, [l:line])
        endfor
    endfor
    if !empty(l:positions)
        let s:change_match = matchaddpos('DiffChange', l:positions)
        call cursor(a:ranges[0][0], 1)
        normal! zz
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

function! ollama#edit#UpdateProgress(timer) abort
    python3 << EOF
import json
import vim

try:
    events = CodeEditor.get_progress_events()
    start = int(vim.eval('g:ollama_edit_progress_index'))
    for event in events[start:]:
        vim.command('call ollama#edit#AppendProgress(' + json.dumps(event.get('text', '')) + ')')
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
                vim.command('call ollama#edit#ShowChanges(' + json.dumps(changed_ranges) + ')')
        vim.command('call ollama#edit#EditCodeDone(' + json.dumps(result) + ', ' + json.dumps(error or '') + ')')
except Exception as exception:
    vim.command('call ollama#edit#EditCodeDone("Error", ' + json.dumps(str(exception)) + ')')
EOF
endfunction

function! s:EditCodeInternal(request, start_line, end_line) abort
    if g:edit_in_progress
        echo 'An OllamaEdit request is already running.'
        return
    endif

    let s:bufnr = bufnr('%')
    let s:firstline = a:start_line
    let s:lastline = a:end_line
    let g:ollama_edit_bufnr = s:bufnr
    let g:ollama_edit_firstline = s:firstline
    let g:ollama_edit_lastline = s:lastline
    let g:ollama_edit_changedtick = b:changedtick
    let g:ollama_edit_cwd = getcwd()

    let l:is_openai = g:ollama_edit_provider =~# '^openai'
    let l:settings = {
                \ 'url': l:is_openai ? g:ollama_openai_baseurl : g:ollama_host,
                \ 'provider': g:ollama_edit_provider,
                \ 'model': g:ollama_edit_model,
                \ 'options': g:ollama_edit_options,
                \ 'credentialname': l:is_openai ? g:ollama_openai_credentialname : g:ollama_ollama_credentialname,
                \ 'cwd': getcwd(),
                \ }
    let l:code_json = json_encode(getline(s:firstline, s:lastline))
    let l:settings_json = json_encode(l:settings)
    let l:request_json = json_encode(a:request)
    let l:filetype = &filetype
    let l:filetype_json = json_encode(l:filetype)
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    let g:edit_in_progress = 1
    let g:ollama_edit_progress_index = 0
    call s:OpenConversation(a:request)

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

function! ollama#edit#EditCode(request) range abort
    call s:EditCodeInternal(a:request, a:firstline, a:lastline)
endfunction

function! ollama#edit#EditPrompt() range abort
    let l:prompt = input('Enter prompt: ', '', 'file')
    if !empty(l:prompt)
        call s:EditCodeInternal(l:prompt, a:firstline, a:lastline)
    endif
endfunction
