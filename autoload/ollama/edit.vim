" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
" avoid starting a 2nd edit job while one is in progress
let g:edit_in_progress = 0

" Define the VimScript callback function
" This will be called from python when to operations is 'done'
" or aborted with 'error'
function! ollama#edit#EditCodeDone(status)
    if a:status == "done"
        echom "Code editing completed!"
    elseif a:status == "error"
        echom "Error occurred during code editing."
    endif
    " stop progress timer
    call timer_stop(b:timer)
    let b:timer = 0
    " close progress popup window
    call popup_close(b:popup)
    let b:popup = 0
    " reset status
    let g:edit_in_progress = 0
    redraw!
endfunction

" Give user visual feedback about job that is in progress
function! ollama#edit#UpdateProgress(popup) abort
    " Cycle through progress states
    let g:progress_indicator = (g:progress_indicator + 1) % 4
    let l:states = ['|', '/', '-', '\']
    call popup_settext(a:popup, 'Processing ' . l:states[g:progress_indicator])
endfunction

" Start the Python function and return immediately
function! ollama#edit#EditCode(request)
    if exists('g:edit_in_progress') && g:edit_in_progress
        return
    endif
    echomsg "Calling ollama#edit#EditCode with request: " . a:request
    let l:model_options = substitute(json_encode(g:ollama_chat_options), "\"", "\\\"", "g")

    " Call the python code to edit the code via Ollama.
    " The python code starts a worker thread so that the GUI stays responsive
    " while waiting for the response.
    python3 << EOF
import vim

# Process arguments
request = vim.eval('a:request')
firstline = vim.eval('a:firstline')
lastline = vim.eval('a:lastline')
# Access global Vim variables
settings = {
    'url': vim.eval('g:ollama_host'),
    'model': vim.eval('g:ollama_model'),
    'options': vim.eval('l:model_options')
}
# Now pass these settings to the CodeEditor function
CodeEditor.start_vim_edit_code(request, firstline, lastline, settings, 'ollama#edit#EditCodeDone')
EOF

    " Create a floating window for progress
    let l:popup_options = {
    \   'pos': 'center',
    \   'minwidth': 20,
    \   'minheight': 1,
    \   'time': 0,
    \   'zindex': 10,
    \   'border': [],
    \   'padding': [0, 1, 0, 1]
    \ }
    let l:popup = popup_create('Processing...', l:popup_options)"
    let b:popup = l:popup
    let g:progress_indicator = 0
    let g:edit_in_progress = 1

    " Set up a timer to check progress periodically
    let b:timer = timer_start(100, { -> ollama#edit#UpdateProgress(l:popup) }, {'repeat': -1})
endfunction

