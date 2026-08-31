" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
let s:ollama_bufname = 'Ollama Chat'
let s:response_line = -1
let s:response_started = v:false

if !exists('g:ollama_review_logfile')
    let g:ollama_review_logfile = tempname() .. '-ollama-review.log'
endif

func! ollama#review#KillChatBot()
    call ollama#logger#Debug("KillChatBot")

    " Interrupt the current request but keep the chat process alive.
    if exists("s:job") && type(s:job) == v:t_job
        call job_stop(s:job, 'int')
    else
        call ollama#logger#Debug("No job to kill")
    endif
endfunc

function! s:StopChatBot() abort
    if exists("s:job") && type(s:job) == v:t_job
        call job_stop(s:job, 'term')
    endif
endfunction

func! s:BufReallyDelete(buf)
    call ollama#logger#Debug("BufReallyDelete " .. a:buf)
    execute "bwipeout! " .. a:buf
endfunc

func! ollama#review#BufDelete(buf)
    call ollama#logger#Debug("BufDelete")
    if a:buf == s:buf
        call ollama#logger#Debug("Deleting buffer " .. a:buf)
        " The buffer was closed by :quit or :q!
        call s:StopChatBot()
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
    let s:response_line = -1
    let s:response_started = v:false

    " Function handling a line of text that has been typed.
    func! TextEntered(text)
        call ollama#logger#Debug("TextEntered: " .. a:text)
        if a:text == ''
            " don't send empty messages
            return
        endif
        " Send the text to a shell with Enter appended.
        call ch_sendraw(s:job, a:text .. "\n")
        let s:response_line = -1
        let s:response_started = v:false
    endfunc

    " Function handling output from the shell without changing the active view.
    func! GotOutput(channel, msg)
        call ollama#logger#Debug("GotOutput: " .. a:msg)

        if !bufexists(s:buf) || !bufloaded(s:buf)
            return
        endif

        " Decode model line breaks; actual newlines frame channel messages.
        let l:msg = substitute(a:msg, '<OLLAMA_NL>', "\n", 'g')
        let l:lines = split(l:msg, "\n", 1)
        let l:first_line = v:true
        for l:line in l:lines
            let l:idx = stridx(l:line, "<EOT>")
            if l:idx != -1
                call ollama#logger#Debug("idx=" .. l:idx)
                let l:line = strpart(l:line, 0, l:idx)
            endif

            if !s:response_started
                if l:line !=# ''
                    " Insert output immediately before the editable prompt line.
                    let l:line_count = getbufinfo(s:buf)[0].linecount
                    call appendbufline(s:buf, l:line_count - 1, l:line)
                    let s:response_line = l:line_count
                    let s:response_started = v:true
                endif
            elseif !l:first_line
                " Each subsequent channel line starts a new output line.
                let l:line_count = getbufinfo(s:buf)[0].linecount
                call appendbufline(s:buf, l:line_count - 1, l:line)
                let s:response_line = l:line_count
            elseif l:line !=# ''
                let l:old_line = getbufline(s:buf, s:response_line)[0]
                call setbufline(s:buf, s:response_line, l:old_line .. l:line)
            endif
            let l:first_line = v:false

            if l:idx != -1
                let s:response_started = v:false
                let s:response_line = -1
                if bufwinid(s:buf) == win_getid()
                    startinsert
                endif
            endif
        endfor
    endfunc

    func! Interrupt(channel) abort
        call ollama#review#KillChatBot()
    endfunc

    " Function handling output from the shell: Add it above the prompt.
    func! GotErrors(channel, msg)
        call ollama#logger#Debug("GotErrors: " .. a:msg)

        let l:bufname = 'stderr'
        let l:bufnr = bufnr(l:bufname)
        if (l:bufnr != -1)
            " buffer already exists
            silent execute 'buffer' l:bufnr
        else
            " create new error buffer
            silent execute 'new' l:bufname
        endif

        setlocal buftype=nofile
        setlocal bufhidden=delete

        call append(line("$"), a:msg)
        stopinsert
    endfunc

    " Function handling the shell exits: close the window.
    func! JobExit(job, status)
        call ollama#logger#Debug("JobExit: " .. a:status)
        if !bufexists(s:buf)
            let s:buf = -1
            return
        endif
        " Switch to the chat buffer
        let l:chat_win = s:FindBufferWindow(s:buf)
        if l:chat_win == -1
            let s:buf = -1
            return
        endif
        execute l:chat_win .. 'wincmd w'
        " Turn off prompt functionality and make the buffer modifiable
        call prompt_setprompt(s:buf, '')
        setlocal buftype=
        setlocal modifiable
        " output info message
        call append(line("$") - 1, "Chat process terminated with exit code " .. a:status)
        call append(line("$") - 1, "Use ':q' or ':bd' to delete this buffer and run ':OllamaChat' again to create a new session.")
        stopinsert
        let s:buf = -1
        " avoid saving and make :q just work
        setlocal nomodified
    endfunc

    let l:model_options = json_encode(g:ollama_chat_options)
    call ollama#logger#Debug("Connecting to Ollama on " .. g:ollama_host .. " using model " .. g:ollama_model)
    call ollama#logger#Debug("model_options=" .. l:model_options)

    " Convert plugin debug level to python logger levels
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)
    let l:base_url = g:ollama_host
    if g:ollama_chat_provider == 'openai'
        let l:base_url = g:ollama_openai_baseurl
    endif

    let l:script_path = printf('%s/python/chat.py', g:ollama_plugin_dir)
    " Create the Python command
    let l:command = [ g:ollama_python_interpreter,
                \ l:script_path,
                \ '-p', g:ollama_chat_provider,
                \ '-m', g:ollama_chat_model,
                \ '-u', l:base_url,
                \ '-o', l:model_options,
                \ '-t', g:ollama_chat_timeout,
                \ '-l', l:log_level ]
    if g:ollama_nothinking ==# v:true
        let l:command += [ '-n' ]
    endif
    " Check if a system prompt was configured
    if g:ollama_chat_systemprompt != ''
         " add system prompt option
        let l:command += [ '-s', g:ollama_chat_systemprompt ]
    endif
    " Add optional credentialname for looking up the API key
    if g:ollama_openai_credentialname != ''
         " add system prompt option
        let l:command += [ '-k', g:ollama_openai_credentialname ]
    elseif g:ollama_ollama_credentialname != ''
         " add system prompt option
        let l:command += [ '-k', g:ollama_ollama_credentialname ]
    endif

    " Redirect job's IO to buffer
    let job_options = {
        \ 'out_cb': function('GotOutput'),
        \ 'err_cb': function('GotErrors'),
        \ 'exit_cb': function('JobExit'),
        \ }

    " Start a shell in the background.
    let s:job = job_start(l:command, l:job_options)

    " Create chat buffer
    let l:bufname = s:ollama_bufname
    if (s:buf != -1)
        " buffer already exists
        let l:chat_win = s:FindBufferWindow(s:buf)
        " switch to existing buffer
        if l:chat_win != -1
            execute l:chat_win  ..  'wincmd w'
        else
            execute 'buffer' s:buf
        endif
        " send lines
        if a:lines isnot v:null
            call append(line("$") - 1, a:lines)
            let l:prompt = join(a:lines, "\n")
            call ollama#logger#Debug("Sending prompt '" .. l:prompt .. "'...")
            call ch_sendraw(s:job, l:prompt .. "\n")
        endif
        return
    endif

    " Create new chat buffer
    if exists('g:ollama_split_vertically') && g:ollama_split_vertically == 1
        silent execute 'vnew' l:bufname
    else
        silent execute 'new' l:bufname
    endif
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
    let b:coc_enabled = 0 " disable CoC in chat buffer
    " Create a channel log so we can see what happens.
    if g:ollama_debug >= 4
        call ch_logfile(g:ollama_review_logfile, 'w')
    endif

    " Add a title to the chat buffer
    let l:title = "Chat with '" .. g:ollama_chat_model .. "' (via " .. g:ollama_chat_provider .. ")"
    call append(0, l:title)
    call append(1, repeat('-', len(l:title)))
    call append(2, "(type 'quit' to exit, press CTRL-C to interrupt output)")
    if a:lines isnot v:null
        call append(3, a:lines)
        call ch_sendraw(s:job, join(a:lines, "\n") .. "\n")
    endif

    " connect buffer with job
    call prompt_setcallback(buf, function("TextEntered"))
    call prompt_setinterrupt(buf, function("Interrupt"))
    eval prompt_setprompt(buf, ">>> ")

    " add key mapping for CTRL-C to terminate the chat script
    execute 'nnoremap <buffer> <C-C> :call ollama#review#KillChatBot()<CR>'

    " buftype=prompt change modified. so reset it to easy to :q
    augroup ollama_chat_fix_modified
      au!
      autocmd! TextChanged <buffer> setlocal nomodified
      autocmd! TextChangedI <buffer> setlocal nomodified
    augroup END

    " Highlight the reasoning/thinking output (lines starting with '> ') in italics
    call matchadd('OllamaThinking', '^> .*$')
    call matchadd('OllamaThinking', '^#\(StartThinking\|EndThinking\)$')

    " Fold the reasoning/thinking output, closed by default
    " The Python script wraps the thinking block in #StartThinking/#EndThinking markers
    setlocal foldmethod=marker
    setlocal foldmarker=#StartThinking,#EndThinking
    setlocal foldtext=ollama#review#ChatFoldText()
    setlocal foldlevel=0
    setlocal foldcolumn=1

    " start accepting shell commands
    startinsert
endfunction

" Compact fold label for the marker-folded thinking output
function! ollama#review#ChatFoldText() abort
    let l:count = 0
    let l:ln = v:foldstart + 1
    while l:ln < v:foldend
        let l:line = getline(l:ln)
        if l:line =~# '^> '
            let l:count += 1
        endif
        let l:ln = l:ln + 1
    endwhile
    if l:count == 0
        return "Thinking..."
    endif
    return "+-- Thinking (" .. l:count .. " lines): "
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
    let prompt_lines = ['"""', a:prompt, "```"  ..  ft] + lines + ["```", '"""']

    " Debug output for prompt
    call ollama#logger#Debug("Prompt:\n"  ..  join(prompt_lines, "\n"))

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

function ollama#review#Chat()
    call s:StartChat(v:null)
endfunction
