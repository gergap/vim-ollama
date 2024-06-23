" autoload/ollama.vim
scriptencoding utf-8

" numeric timer Id
let s:timer_id = -1
" a running REST API job
let s:job = v:null
let s:kill_job = v:null
" fill-in-the-middle
let s:prefix_text = '<PRE> '
let s:middle_text = ' <MID>'
let s:suffix_text = ' <SUF>'
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
    call ollama#logger#Debug("Scheduling timer...")
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
    let s:job = v:null
    let s:prompt = ''
endfunction

function! ollama#GetSuggestion(timer)
    call ollama#logger#Debug("GetSuggestion")
    " reset timer handle when called
    let s:timer_id = -1
    let l:current_line = line('.')
    let l:current_col = col('.')
    let l:context_lines = 30

    " Get the lines before and after the current line
    let l:prefix_lines = getline(max([1, l:current_line - l:context_lines]), l:current_line - 1)
    let l:suffix_lines = getline(l:current_line + 1, min([line('$'), l:current_line + l:context_lines]))

    " Combine prefix lines and current line's prefix part
    let l:prefix = join(l:prefix_lines, "\n") . "\n" . strpart(getline('.'), 0, l:current_col - 1)
    " Combine suffix lines and current line's suffix part
    let l:suffix = strpart(getline('.'), l:current_col - 1) . "\n" . join(l:suffix_lines, "\n")

    " Create the prompt using the specified syntax
    let l:prompt = s:prefix_text . l:prefix . s:suffix_text . l:suffix . s:middle_text

    " Adjust the command to use the prompt as stdin input
    let l:command = printf('python3 %s/python/ollama.py -m %s -u %s', expand('<sfile>:h:h'), g:ollama_model, g:ollama_host)
    let l:job_options = {
        \ 'out_mode': 'raw',
        \ 'out_cb': function('s:HandleCompletion'),
        \ 'err_cb': function('s:HandleError'),
        \ 'exit_cb': function('s:HandleExit')
        \ }

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
    if s:job isnot v:null
        let s:kill_job = s:job
        call job_stop(s:job)
        let s:job = v:null
    endif
endfunction

function! s:KillTimer()
    if s:timer_id != -1
        call ollama#logger#Debug("Killing existing timer.")
        call timer_stop(s:timer_id)
        let s:timer = -1
    endif
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
    return ''
endfunction



