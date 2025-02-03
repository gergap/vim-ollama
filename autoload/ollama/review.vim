" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1

" Map a key to send user input to the chatbot
nnoremap <buffer> <silent> <Enter> :call <sid>SendInputToChatBot()<CR>

if !exists('g:ollama_review_logfile')
    let g:ollama_review_logfile = tempname() . '-ollama-review.log'
endif

" Define a function to send user input to the chatbot
function! s:SendInputToChatBot()
    " Get the user input
    let user_input = input(">>> ")

    " Append the user's input to the buffer
    call append(line('$'), user_input)

    " Send the input to the chatbot
    call ch_sendraw(b:chatbot_channel, user_input . "\n")
endfunction

func! ollama#review#KillChatBot()
    call ollama#logger#Debug("KillChatBot")

    " Stop the job if it exists
    if exists("s:job") && type(s:job) == v:t_number
        call job_stop(s:job)
        while job_status(s:job) == 'run'
            sleep 1
        endwhile
    endif
endfunc

func! s:BufReallyDelete(buf)
    call ollama#logger#Debug("BufReallyDelete ".a:buf)
    execute "bwipeout! ".a:buf
endfunc

func! ollama#review#BufDelete(buf)
    call ollama#logger#Debug("BufDelete")
    if a:buf == s:buf
        call ollama#logger#Debug("Deleting buffer ".a:buf)
        " The buffer was closed by :quit or :q!
        call ollama#review#KillChatBot()
        " Undo 'buftype=prompt' and make buffer deletable
        if bufexists(s:buf)
            setlocal buftype=
            setlocal modifiable
        endif
        " We cannot wipe the buffer while being used in autocmd
        call timer_start(10, {-> s:BufReallyDelete(a:buf)})
    endif
endfunc

" Function to find the window containing the buffer
function! s:FindBufferWindow(bufnr)
    for i in range(1, winnr('$'))
        if bufnr(winbufnr(i)) == a:bufnr
            return i
        endif
    endfor
    return -1
endfunction

function! s:StartChat(lines) abort
    " Function handling a line of text that has been typed.
    func! TextEntered(text)
        call ollama#logger#Debug("TextEntered: ".a:text)
        if a:text == ''
            " don't send empty messages
            return
        endif
        " Send the text to a shell with Enter appended.
        call ch_sendraw(s:job, a:text .. "\n")
    endfunc

    " Function handling output from the shell: Add it above the prompt.
    func! GotOutput(channel, msg)
        call ollama#logger#Debug("GotOutput: ".a:msg)
        " Save current buffer and window settings
        let l:current_win = win_getid()
        let l:current_buf = bufnr('%')
        let l:need_restore = 0

        if l:current_buf != s:buf
            call ollama#logger#Debug("switch to chat buffer")
            let l:need_restore = 1
            " Switch to the chat buffer
            execute 'buffer' s:buf
        endif

        " append lines
        let l:lines = split(a:msg, "\n")
        for l:line in l:lines
            " when we received <EOT> start insert mode again
            let l:idx = stridx(l:line, "<EOT>")
            if l:idx != -1
                call ollama#logger#Debug("idx=".l:idx)
                let l:line = strpart(l:line, 0, l:idx)
            endif
            call append(line("$") - 1, l:line)
        endfor

        if l:need_restore == 1
            call ollama#logger#Debug("restore previous buffer")
            " Restore previous buffer and window
            execute 'buffer' l:current_buf
            call win_gotoid(l:current_win)
        endif
    endfunc

    " Function handling output from the shell: Add it above the prompt.
    func! GotErrors(channel, msg)
        call ollama#logger#Debug("GotErrors: ".a:msg)

        let l:bufname = 'stderr'
        let l:bufnr = bufnr(l:bufname)
        if (l:bufnr != -1)
            " buffer already exists
            execute 'buffer' l:bufnr
        else
            " create new error buffer
            execute 'new' l:bufname
        endif

        " Simply append to current buffer
        call append(line("$"), a:msg)
    endfunc

    " Function handling the shell exits: close the window.
    func! JobExit(job, status)
        call ollama#logger#Debug("JobExit: ".a:status)
        " Switch to the chat buffer
        execute 'buffer' s:buf
        " Turn off prompt functionality and make the buffer modifiable
        call prompt_setprompt(s:buf, '')
        setlocal buftype=
        setlocal modifiable
        " output info message
        call append(line("$") - 1, "Chat process terminated with exit code ".a:status)
        call append(line("$") - 1, "Use ':q!' or ':bd!' to delete this buffer and run ':OllamaChat' again to create a new session.")
        stopinsert
    endfunc

    " Redirect job's IO to buffer
    let job_options = {
        \ 'out_cb': function('GotOutput'),
        \ 'err_cb': function('GotErrors'),
        \ 'exit_cb': function('JobExit'),
        \ }

    " Convert plugin debug level to python logger levels
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    " Start the Python script as a job
    let l:command = printf('python3 %s/python/chat.py -m %s -u %s -t %s -l %u',
                \ expand('<script>:h:h:h'),
                \ g:ollama_chat_model, 
                \ g:ollama_host,
                \ g:ollama_timeout,
                \ l:log_level)

    " Start a shell in the background.
    let s:job = job_start(l:command, job_options)

    " Create chat buffer
    let l:bufname = 'Ollama Chat'
    let l:bufnr = bufnr(l:bufname)
    if (l:bufnr != -1)
        " buffer already exists
        let l:chat_win = s:FindBufferWindow(l:bufnr)
        " switch to existing buffer
        if l:chat_win != -1
            execute l:chat_win . 'wincmd w'
        else
            execute 'buffer' l:bufnr
        endif
        " send lines
        if a:lines isnot v:null
            call append(line("$") - 1, a:lines)
            call ch_sendraw(s:job, join(a:lines, "\n") .. "\n")
        endif
        return
    endif

    " Create new chat buffer
    execute 'vnew' l:bufname
    " Set the filetype to ollama-chat
