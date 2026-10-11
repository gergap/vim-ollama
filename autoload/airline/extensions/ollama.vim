" SPDX-License-Identifier: GPL-3.0-or-later
" Context usage part for Vim Airline.

function! airline#extensions#ollama#init(ext) abort
    if !exists('*airline#parts#define_function')
        return
    endif
    call airline#parts#define_function('ollama_context', 'ollama#edit#ContextStatus')
endfunction
