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
if !exists('g:ollama_chat_systemprompt')
    " empty means no system prompt, we use th built-in one
    let g:ollama_chat_systemprompt = ''
endif
if !exists('g:ollama_model_options')
    " default model options for code completion
    " Predict less -> faster response time
    let g:ollama_model_options = {
                \ 'temperature': 0,
                \ 'top_p': 0.95,
                \ 'num_predict': 128
                \ }
endif
if !exists('g:ollama_chat_options')
    " default model options for chat and code editing tasks
    " we need more prediction for larger tasks
    let g:ollama_chat_options = {
                \ 'temperature': 0,
                \ 'top_p': 0.95,
                \ 'num_predict': 4096,
                \ 'num_ctx': 8192,
                \ 'keep_alive': 1800,
                \ }
endif
if !exists('g:ollama_debounce_time')
    let g:ollama_debounce_time = 500
endif
if !exists('g:ollama_context_lines')
    let g:ollama_context_lines = 30
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
    nnoremap <Plug>(ollama-accept-changes) <Cmd>call ollama#edit#AcceptCurrent()<CR>
    nnoremap <Plug>(ollama-reject-changes) <Cmd>call ollama#edit#RejectCurrent()<CR>
    nnoremap <Plug>(ollama-accept-all-changes) <Cmd>call ollama#edit#AcceptAll()<CR>
    nnoremap <Plug>(ollama-reject-all-changes) <Cmd>call ollama#edit#RejectAll()<CR>
    nnoremap <Plug>(ollama-edit)           <Cmd>call ollama#edit#EditPrompt()<CR>
    vnoremap <Plug>(ollama-edit)           <Cmd>call ollama#edit#EditPrompt()<CR>

    " Setup default mappings
    imap <silent> <C-]>     <Plug>(ollama-dismiss)
    imap <silent> <Tab>     <Plug>(ollama-tab-completion)
    imap <silent> <M-Right> <Plug>(ollama-insert-line)
    imap <silent> <M-C-Right> <Plug>(ollama-insert-word)
    vmap <silent> <leader>r <Plug>(ollama-review)
    nmap <silent> <C-M-y> <Plug>(ollama-accept-changes)
    nmap <silent> <C-M-n> <Plug>(ollama-reject-changes)
    nmap <silent> <C-Y> <Plug>(ollama-accept-all-changes)
    nmap <silent> <C-N> <Plug>(ollama-reject-all-changes)
    nmap <silent> <C-I> <Plug>(ollama-edit)
    vmap <silent> <C-I> <Plug>(ollama-edit)
endfunction

function! s:Init() abort
    call ollama#setup#Init()
    call s:MapTab()
endfunction

" Create autocommand group
augroup ollama
    autocmd!
    autocmd CursorMovedI          * if &buftype != 'prompt' | call ollama#Schedule() | endif
    autocmd InsertLeave           * if &buftype != 'prompt' | call ollama#Dismiss() | endif
    autocmd VimEnter              * call s:Init()
    autocmd BufDelete             * call ollama#review#BufDelete(expand("<abuf>"))
    autocmd ColorScheme,VimEnter  * call s:ColorScheme()
    autocmd VimEnter              * call ollama#setup#Init()
augroup END

" Set omnifunc for the current file type
augroup OllamaCompletion
    autocmd!
    autocmd FileType vim.ollama setlocal omnifunc=ollama#config#OmniComplete
    autocmd FileType vim.ollama let b:ollama_enabled=0
    " trigger completion when : is pressed
    autocmd FileType vim.ollama inoremap <silent> <buffer> : :<C-X><C-O>
    autocmd FileType vim.ollama inoremap <silent> <buffer> <expr> ' ollama#config#TriggerModelCompletion()
augroup END

call s:ColorScheme()

" Load autoload functions
runtime autoload/ollama.vim

" Define a command to start the chat session
command! -range=% OllamaReview <line1>,<line2>call ollama#review#Review()
command! -range=% OllamaSpellCheck <line1>,<line2>call ollama#review#SpellCheck()
command! -nargs=1 -range=% OllamaTask <line1>,<line2>call ollama#review#Task(<f-args>)
command! -nargs=1 -range=% OllamaEdit <line1>,<line2>call ollama#edit#EditCode(<f-args>)
command! OllamaChat call ollama#review#Chat()
command! -nargs=1 -complete=customlist,ollama#CommandComplete Ollama call ollama#Command(<f-args>)

" Define new signs for diffs
sign define NewLine text=+ texthl=DiffAdd
sign define ChangedLine text=~ texthl=DiffChange
sign define DeletedLine text=- texthl=DiffDelete
" Define inline diff property types
highlight OllamaButton ctermfg=White ctermbg=Blue guifg=#FFFFFF guibg=#0000FF
call prop_type_add("OllamaDiffDel", {"highlight": "DiffDelete"})
call prop_type_add("OllamaDiffAdd", {"highlight": "DiffAdd"})
call prop_type_add("OllamaButton", {"highlight": "OllamaButton"})

function! PluginInit() abort
    " Add the plugin's python directory to Python's sys.path
    python3 << EOF
import sys
import os

# Adjust the path to point to the plugin's python directory
plugin_python_path = os.path.join(vim.eval("expand('<sfile>:p:h:h')"), "python")
if plugin_python_path not in sys.path:
    sys.path.append(plugin_python_path)

# Import your CodeEditor module
import CodeEditor
import VimHelper
EOF
endfunction

call PluginInit()
