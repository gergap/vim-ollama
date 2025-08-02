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
        echoe "Error occurred during code editing."
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

" Callback wrapper which delegates the call to Python
function! ollama#edit#DialogCallback(id, result)
    python3 << EOF
import vim
try:
    id = int(vim.eval('a:id'))
    result = int(vim.eval('a:result'))
    CodeEditor.DialogCallback(id, result)
except Exception as e:
    exc_type, exc_value, tb = sys.exc_info()
    print(f"Error in DialogCallback: {str(e)} at line {tb.tb_lineno} of {sys._getframe(0).f_code.co_filename}")
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command(f'echon "Error in delegating callback: {str(e)}"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass
EOF
endfunction

" Give user visual feedback about job that is in progress
function! ollama#edit#UpdateProgress(popup)
    " Cycle through progress states
    let g:progress_indicator = (g:progress_indicator + 1) % 4
    let l:states = ['|', '/', '-', '\']
    call popup_settext(a:popup, 'Processing ' .. l:states[g:progress_indicator])

    " Poll the job status, because Vim calls from worker threads produce
    " segfaults
    python3 << EOF
import sys
import json
import vim
try:
    buf = vim.current.buffer
    result, groups = CodeEditor.get_job_status()
    if result != 'InProgress':
        # Report changes in code done to user interface
        vim.command('call ollama#edit#EditCodeDone("' + str(result) + '")')
        use_inline_diff = int(vim.eval('g:ollama_use_inline_diff'))

        if groups:
            if use_inline_diff:
                CodeEditor.ShowAcceptDialog("ollama#edit#DialogCallback", 0)
            else:
                vim.command("echo 'Applied changes.'")
        else:
            vim.command('call popup_notification("The LLM response did not contain any changes", #{ pos: "center"})')

except Exception as e:
    exc_type, exc_value, tb = sys.exc_info()
    print(f"Error updating progress: {str(e)} at line {tb.tb_lineno} of {sys._getframe(0).f_code.co_filename}")
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command(f'echon "Error updating progress: {str(e)}"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass

EOF
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Internal Helper function for offloading logic to Python
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! s:EditCodeInternal(request, first_line, last_line) abort
    if exists('g:edit_in_progress') && g:edit_in_progress
        return
    endif
    let l:model_options = substitute(json_encode(g:ollama_edit_options), "\"", "\\\"", "g")
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    " Call the python code to edit the code via Ollama.
    " The python code starts a worker thread so that the GUI stays responsive
    " while waiting for the response.
    python3 << EOF
import vim

# Process arguments
request = vim.eval('a:request')
firstline = vim.eval('a:first_line')
lastline = vim.eval('a:last_line')
log_level = int(vim.eval('l:log_level'))
# Access global Vim variables
settings = {
    'url': vim.eval('g:ollama_host'),
    'model': vim.eval('g:ollama_edit_model'),
    'options': vim.eval('l:model_options')
}
CodeEditor.SetLogLevel(log_level)
# Now pass these settings to the CodeEditor function
CodeEditor.start_vim_edit_code(request, firstline, lastline, settings)
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

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Start the Python function and return immediately (Range command)
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#EditCode(request)
    call s:EditCodeInternal(a:request, a:firstline, a:lastline)
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Popup edit prompt, instead of Edit command
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#EditPrompt()
    " Initialize line numbers
    let l:firstline = 0
    let l:lastline = 0

    if mode() ==# 'v' || mode() ==# 'V' || mode() ==# "\<C-V>"
        " Get the first and last line of the selection
        let l:firstline = line("'<")
        let l:lastline = line("'>")
    else
        let l:firstline = 1
        let l:lastline = line('$')
    endif

    " Extract the selected text or the whole file content
    let l:selected_text = join(getline(l:firstline, l:lastline), "\n")

    " Show a prompt to enter the user request
    let l:prompt = input('Enter prompt: ', '', 'file')

    " If the prompt is empty, exit
    if empty(l:prompt)
        return
    endif

    " Call the ollama#edit#EditCodeInternal function with the request and selected context
    call s:EditCodeInternal(l:prompt, l:firstline, l:lastline)
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Accept All Changes
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#AcceptAll()
    python3 << EOF
import vim
try:
    CodeEditor.AcceptAllChanges()
except Exception as e:
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command('echo "Error accepting changes: ' + str(e) + '"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass
EOF
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Reject All Changes
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#RejectAll()
    python3 << EOF
import vim
try:
    CodeEditor.RejectAllChanges()
except Exception as e:
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command('echo "Error rejecting changes: ' + str(e) + '"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass
EOF
endfunction