"    setlocal filetype=ollama-chat
    setlocal filetype=markdown
    setlocal buftype=prompt
    " enable BufDelete event when closing buffer usig :q!
    setlocal bufhidden=delete
    setlocal noswapfile
    setlocal modifiable
    setlocal wrap
    let l:buf = bufnr('')
    let s:buf = l:buf
    " Create a channel log so we can see what happens.
    if g:ollama_debug >= 4
        call ch_logfile(g:ollama_review_logfile, 'w')
    endif

    " Add a title to the chat buffer
    call append(0, "Chat with Bot")
    call append(1, "-------------")
    if a:lines isnot v:null
        call append(2, a:lines)
        call ch_sendraw(s:job, join(a:lines, "\n") .. "\n")
    endif

    " connect buffer with job
    call prompt_setcallback(buf, function("TextEntered"))
    eval prompt_setprompt(buf, ">>> ")

    " add key mapping for CTRL-C to terminate the chat script
    execute 'nnoremap <buffer> <C-C> :call ollama#review#KillChatBot()<CR>'
    execute 'inoremap <buffer> <C-C> <esc>:call ollama#review#KillChatBot()<CR>'

    " start accepting shell commands
    startinsert
endfunction

" Creates a chat window with the given prompt and copies the current selection
" into a multiline prompt. The code is formatted using backticks and the
" current filetype.
function! s:StartChatWithContext(prompt, start_line, end_line) abort
    " Validate range
    if a:start_line > a:end_line || a:start_line < 1 || a:end_line > line('$')
        echoerr "Invalid range"
        return
    endif

    let num_lines = a:end_line - a:start_line + 1
    let lines = getline(a:start_line, a:end_line)
    let ft = &filetype !=# '' ? &filetype : 'plaintext'

    " Create prompt with context of code
    let prompt_lines = ['"""', a:prompt, "```" . ft] + lines + ["```", '"""']

    " Debug output for prompt
    call ollama#logger#Debug("Prompt:\n" . join(prompt_lines, "\n"))

    " Start chat (ensure this function is defined elsewhere)
    call s:StartChat(prompt_lines)
endfunction

" Create chat with code review prompt
function! ollama#review#Review() range
    call s:StartChatWithContext("Please review the following code:", a:firstline, a:lastline)
endfunction

" Create chat with spell checking prompt
function! ollama#review#SpellCheck() range
    call s:StartChatWithContext("Please review the following text for spelling errors and provide accurate corrections. Ensure that all words are spelled correctly, and make necessary adjustments to enhance the overall spelling accuracy of the text:", a:firstline, a:lastline)
endfunction

" Create chat window with custom prompt
function! ollama#review#Task(prompt) range
    call s:StartChatWithContext(a:prompt, a:firstline, a:lastline)
endfunction

" Create chat with code review prompt
function! ollama#review#Review() range
    call s:StartChatWithContext("Please review the following code:", a:firstline, a:lastline)
endfunction

" Create chat with spell checking prompt
function! ollama#review#SpellCheck() range
    call s:StartChatWithContext("Please review the following text for spelling errors and provide accurate corrections. Ensure that all words are spelled correctly, and make necessary adjustments to enhance the overall spelling accuracy of the text:", a:firstline, a:lastline)
endfunction

" Create chat window with custom prompt
function! ollama#review#Task(prompt) range
    call s:StartChatWithContext(a:prompt, a:firstline, a:lastline)
endfunction

function ollama#review#Chat()
    call s:StartChat(v:null)
endfunction
