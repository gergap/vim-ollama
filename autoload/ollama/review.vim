" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
let s:ollama_bufname = 'Ollama Chat'

if !exists('g:ollama_review_logfile')
    let g:ollama_review_logfile = tempname() .. '-ollama-review.log'
endif

func! ollama#review#KillChatBot()
    call ollama#logger#Debug("KillChatBot")

    " Stop the job if it exists
    if exists("s:job") && type(s:job) == v:t_job
        call ch_sendraw(s:job, "quit\n")
        call job_stop(s:job)
        while job_status(s:job) == 'run'
            sleep 1
        endwhile
        let s:buf = -1
    else
        call ollama#logger#Debug("No job to kill")
    endif
endfunc

func! s:BufReallyDelete(buf)
    call ollama#logger#Debug("BufReallyDelete " .. a:buf)
    execute "bwipeout! " .. a:buf
endfunc

func! ollama#review#BufDelete(buf)
    call ollama#logger#Debug("BufDelete")
    if a:buf == s:buf
        call ollama#logger#Debug("Deleting buffer " .. a:buf)
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
    " Counter for reducing redraw frequency
    let s:token_count = 0

    " Function handling a line of text that has been typed.
    func! TextEntered(text)
        call ollama#logger#Debug("TextEntered: " .. a:text)
        if a:text == ''
            " don't send empty messages
            return
        endif
        " Send the text to a shell with Enter appended.
        call ch_sendraw(s:job, a:text .. "\n")
        " Reset token count for new request
        let s:token_count = 0
    endfunc

    " OLD VERSION: Append each token as a new line (non-streaming)
    func! GotOutputOld(channel, msg)
        call ollama#logger#Debug("GotOutput: " .. a:msg)
        " append lines
        let l:lines = split(a:msg, "\n")
        for l:line in l:lines
            " when we received <EOT> start insert mode again
            let l:idx = stridx(l:line, "<EOT>")
            if l:idx != -1
                call ollama#logger#Debug("idx=" .. l:idx)
                let l:line = strpart(l:line, 0, l:idx)
            endif
            call appendbufline(s:buf, "$", l:line)
            if bufname() == s:ollama_bufname " Check if current active window is Ollama Chat
                " check if in insert mode
                if mode() == 'i'
                    " start insert mode again
                    call feedkeys("\<Esc>")
                endif
                call feedkeys("G") "jump to end
                if l:idx != -1
                    " start insert mode
                    call feedkeys("a")
                endif
            endif
        endfor
    endfunc

    " NEW VERSION: Stream tokens on the same line with real-time cursor tracking
    func! GotOutputNew(channel, msg)
        " call ollama#logger#Debug("GotOutput: [" .. a:msg .. "]")

        " Check for <EOT> marker
        let l:idx = stridx(a:msg, "<EOT>")
        let l:is_eot = l:idx != -1
        let l:content = l:is_eot ? strpart(a:msg, 0, l:idx) : a:msg

        " Append content to the last line for streaming effect
        let l:updated_line_num = 0
        let l:updated_line_content = ""
        let l:line_count = 0

        if !empty(l:content)
            " Get buffer line count efficiently
            let l:buf_info = getbufinfo(s:buf)[0]
            let l:line_count = l:buf_info.linecount
            " call ollama#logger#Debug("line_count=" .. l:line_count)

            if l:line_count == 0
                " Buffer is empty, append as new line
                " call ollama#logger#Debug("Buffer empty, appending first line")
                call appendbufline(s:buf, 0, l:content)
                let l:updated_line_num = 1
                let l:updated_line_content = l:content
            else
                " Get only the last line (much faster than getting all lines)
                let l:last_line = getbufline(s:buf, l:line_count, l:line_count)[0]
                let l:updated_line_content = l:last_line .. l:content
                " call ollama#logger#Debug("Appending to line " .. l:line_count .. ": '" .. l:last_line .. "' + '" .. l:content .. "'")
                call setbufline(s:buf, l:line_count, l:updated_line_content)
                let l:updated_line_num = l:line_count
            endif
        endif

        " When streaming is done, add a new line for the next input
        if l:is_eot
            " call ollama#logger#Debug("EOT received, adding newline")
            call appendbufline(s:buf, "$", "")
            " Reuse line_count if we already got it, otherwise fetch
            if l:line_count > 0
                let l:updated_line_num = l:line_count + 1
            else
                let l:buf_info = getbufinfo(s:buf)[0]
                let l:updated_line_num = l:buf_info.linecount
            endif
            let l:updated_line_content = ""
        endif

        " Update cursor position if this is the active chat window
        if bufname() == s:ollama_bufname " Check if current active window is Ollama Chat
            let l:winid = bufwinid(s:buf)
            if l:winid != -1 && l:updated_line_num > 0
                " Set cursor position directly (much faster than feedkeys)
                let l:col = len(l:updated_line_content) + 1
                call win_execute(l:winid, 'call cursor(' . l:updated_line_num . ', ' . l:col . ')')

                " Increment token counter and only redraw every N tokens (or always for EOT)
                let s:token_count += 1
                if l:is_eot || s:token_count % 5 == 0
                    redraw
                endif

                if l:is_eot
                    " Streaming done, enter insert mode
                    if mode() == 'i'
                        call feedkeys("\<Esc>")
                    endif
                    call feedkeys("a")
                endif
            endif
        endif
    endfunc

    " Wrapper function that delegates to new version by default
    " To use old version, set g:ollama_use_old_output = 1
    func! GotOutput(channel, msg)
        if exists('g:ollama_use_old_output') && g:ollama_use_old_output
            call GotOutputOld(a:channel, a:msg)
        else
            call GotOutputNew(a:channel, a:msg)
        endif
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
        " Switch to the chat buffer
        execute 'buffer' s:buf
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
    call ollama#logger#Debug("Chat Connecting to Ollama on " .. g:ollama_host .. " using model " .. g:ollama_model)
    call ollama#logger#Debug("model_options=" .. l:model_options)

    if exists('g:ollama_model_sampling_denylist')
            \ && len(g:ollama_model_sampling_denylist) > 0
            \ && index(g:ollama_model_sampling_denylist, g:ollama_chat_model) >= 0
        let l:sampling_enabled = 0
    else
        let l:sampling_enabled = 1
    endif
    call ollama#logger#Debug("sampling_enabled=" .. l:sampling_enabled)

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
                \ "-se", l:sampling_enabled,
                \ '-t', g:ollama_chat_timeout,
                \ '-l', l:log_level ]
    " Check if a system prompt was configured
    if g:ollama_chat_systemprompt != ''
         " add system prompt option
        let l:command += [ '-s', g:ollama_chat_systemprompt ]
    endif
    " Add optional credentialname for looking up the API key
    if g:ollama_openai_credentialname != ''
         " add system prompt option
        let l:command += [ '-k', g:ollama_openai_credentialname ]
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
    " setlocal filetype=ollama-chat
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
    eval prompt_setprompt(buf, ">>> ")

    " add key mapping for CTRL-C to terminate the chat script
    execute 'nnoremap <buffer> <C-C> :call ollama#review#KillChatBot()<CR>'
    execute 'inoremap <buffer> <C-C> <esc>:call ollama#review#KillChatBot()<CR>'

    " buftype=prompt change modified. so reset it to easy to :q
    augroup ollama_chat_fix_modified
      au!
      autocmd! TextChanged <buffer> setlocal nomodified
      autocmd! TextChangedI <buffer> setlocal nomodified
    augroup END

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
