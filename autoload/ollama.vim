" autoload/ollama.vim
let s:ns_id = nvim_create_namespace('ollama.suggestion')
let s:timer_id = -1
let s:suggestion = ''

function! ollama#schedule()
  if s:timer_id != -1
    call timer_stop(s:timer_id)
  endif
  let s:timer_id = timer_start(g:ollama_debounce_time, 'ollama#get_suggestion')
endfunction

function! ollama#get_suggestion(timer)
  let l:current_line = getline('.')
  let l:current_col = col('.')
  let l:prefix = strpart(l:current_line, 0, l:current_col - 1)
  let l:command = printf('python3 %s/python/ollama.py %s', expand('<sfile>:h:h'), g:ollama_api_url)
  let l:suggestion = system(l:command, l:prefix)
  call ollama#show_suggestion(l:suggestion)
endfunction

function! ollama#show_suggestion(suggestion)
  if !empty(a:suggestion)
    let s:suggestion = a:suggestion
    let l:current_col = col('.')
    call nvim_buf_clear_namespace(0, s:ns_id, 0, -1)
    call nvim_buf_set_extmark(0, s:ns_id, line('.'), l:current_col - 1, {'virt_text': [[s:suggestion, 'Comment']]})
  else
    call ollama#clear_preview()
  endif
endfunction

function! ollama#clear_preview()
  call nvim_buf_clear_namespace(0, s:ns_id, 0, -1)
endfunction

function! ollama#insert_suggestion()
  if !empty(s:suggestion)
    let l:current_col = col('.')
    let l:line = getline('.')
    let l:before_cursor = strpart(l:line, 0, l:current_col - 1)
    let l:after_cursor = strpart(l:line, l:current_col - 1)
    call setline('.', l:before_cursor . s:suggestion . l:after_cursor)
    call cursor(line('.'), l:current_col + len(s:suggestion))
    call ollama#clear_preview()
    let s:suggestion = ''
  endif
  return ''
endfunction

