" autoload/ollama.vim
" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
scriptencoding utf-8

" numeric timer Id
let s:timer_id = -1
" a running REST API job
let s:job = v:null
let s:kill_job = v:null
" fill-in-the-middle (default settings for codellama)
let s:fim_prefix = '<PRE> '
let s:fim_middle = ' <MID>'
let s:fim_suffix = ' <SUF>'
" current prompt
let s:prompt = ''
" current suggestions
let s:suggestion = ''
" text property id for ghost text
let s:prop_id = -1

let s:has_nvim_ghost_text = has('nvim-0.6') && exists('*nvim_buf_get_mark')
let s:vim_minimum_version = '9.0.0185'
let s:has_vim_ghost_text = has('patch-' . s:vim_minimum_version) && has('textprop')
let s:has_ghost_text = s:has_nvim_ghost_text || s:has_vim_ghost_text

let s:hlgroup = 'OllamaSuggestion'
let s:annot_hlgroup = 'OllamaAnnotation'

if s:has_vim_ghost_text && empty(prop_type_get(s:hlgroup))
    call prop_type_add(s:hlgroup, {'highlight': s:hlgroup})
endif
if s:has_vim_ghost_text && empty(prop_type_get(s:annot_hlgroup))
    call prop_type_add(s:annot_hlgroup, {'highlight': s:annot_hlgroup})
endif

function! ollama#Schedule()
    if !ollama#IsEnabled()
        return
    endif
    call ollama#logger#Debug("Scheduling timer...")
    " get current buffer type
    if &buftype=='prompt'
        call ollama#logger#Debug("Ignoring prompt buffer")
        return
    endif
    call s:KillTimer()
    let s:suggestion = ''
    call ollama#UpdatePreview(s:suggestion)
    let s:timer_id = timer_start(g:ollama_debounce_time, 'ollama#GetSuggestion')
endfunction

" handle output on stdout
function! s:HandleCompletion(job, data)
    call ollama#logger#Debug("Received completion: ".a:data)
    if !empty(a:data)
        "let l:suggestion = join(a:data, "\n")
        let s:suggestion = a:data
        call ollama#UpdatePreview(s:suggestion)
    endif
endfunction

" handle output on stderr
function! s:HandleError(job, data)
    call ollama#logger#Debug("Received stderr: ".a:data)
    if !empty(a:data)
        echohl ErrorMsg
        echom "Error: " . join(a:data, "\n")
        echohl None
    endif
endfunction

function! s:HandleExit(job, exit_code)
    call ollama#logger#Debug("Process exited: ".a:exit_code)
    if a:exit_code != 0
        " Don't log errors if we killed the job, this is expected
        if a:job isnot s:kill_job
            echohl ErrorMsg
            echo "Process exited with code: " . a:exit_code
            echohl None
        else
            call ollama#logger#Debug("Process terminated as expected")
        endif
        call ollama#ClearPreview()
    endif
    " release reference to job object
    if s:job is a:job
        let s:job = v:null
    endif
    let s:prompt = ''
endfunction

function! ollama#GetSuggestion(timer)
    call ollama#logger#Debug("GetSuggestion")
    " reset timer handle when called
    let s:timer_id = -1
    let l:current_line = line('.')
    let l:current_col = col('.')
    let l:context_lines = 30
    " get active FIM settings
    let l:fim_prefix = get(g:, 'ollama_fim_prefix', s:fim_prefix)
    let l:fim_middle = get(g:, 'ollama_fim_middle', s:fim_middle)
    let l:fim_suffix = get(g:, 'ollama_fim_suffix', s:fim_suffix)

    " Get the lines before and after the current line
    let l:prefix_lines = getline(max([1, l:current_line - l:context_lines]), l:current_line - 1)
    let l:suffix_lines = getline(l:current_line + 1, min([line('$'), l:current_line + l:context_lines]))

    " Combine prefix lines and current line's prefix part
    let l:prefix = join(l:prefix_lines, "\n")
    if !empty(l:prefix)
        let l:prefix .= "\n"
    endif
    let l:prefix .= strpart(getline('.'), 0, l:current_col - 1)
    " Combine suffix lines and current line's suffix part
    let l:suffix = strpart(getline('.'), l:current_col - 1)
    if !empty(l:suffix)
        let l:suffix .= "\n"
    endif
    let l:suffix .= join(l:suffix_lines, "\n")

    " Create the prompt using the specified syntax
    if (g:ollama_model == 'llama3')
        " TODO: make this working!!!
        " llama3 does not support fill-in-the-middle, so we use a carefully
        " engineered prompt instead and hope for the best.
        let l:prompt = "You are a code completion model. When provided with some code, complete the code marked with _____. Output only the completion. Output no other code. Output no other text.\n"
        let l:prompt .= "```\n".l:prefix."_____\n".l:suffix."\n```"
    else
        " Regular fill-in-the-middle for codellama using configured tokens
        let l:prompt = l:fim_prefix . l:prefix . l:fim_suffix . l:suffix . l:fim_middle
    endif

    " Adjust the command to use the prompt as stdin input
    let l:command = printf('python3 %s/python/ollama.py -m %s -u %s', expand('<script>:h:h'), g:ollama_model, g:ollama_host)
    let l:job_options = {
        \ 'out_mode': 'raw',
        \ 'out_cb': function('s:HandleCompletion'),
        \ 'exit_cb': function('s:HandleExit')
        \ }
        "\ 'err_cb': function('s:HandleError'),

    if (s:prompt == l:prompt)
        call ollama#logger#Debug("Ignoring search for '".l:prompt."'. Already running.")
        return
    endif
    " save current search
    let s:prompt = l:prompt

    " Kill any running job and replace with new one
    if s:job isnot v:null
        call ollama#logger#Debug("Terminating existing job.")
        call s:KillJob()
    endif

    call ollama#logger#Debug("Starting job for '".l:prompt."'...")
    " create job object and hold reference to avoid closing channels
    let s:job = job_start(l:command, l:job_options)
    let channel = job_getchannel(s:job)
    call ch_sendraw(channel, l:prompt)
    call ch_close_in(channel)
