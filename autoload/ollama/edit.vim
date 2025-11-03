" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
" avoid starting a 2nd edit job while one is in progress
let g:edit_in_progress = 0
" stores winid for each popid to figure out what popup was clicked
" key=changeId, value=winId
let s:popups = {}

function! ollama#edit#test() abort
    call s:ShowAcceptButtons(13, 0)
    call s:ShowAcceptButtons(18, 1)
    call s:ShowAcceptButtons(24, 2)
endfunction

function! s:DebugPrintPopups() abort
    for [key, Value] in items(s:popups)
        call ollama#logger#Debug("popup " ..key .. "=" .. string(Value))
    endfor
endfunction

" Creates a text property of type OllamaPopupMarker at the given line
" The changeId will be used as property Id
function! s:CreatePopupMarker(lnum, changeId) abort
    " Add a text property to the given line
    let propId = a:changeId  " use changeId as unique id
    " get content at given line
    let content = getline(a:lnum)
    let length = strlen(content)
    if length == 0
        let length = 1
    endif
    call ollama#logger#Debug('prop_add at line '..a:lnum..', id='..propId..', length='..length)
"    let ret = prop_add(a:lnum, 1, #{type: 'OllamaPopupMarker', id: propId, length: length})
    let ret = prop_add(a:lnum, length, #{type: 'OllamaPopupMarker', id: propId})
    call ollama#logger#Debug('ret='..ret)
endfunction

" Deletes the Popup Marker for the given changeId
function! s:DeletePopupMarker(changeId) abort
    let propId = a:changeId
    call prop_remove(#{type: 'OllamaPopupMarker', id: propId, both: 1})
endfunction

" Function to show Accept/Reject popup at a given line
function! s:ShowAcceptButtons(lnum, changeId) abort
    call ollama#logger#Debug('Showing Accept/Reject popup for changeId='..a:changeId..' at line='..a:lnum)
    call s:CreatePopupMarker(a:lnum, a:changeId)
    let propId = a:changeId

    " Create the popup text with two buttons
"    let lines = ['[Accept]  [Reject]']
    let lines = ['✅  ❌']

    " Callback for when the popup closes
    function! s:PopupCallback(winid, result) abort
        call ollama#logger#Debug('PopupCallback winid='..a:winid..', result='..a:result)
        " Get the options used to create the popup
        let opts = popup_getoptions(a:winid)
        " trace all options
"        for [key, Value] in items(opts)
"            echom key .. "=" .. string(Value)
"        endfor

        " The 'textpropid' is stored in opts
        if has_key(opts, 'textpropid')
            let l:change_id = opts.textpropid
            " remove entry from s:popup
            call remove(s:popups, l:change_id)
            if a:result == 0
                call ollama#logger#Debug('Accepting change '..l:change_id)
                call ollama#edit#AcceptChange(l:change_id)
            elseif a:result == 1
                call ollama#logger#Debug('Rejecting change '..l:change_id)
                call ollama#edit#RejectChange(l:change_id)
            else
                echoerr "Unexpected result "..a:result
            endif
        else
            echoerr "Cannot determine ChangeId for popup"
        endif
    endfunction

    " Filter function to handle clicks
    " Return 0: Vim will continue to handle the event
    " Return 1: event was handled and can be discarded
    function! s:PopupFilter(winid, key) abort
        " Ignore empty keys
        if a:key ==# ''
            return 0
        endif

"        let hex = join(map(split(a:key, '\zs'), {idx, val -> printf('%02X', char2nr(val))}), ' ')
"        call ollama#logger#Debug('PopupFilter:'..a:winid..' key='..hex)

        " handle raw terminal mouse codes
        if (a:key ==# "\x80\xFD\x2E") || a:key =~? '<LeftMouse>'
            let mp = getmousepos()
"            call ollama#logger#Debug('mp: winid='..mp.winid..' col='..mp.column..' line='.mp.line)
            " only handle mouse clicks when on the correct line.
            " mp.col/line is relative to winid
            if mp.winid != a:winid || mp.line != 1 " our popup only has one line
                return 0 " call other event filters until we found the right one
            endif
            " Determine which button was clicked
            if mp.column < 3
                call ollama#logger#Debug('Accept with 0 for windid '..a:winid)
                call popup_close(a:winid, 0) " Accept
                return 1
            elseif mp.column < 7
                call ollama#logger#Debug('Reject with 1 for windid '..a:winid)
                call popup_close(a:winid, 1) " Reject
                return 1
            endif
            call ollama#logger#Debug('Ingore event for windid '..a:winid)
            return 0
        endif
        " forward events to Vim
        return 0
    endfunction

    call ollama#logger#Debug('Create popup at line '..a:lnum..' for propId '..propId)
    " Create the popup attached to the text property
    let popup_winid = popup_create(lines, #{
        \ textprop: 'OllamaPopupMarker',
        \ textpropid: propId,
        \ line: 1,
        \ col: 1,
        \ pos: 'botleft',
        \ padding: [0,1,0,1],
        \ border: [0,0,0,0],
        \ highlight: 'OllamaPopup',
        \ close: 'none',
        \ filter: function('s:PopupFilter'),
        \ filter_mode: 'n',
        \ callback: function('s:PopupCallback')
        \ })
    call ollama#logger#Debug('New winId for propId '..propId..' is '..popup_winid)
    let s:popups[propId] = popup_winid
endfunction

function! ollama#edit#ShowAcceptButtons(lnum, change_id)
    call s:ShowAcceptButtons(a:lnum, a:change_id)
endfunction

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
    call popup_close(b:popup_progress)
    let b:popup_progress = 0
    " reset status
    let g:edit_in_progress = 0
    " Show Winbar with Accept/Deny buttons
    nnoremenu 1.10 WinBar.Accept\ All :OllamaAcceptAll<CR>
    nnoremenu 1.20 WinBar.Reject\ All :OllamaRejectAll<CR>
    redraw!
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
    result, groups, errormsg = CodeEditor.get_job_status()
    if result != 'InProgress':
        # Report changes in code done to user interface
        vim.command('call ollama#edit#EditCodeDone("' + str(result) + '")')
        use_inline_diff = int(vim.eval('g:ollama_use_inline_diff'))

        if result == 'Error':
            if errormsg is None:
                errormsg = 'Unknown'
            vim.command(f'echom "Error updating progress: {errormsg}"')
            vim.command('call popup_notification("'+errormsg+'", #{ pos: "center"})')
        else:
            # Done
            if groups and use_inline_diff:
                for change_id, g in enumerate(groups):
                    start_line = g.start_line
                    if start_line > 0:
                        vim.command(f'call ollama#edit#ShowAcceptButtons({start_line}, {change_id})')
            else:
                vim.command('call popup_notification("The LLM response did not contain any changes", #{ pos: "center"})')
            vim.command('redraw!')

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
baseurl = vim.eval('g:ollama_host')
provider = vim.eval('g:ollama_edit_provider')
credentialname = None
if provider.startswith('openai'):
    baseurl = vim.eval('g:ollama_openai_baseurl')
    credentialname = vim.eval('g:ollama_openai_credentialname')
elif provider == 'mistral':
    baseurl = vim.eval('g:ollama_mistral_baseurl')
    credentialname = vim.eval('g:ollama_mistral_credentialname')
# Access global Vim variables
settings = {
    'url': baseurl,
    'provider': provider,
    'model': vim.eval('g:ollama_edit_model'),
    'options': vim.eval('l:model_options')
}
CodeEditor.SetLogLevel(log_level)
# Now pass these settings to the CodeEditor function
CodeEditor.start_vim_edit_code(request, firstline, lastline, settings, credentialname)
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
    let b:popup_progress = l:popup
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

function! ollama#edit#AcceptChange(index)
    call s:DeletePopupMarker(a:index)
    if len(s:popups) == 0
        call ollama#logger#Debug('all popups closed')
        " remove menubar
        aunmenu WinBar
    endif
    python3 << EOF
import vim
try:
    index = vim.eval('a:index')
    CodeEditor.AcceptChange(int(index))
except Exception as e:
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command('echo "Error accepting change: ' + str(e) + '"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass
EOF
endfunction

function! ollama#edit#RejectChange(index)
    echom 'ollama#edit#RejectChange()'
    call s:DeletePopupMarker(a:index)
    if len(s:popups) == 0
        call ollama#logger#Debug('all popups closed')
        " remove menubar
        aunmenu WinBar
    endif
    python3 << EOF
import vim
try:
    index = vim.eval('a:index')
    CodeEditor.RejectChange(int(index))
except Exception as e:
    # Handle or print the exception here.
    vim.command('echohl ErrorMsg')
    vim.command('echo "Error rejecting change: ' + str(e) + '"')
    vim.command('echon ""')  # To display a newline.
finally:
    pass
EOF
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Accept All Changes
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#AcceptAll()
    " iterate over all popups and accept them
    for [changeId, winId] in items(s:popups)
        call popup_close(winId, 0)
    endfor
    let s:popup = {}
    " remove menubar
    aunmenu WinBar
endfunction

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Reject All Changes
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
function! ollama#edit#RejectAll()
    echom 'ollama#edit#RejectAll()'
    " iterate over all popups and reject them
    for [changeId, winId] in items(s:popups)
        call popup_close(winId, 1)
    endfor
    let s:popup = {}
    " remove menubar
    aunmenu WinBar
endfunction

