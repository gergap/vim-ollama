" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
let s:outputbuf = -1
let s:code_status = 0 " 0: Idle, 1: Code Started, 2: Code End
let s:num_files_generated = 0
let s:lineno = 0

if !exists('g:ollama_review_logfile')
    let g:ollama_review_logfile = tempname() . '-ollama-review.log'
endif

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

function! s:StartChat(lines, systemprompt) abort
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

        " append lines
        let l:lines = split(a:msg, "\n")
        for l:line in l:lines
            " when we received <EOT> start insert mode again
            let l:idx = stridx(l:line, "<EOT>")
            if l:idx != -1
                call ollama#logger#Debug("idx=".l:idx)
                let l:line = strpart(l:line, 0, l:idx)
            endif

            " check for '\file{filename}', capture the filename
            if l:line =~ '^\\file{'
                " Use matchlist to capture the filename inside the braces
                let match_result = matchlist(l:line, '\\file{\(.*\)}')
                " The first element of the list is the full match, the second is the captured filename
                let l:filename = match_result[1]

                if l:filename  == ''
                    call ollama#logger#Debug("no filename")
                else
                    call ollama#logger#Debug("got filename=".l:filename)

                    " Extract directory from filename
                    let l:dirname = fnamemodify(l:filename, ':h')

                    " Ensure the directory exists
                    if !isdirectory(l:dirname)
                        call mkdir(l:dirname, 'p')
                    endif

                    " move to left pane
                    execute 'wincmd h'
                    " open/create file in new window
                    execute 'edit!' l:filename
                    " delete any existing content, so that the LLM can replace
                    " it with a new version
                    execute 'normal! ggdG'
                    " store buffer handle in s:outputbuf
                    let s:outputbuf = bufnr()
                    let s:num_files_generated += 1
                    return
                endif
            elseif l:line =~'^Finished.'
                call appendbufline(s:buf, "$", "TATAAA!")
                if s:num_files_generated > 0
                    call appendbufline(s:buf, "$", s:num_files_generated. " files generated. Use :wa to save them all.")
                    let s:num_files_generated = 0
                    return
                endif
            endif

            " check if output should be redirected to new file
            if s:outputbuf != -1
                " check s:code_status
                if l:line =~ '^```'
                    if s:code_status == 0
                        let s:code_status = 1
                        let s:lineno = 1
                    else
                        let s:outputbuf = -1
                        let s:code_status = 0
                        " switch back to chat window
                        execute 'wincmd l'
                    endif
                    return
                endif
                if s:code_status == 1
                    call setbufline(s:outputbuf, s:lineno, l:line)
                    let s:lineno = s:lineno + 1
                endif
            else
                " append to chat buffer
                call appendbufline(s:buf, "$", l:line)
            endif
        endfor
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

    let l:model_options = json_encode(g:ollama_chat_options)
    call ollama#logger#Debug("Connecting to Ollama on ".g:ollama_host." using model ".g:ollama_model)
    call ollama#logger#Debug("model_options=".l:model_options)

    " Convert plugin debug level to python logger levels
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    let l:script_path = printf('%s/python/chat.py', g:ollama_plugin_dir)
    " Create the Python command
    let l:command = [ g:ollama_python_interpreter,
                \ l:script_path,
                \ '-m', g:ollama_chat_model,
                \ '-u', g:ollama_host,
                \ '-o', l:model_options,
                \ '-t', g:ollama_chat_timeout,
                \ '-l', l:log_level ]
    " Check if a system prompt was configured
    if a:systemprompt != ''
         " add system prompt option
        let l:command += [ '-s', a:systemprompt ]
    elseif g:ollama_chat_systemprompt != ''
         " add system prompt option
        let l:command += [ '-s', g:ollama_chat_systemprompt ]
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
            let l:prompt = join(a:lines, "\n")
            call ollama#logger#Debug("Sending prompt '".l:prompt."'...")
            call ch_sendraw(s:job, l:prompt .. "\n")
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
    if a:systemprompt != ''
        call append(2, "System prompt: ".a:systemprompt)
    endif
    if a:lines isnot v:null
        call append("$", a:lines)
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

" Create chat window with custom prompt
function! ollama#review#CodeGen(prompt)
    let l:systemprompt = "You are a code generator AI running inside Vim. When creating code examples use the special command `\\file{filename}` to mark the start of a new file, followed by the markdown code snippets. Don't generate any explanations. Finish generation by writing 'Finished.' on a new line."
    let s:num_files_generated = 0
    call s:StartChat([ a:prompt ], l:systemprompt)
    stopinsert
endfunction
