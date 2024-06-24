" plugin/ollama.vim
if exists('g:loaded_ollama')
    finish
endif
let g:loaded_ollama = 1

if v:version < 800 || !exists('##InsertLeavePre')
    finish
endif

" Default settings
if !exists('g:ollama_host')
    let g:ollama_host = 'http://tux:11434'
endif
if !exists('g:ollama_model')
    let g:ollama_model = 'codellama:code'
    let g:ollama_model = 'llama3'
endif
if !exists('g:ollama_debounce_time')
    let g:ollama_debounce_time = 500
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

" Map <Tab> to insert suggestion
function! s:MapTab() abort
    inoremap <silent> <Tab> <C-R>=ollama#InsertSuggestion()<CR>
    vmap <silent> <leader>r :call ollama#review#Review()<CR>
endfunction

" Create autocommand group
augroup ollama
    autocmd!
    autocmd CursorMovedI          * call ollama#Schedule()
    autocmd InsertLeave           * call ollama#Dismiss()
    autocmd ColorScheme,VimEnter  * call s:ColorScheme()
augroup END

call s:ColorScheme()
call s:MapTab()

" Load autoload functions
runtime autoload/ollama.vim


" Define a command to start the chat session
command! -nargs=1 OllamaReview call ollama#review#Review(<f-args>)
command! -nargs=1 OllamaChat call ollama#review#Chat(<f-args>)
