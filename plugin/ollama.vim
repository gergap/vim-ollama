" plugin/ollama.vim
" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
if exists('g:loaded_ollama')
    finish
endif
let g:loaded_ollama = 1

if v:version < 800 || !exists('##InsertLeavePre')
    finish
endif

" Default settings
if !exists('g:ollama_enabled')
    let g:ollama_enabled = 1
endif
if !exists('g:ollama_host')
    let g:ollama_host = 'http://localhost:11434'
endif
if !exists('g:ollama_model')
    " default code completion model
    let g:ollama_model = 'codellama:code'
endif
if !exists('g:ollama_chat_model')
    " default chat model
    let g:ollama_chat_model = 'llama3'
endif
if !exists('g:ollama_model_options')
    " default model options
    let g:ollama_model_options = {
                \ 'temperature': 0,
                \ 'top_p': 0.95
                \ }
endif
if !exists('g:ollama_debounce_time')
    let g:ollama_debounce_time = 500
endif

if !exists('g:ollama_timeout')
    let g:ollama_timeout = 10
endif

" Defines the color scheme for ollama suggestions
function! s:ColorScheme() abort
    if &t_Co == 256
        hi def OllamaSuggestion guifg=#808080 ctermfg=244
    else
        hi def OllamaSuggestion guifg=#808080 ctermfg=12
    endif
    hi def link OllamaAnnotation MoreMsg
endfunction

function! s:HandleTabCompletion() abort
    if &buftype == 'prompt'
        " ignore tab in chat buffer
        return "\<Tab>"
    endif
    let suggestion = ollama#InsertSuggestion()
    if suggestion != '\t'
        " AI suggestion was inserted
        return ''
    endif
    call ollama#logger#Info("Forward <tab> to original mapping: ". string(g:ollama_original_tab_mapping))

    " fallback to default tab completion if no suggestion was inserted
    if exists('g:ollama_original_tab_mapping') && !empty(g:ollama_original_tab_mapping)
        if g:ollama_original_tab_mapping.rhs =~# '^<Plug>'
            call ollama#logger#Info("<tab> feedkeys")
            call feedkeys("\<Plug>" . matchstr(g:ollama_original_tab_mapping.rhs, '^<Plug>\zs.*'), 'm')
            return ''
        endif
        " If no completion and there is an original <Tab> mapping, execute it
        if g:ollama_original_tab_mapping.expr
            " rhs is an expression
            call ollama#logger#Info("<tab> expression")
            return "\<C-R>=" . g:ollama_original_tab_mapping.rhs . "\<CR>"
        else
            " rhs is a string
            call ollama#logger#Info("<tab> string")
            let tab_fallback = substitute(json_encode(g:ollama_original_tab_mapping.rhs), '<', '\\<', 'g')
            return eval(tab_fallback)
        endif
    else
        " Default to a literal tab if there's no original mapping
        call ollama#logger#Info("<tab> literal")
        return "\<Tab>"
    endif
endfunction

" Map <Tab> to insert suggestion
function! s:MapTab() abort
    " Save the existing <Tab> mapping in insert mode
    if !exists('g:ollama_original_tab_mapping') || empty(g:ollama_original_tab_mapping)
        call ollama#logger#Info("Mapping <tab> to vim-ollama")
        let g:ollama_original_tab_mapping = maparg('<Tab>', 'i', 0, 1)
        call ollama#logger#Info("Original Mapping: " . string(g:ollama_original_tab_mapping))
    else
        call ollama#logger#Info("Not mapping <tab> to vim-ollama, because mapping already exists")
    endif

    " Create plugs
    inoremap <Plug>(ollama-dismiss)        <Cmd>call ollama#Dismiss()<CR>
    inoremap <Plug>(ollama-tab-completion) <C-R>=<SID>HandleTabCompletion()<CR>
    inoremap <Plug>(ollama-insert-line)    <Cmd>call ollama#InsertNextLine()<CR>
    inoremap <Plug>(ollama-insert-word)    <Cmd>call ollama#InsertNextWord()<CR>
    vnoremap <Plug>(ollama-review)         <Cmd>call ollama#review#Review()<CR>
    nnoremap <Plug>(ollama-toggle)         <Cmd>call ollama#Toggle()<CR>

    " Setup default mappings
    imap <silent> <C-]>     <Plug>(ollama-dismiss)
    imap <silent> <Tab>     <Plug>(ollama-tab-completion)
    imap <silent> <M-Right> <Plug>(ollama-insert-line)
    imap <silent> <M-C-Right> <Plug>(ollama-insert-word)
    vmap <silent> <leader>r <Plug>(ollama-review)
endfunction

" Create autocommand group
augroup ollama
    autocmd!
    autocmd CursorMovedI          * if &buftype != 'prompt' | call ollama#Schedule() | endif
    autocmd InsertLeave           * if &buftype != 'prompt' | call ollama#Dismiss() | endif
    autocmd VimEnter              * call s:MapTab()
    autocmd BufDelete             * call ollama#review#BufDelete(expand("<abuf>"))
    autocmd ColorScheme,VimEnter  * call s:ColorScheme()
augroup END

call s:ColorScheme()

" Load autoload functions
runtime autoload/ollama.vim

" Define a command to start the chat session
command! -range=% OllamaReview <line1>,<line2>call ollama#review#Review()
command! -range=% OllamaSpellCheck <line1>,<line2>call ollama#review#SpellCheck()
command! -nargs=1 -range=% OllamaTask <line1>,<line2>call ollama#review#Task(<f-args>)
command! OllamaChat call ollama#review#Chat()
command! -nargs=1 Ollama call ollama#Command(<f-args>)
