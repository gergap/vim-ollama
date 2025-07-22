" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
" Set up omni-completion for Ollama config file

" Default list
let s:model_list = ['starcoder2:3b', 'qwen2.5-coder:7b', 'codellama:code', 'llama3.1:8b']
let s:new_models = []
let s:fetched = 0

" Help text for balloon expression
let s:help_text = {
\ 'ollama_use_venv': 'Use Python virtual environment',
\ 'ollama_host': 'Ollama API host URL (default=http://localhost:11434).',
\ 'ollama_model': 'Default model for <tab> completions.',
\ 'ollama_model_options': 'Options for model customization.',
\ 'ollama_context_lines': 'Number of context lines to consider (default=10).',
\ 'ollama_debounce_time': 'Debounce time for completions in [ms] (default=500).',
\ 'ollama_chat_model': 'Model used for chat interactions.',
\ 'ollama_chat_systemprompt': 'System prompt for chat context.',
\ 'ollama_chat_options': 'Chat model customization options.',
\ 'ollama_chat_timeout': 'Timeout for chat responses in seconds (default=10).',
\ 'ollama_edit_model': 'Model used for text editing.',
\ 'ollama_edit_options': 'Options for edit model.',
\ 'ollama_use_inline_diff': 'Use inline diff for edits (default=1).',
\ 'ollama_debug': 'Enable debug logging (0=Off, 1=Errors, 2=Warnings, 3=Info, 4=Debug, default=0).',
\ 'ollama_logfile': 'Logfile path for debugging.',
\ 'ollama_review_logfile': 'Review-specific logfile path.',
\ 'ollama_no_maps': 'Disable default mappings for Ollama plugs (default=0).',
\ 'ollama_model_provider': 'Provider for code completions: "ollama" or "openai".',
\ 'ollama_edit_model_provider': 'Provider for code edits: "ollama" or "openai".',
\ 'ollama_chat_model_provider': 'Provider for chat conversations: "ollama" or "openai".',
\ 'ollama_openai_api_key': 'OpenAI API key for OpenAI provider.',
\ 'ollama_enabled': 'Enable or disable Ollama integration.'
\ }

" Retrieves the list of installed Ollama models asynchronously
function! ollama#config#FetchModels() abort
    if (s:fetched)
        return
    endif
    let s:fetched = 1

    " Construct the shell command to call list_models.py with the provided URL
    let l:script_path = printf('%s/python/list_models.py', g:ollama_plugin_dir)
    let l:command = [ g:ollama_python_interpreter, l:script_path, '-u', g:ollama_host]

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
    return keys(s:help_text)
endfunction

function! ollama#config#OmniComplete(findstart, base)
    let line = getline('.')
    let col = col('.') - 1

    if a:findstart
        " Find the start position for completion
        " Case 1: Inside quotes for model name completion
        if line =~# '\v(ollama_model|ollama_chat_model|ollama_edit_model)\s*\=\s*'''
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
        if line =~# '\v(ollama_model|ollama_chat_model|ollama_edit_model)\s*\=\s*'''
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
    if line =~# '\v(ollama_model|ollama_chat_model|ollama_edit_model)\s*\=\s*$'
        call ollama#config#FetchModels()
        return "'\<C-X>\<C-O>"
    else
        return "'"
    endif
endfunction

function! ollama#config#SetupHelp() abort
    " Check if balloon evaluation is supported
    if has('balloon_eval')
        setlocal balloonexpr=ollama#config#ShowHelp()
        setlocal ballooneval
        setlocal balloonevalterm
    endif
endfunction

function! ollama#config#ShowHelp() abort
    " Get the word under the mouse cursor if available, otherwise use the cursor position
    let l:word = (exists('v:beval_text') && !empty(v:beval_text)) ? v:beval_text : expand('<cword>')

    " Check if it's a relevant config variable
    if has_key(s:help_text, l:word)
        return s:help_text[l:word]
    else
        return ''
    endif
endfunction

" vim: filetype=vim
