" plugin/ollama.vim
if exists('g:loaded_ollama')
  finish
endif
let g:loaded_ollama = 1

" Default settings
if !exists('g:ollama_api_url')
  let g:ollama_api_url = 'http://tux:5000/api/suggestions'
endif
if !exists('g:ollama_debounce_time')
  let g:ollama_debounce_time = 300
endif

" Load autoload functions
runtime autoload/ollama.vim

" Create autocommand group
augroup ollama
  autocmd!
  autocmd CursorMovedI * call ollama#schedule()
  autocmd InsertLeave * call ollama#clear_preview()
augroup END

" Map <Tab> to insert suggestion
inoremap <silent> <Tab> <C-R>=ollama#insert_suggestion()<CR>

