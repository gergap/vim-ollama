" autoload/ollama.vim
scriptencoding utf-8

let s:timer_id = -1
let s:suggestion = ''
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
    if s:timer_id != -1
        call timer_stop(s:timer_id)
    endif
    let s:timer_id = timer_start(g:ollama_debounce_time, 'ollama#GetSuggestion')
endfunction

function! ollama#GetSuggestion(timer)
    let l:current_line = getline('.')
    let l:current_col = col('.')
    let l:prefix = strpart(l:current_line, 0, l:current_col - 1)
    let l:command = printf('python3 %s/python/ollama.py %s', expand('<sfile>:h:h'), g:ollama_api_url)
    let l:suggestion = system(l:command, l:prefix)
    call ollama#UpdatePreview(l:suggestion)
endfunction

function! ollama#UpdatePreview(suggestion)
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
    call prop_remove({'type': s:hlgroup, 'all': v:true})
    call prop_remove({'type': s:annot_hlgroup, 'all': v:true})
endfunction

function! ollama#Clear() abort
    if s:timer_id != -1
        "call timer_stop(remove(g:, '_ollama_timer'))
        call timer_stop(s:timer_id)
    endif
    "if exists('b:_ollama')
    "    call copilot#client#Cancel(get(b:_ollama, 'first', {}))
    "    call copilot#client#Cancel(get(b:_ollama, 'cycling', {}))
    "endif
    call s:UpdatePreview()
    unlet! b:_ollama
    return ''
endfunction

function! ollama#Dismiss() abort
    call ollama#Clear()
    call ollama#UpdatePreview()
endfunction

function! ollama#InsertSuggestion()
    if !empty(s:suggestion)
        let l:current_col = col('.')
        let l:line = getline('.')
        let l:before_cursor = strpart(l:line, 0, l:current_col - 1)
        let l:after_cursor = strpart(l:line, l:current_col - 1)
        let l:text = split(s:suggestion, "\r\n\\=\\|\n", 1)

        " Get the current indentation level
        let l:indent = indent(line('.'))

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
