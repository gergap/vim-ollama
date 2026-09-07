" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2026 Gerhard Gappmeier <gappy1502@gmx.net>
" Session-local TODO storage and display for OllamaEdit.
scriptencoding utf-8

let s:todos = []
let s:bufnr = -1

function! s:StatusMark(status) abort
    return a:status ==# 'completed' ? '[✓]' : a:status ==# 'in_progress' ? '[•]' : a:status ==# 'cancelled' ? '[✕]' : '[ ]'
endfunction

function! s:Lines() abort
    let l:lines = ['Ollama Todo List', '================', '']
    for l:todo in s:todos
        call add(l:lines, s:StatusMark(l:todo.status) .. ' ' .. l:todo.content)
    endfor
    if empty(s:todos)
        call add(l:lines, '[ ] No todos')
    endif
    return l:lines
endfunction

function! s:SetupWindow() abort
    setlocal nonumber norelativenumber signcolumn=no foldcolumn=0 wrap
    execute 'vertical resize ' .. max([40, &columns / 4])
endfunction

function! s:OpenOrUpdate() abort
    if !bufexists(s:bufnr)
        botright vertical new
        let s:bufnr = bufnr('%')
        setlocal buftype=nofile bufhidden=hide noswapfile
        setlocal filetype=vim nospell
        call s:SetupWindow()
        setlocal nomodifiable readonly
        let b:ollama_todo = v:true
    else
        let l:window = bufwinid(s:bufnr)
        if l:window != -1
            call win_gotoid(l:window)
        else
            botright vertical split
            execute 'buffer ' .. s:bufnr
        endif
        call s:SetupWindow()
    endif
    let l:modifiable = &l:modifiable
    setlocal modifiable noreadonly
    call setline(1, s:Lines())
    if line('$') > len(s:Lines())
        call deletebufline(s:bufnr, len(s:Lines()) + 1, '$')
    endif
    let &l:modifiable = l:modifiable
    setlocal readonly nomodifiable
endfunction

function! ollama#todo#Write(request_id, arguments) abort
    try
        if type(a:arguments) != v:t_dict || type(get(a:arguments, 'todos', v:null)) != v:t_list
            throw 'todowrite requires a todos list'
        endif
        let l:todos = []
        let l:ids = {}
        for l:todo in a:arguments.todos
            if type(l:todo) != v:t_dict
                throw 'each todo must be an object'
            endif
            for l:key in ['content', 'status', 'priority', 'id']
                if type(get(l:todo, l:key, v:null)) != v:t_string || empty(get(l:todo, l:key))
                    throw 'each todo requires non-empty string fields: content, status, priority, id'
                endif
            endfor
            if index(['pending', 'in_progress', 'completed', 'cancelled'], l:todo.status) < 0
                throw 'todo status must be pending, in_progress, completed, or cancelled'
            endif
            if index(['high', 'medium', 'low'], l:todo.priority) < 0
                throw 'todo priority must be high, medium, or low'
            endif
            if has_key(l:ids, l:todo.id)
                throw 'todo ids must be unique'
            endif
            let l:ids[l:todo.id] = v:true
            call add(l:todos, {'content': l:todo.content, 'status': l:todo.status,
                        \ 'priority': l:todo.priority, 'id': l:todo.id})
        endfor
        let s:todos = l:todos
        call s:OpenOrUpdate()
        let l:remaining = len(filter(copy(s:todos), 'v:val.status !=# "completed"'))
        let l:output = json_encode(s:todos)
        call ollama#edit#SubmitMakeResult(a:request_id, {
                    \ 'ok': v:true,
                    \ 'title': l:remaining .. ' todos',
                    \ 'output': l:output,
                    \ 'metadata': {'todos': s:todos},
                    \ 'message': l:remaining .. ' todos updated'})
    catch
        call ollama#edit#SubmitMakeResult(a:request_id, {'ok': v:false, 'message': v:exception, 'error': v:exception})
    endtry
endfunction

function! ollama#todo#Show() abort
    call s:OpenOrUpdate()
endfunction
