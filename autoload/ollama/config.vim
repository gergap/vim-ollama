" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
" Set up omni-completion for Ollama config file

" Default list
let s:model_list = ['starcoder2:3b', 'qwen2.5-coder:7b', 'codellama:code', 'llama3.1:8b']
let s:new_models = []
let s:fetched = 0

" Retrieves the list of installed Ollama models asynchronously
function! ollama#config#FetchModels() abort
    if (s:fetched)
        return
    endif
    let s:fetched = 1

    " Construct the shell command to call list_models.py with the provided URL
    let l:script_path = printf('%s/python/list_models.py', expand('<script>:h:h:h'))
    let l:command = ['python3', l:script_path, '-u', g:ollama_host]

    " Define the callback for when the job finishes
    let l:job_options = {
                \ 'out_cb': function('ollama#config#HandleJobOutput'),
                \ 'err_cb': function('ollama#config#HandleJobError'),
                \ 'exit_cb': function('ollama#config#HandleJobExit'),
                \ }

    " Start the asynchronous job
    call job_start(l:command, l:job_options)
endfunction

" Handles the output of the async job
function! ollama#config#HandleJobOutput(channel, msg) abort
    if empty(a:msg)
        return
    endif

    " append models to list
    call extend(s:new_models, split(a:msg, '\n'))
    " filter duplicates and sort alphabetically
    let s:new_models = sort(uniq(s:new_models))
endfunction

" Handles errors from the async job
function! ollama#config#HandleJobError(channel, msg) abort
    if !empty(a:msg)
        echoerr "Error: " . a:msg
    endif
endfunction

function! ollama#config#HandleJobExit(channel, status) abort
    if a:status == 0
        let s:model_list = s:new_models
        " update popup list
        call feedkeys("\<C-x>\<C-o>")
    else
        let s:fetched = 0
    endif
endfunction

" Function to get available model names (dummy example, replace with your function)
function! OllamaModelNames()
    return s:model_list
endfunction

" Function to get variable names starting with g:ollama_
function! OllamaVariableNames()
    return [ 'ollama_host', 'ollama_model', 'ollama_chat_model', 'ollama_model_options', 'ollama_chat_options', 'ollama_debounce_time', 'ollama_debug', 'ollama_log_file', 'ollama_enabled']
endfunction

function! ollama#config#OmniComplete(findstart, base)
    let line = getline('.')
    let col = col('.') - 1

    if a:findstart
        " Find the start position for completion
        " Case 1: Inside quotes for model name completion
        if line =~# '\v(ollama_model|ollama_chat_model)\s*\=\s*'''
            let pos = matchstrpos(line, '=\s*''\zs[^'']')[1]
            return pos

        " Case 2: Completing variable names starting with g:
        elseif line =~# '\vg:[a-zA-Z0-9_]*$'
            return matchstrpos(line, '\vg:\zs[a-zA-Z0-9_]*$')[1]

        else
            return -2  " Not supported context
        endif
    else
        " Provide completion options
        " Case 1: Completing model names
        if line =~# '\v(ollama_model|ollama_chat_model)\s*\=\s*'''
            return OllamaModelNames()

        " Case 2: Completing variable names
        elseif line =~# '\vg:[a-zA-Z0-9_]*$'
            return OllamaVariableNames()

        else
            return []  " Empty completion
        endif
    endif
endfunction

function ollama#config#TriggerModelCompletion()
    let line = getline('.')
    if line =~# '\v(ollama_model|ollama_chat_model)\s*\=\s*$'
        call ollama#config#FetchModels()
        return "'\<C-X>\<C-O>"
    else
        return "'"
    endif
endfunction

" vim: filetype=vim