endfunction

function! ollama#UpdatePreview(suggestion)
    call ollama#logger#Debug("UpdatePreview: suggestion='".a:suggestion."'")
    if !empty(a:suggestion)
        let s:suggestion = a:suggestion
        let text = split(s:suggestion, "\r\n\\=\\|\n", 1)
        if empty(text[-1])
            call remove(text, -1)
        endif
        if empty(text) || !s:has_ghost_text
            return ollama#ClearPreview()
        endif
        let annot= ''
        call ollama#ClearPreview()
        call prop_add(line('.'), col('.'), {'type': s:hlgroup, 'text': text[0]})
        for line in text[1:]
            call prop_add(line('.'), 0, {'type': s:hlgroup, 'text_align': 'below', 'text': line})
        endfor
        if !empty(annot)
            call prop_add(line('.'), col('$'), {'type': s:annot_hlgroup, 'text': ' ' . annot})
        endif
    else
        call ollama#ClearPreview()
    endif
endfunction

function! ollama#ClearPreview()
    call ollama#logger#Debug("ClearPreview")
    call prop_remove({'type': s:hlgroup, 'all': v:true})
    call prop_remove({'type': s:annot_hlgroup, 'all': v:true})
endfunction

function! s:KillJob()
    try
        if s:job isnot v:null
            call ollama#logger#Debug("Killing existing job.")
            let s:kill_job = s:job
            call job_stop(s:job, "kill")
        endif
    catch
        call ollama#logger#Error("KillJob failed")
    endtry
endfunction

function! s:KillTimer()
    try
        if s:timer_id != -1
            call ollama#logger#Debug("Killing existing timer.")
            call timer_stop(s:timer_id)
            let s:timer = -1
        endif
    catch
        call ollama#logger#Error("KillTimer failed")
    endtry
endfunction

function! ollama#Clear() abort
    call ollama#logger#Debug("Clear")
    call s:KillTimer()
    call s:KillJob()
    call ollama#ClearPreview()
    unlet! b:_ollama
    return ''
endfunction

function! ollama#Dismiss() abort
    call ollama#logger#Debug("Dismiss")
    call ollama#Clear()
endfunction

function! ollama#InsertSuggestion()
    call ollama#logger#Debug("InsertSuggestion")
    if !empty(s:suggestion)
        let l:current_col = col('.')
        let l:line = getline('.')
        let l:before_cursor = strpart(l:line, 0, l:current_col - 1)
        let l:after_cursor = strpart(l:line, l:current_col - 1)
        let l:text = split(s:suggestion, "\r\n\\=\\|\n", 1)

        " Get the current indentation level
        let l:indent = indent(line('.'))
        let l:indent = 0

        " Insert the first line with current cursor position
        let l:new_line = l:before_cursor . l:text[0] . l:after_cursor
        call setline('.', l:new_line)

        " Insert remaining lines with proper indentation
        let l:row = line('.')
        for l:idx in range(1, len(l:text)-1)
            let l:indented_line = repeat(' ', l:indent) . l:text[l:idx]
            call append(l:row + l:idx - 1, l:indented_line)
        endfor

        " Move the cursor to the end of the inserted text
        call cursor(l:row + len(l:text) - 1, col('.') + len(l:text[-1]))

        call ollama#ClearPreview()
        let s:suggestion = ''
    endif
    return '\t'
endfunction

function ollama#IsEnabled() abort
    if exists('g:ollama_enabled') && g:ollama_enabled == 1
        return 1
    else
        return 0
    endif
endfunction

" Enables the plugin. If it is already enabled, does nothing.
function ollama#Enable() abort
    if !exists('g:ollama_enabled') || g:ollama_enabled != 1
        let g:ollama_enabled = 1
        echo "Vim-Ollama is enabled."
    endif
endfunction

" Disables the plugin. If it is already disabled, does nothing.
function ollama#Disable() abort
    if exists('g:ollama_enabled') && g:ollama_enabled == 1
        unlet g:ollama_enabled
        echo "Vim-Ollama is disabled."
    endif
endfunction

" Toggle the enabled state of the plugin.
function ollama#Toggle() abort
    if ollama#IsEnabled()
        call ollama#Disable()
    else
        call ollama#Enable()
    endif
endfunction

" Provide different commands: enable, disable, help
function ollama#Command(command) abort
    if a:command == 'enable'
        call ollama#Enable()
    elseif a:command == 'disable'
        call ollama#Disable()
    else
        echo "Usage: Ollama <enable|disable>"
    endif
endfunction


