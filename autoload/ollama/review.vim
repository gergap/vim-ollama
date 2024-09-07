let s:job = v:null
let s:buf = -1

" Map a key to send user input to the chatbot
nnoremap <buffer> <silent> <Enter> :call <sid>SendInputToChatBot()<CR>

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
    call job_stop(s:job)
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
        " set to nofile to avoid saveing prompts
        call append(line("$") - 1, "Chat process terminated with exit code ".a:status)
        call append(line("$") - 1, "Run 'OllamaChat' again to restart it or 'bd!' to delete this buffer.")
    endfunc

    " Redirect job's IO to buffer
    let job_options = {
        \ 'out_cb': function('GotOutput'),
        \ 'err_cb': function('GotErrors'),
        \ 'exit_cb': function('JobExit'),
        \ }

    " Start the Python script as a job
    let l:command = printf('python3 %s/chat.py -m %s -u %s', expand('<script>:h:h:h'), g:ollama_chat_model, g:ollama_host)

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
    "setlocal bufhidden=wipe
    setlocal noswapfile
    setlocal modifiable
    setlocal wrap
    let l:buf = bufnr('')
    let s:buf = l:buf
    " Create a channel log so we can see what happens.
    call ch_logfile('logfile', 'w')

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

function ollama#review#Review() range
    let num_lines = a:lastline - a:firstline
    let lines = getline(a:firstline, a:lastline)

    let prompt = "Please review the following code:"
    call insert(lines, '"""', 0)
    call insert(lines, prompt, 1)
    call insert(lines, "```", 2)
    call add(lines, "```")
    call add(lines, '"""')

    call ollama#logger#Debug("Prompt:".join(lines, "\n"))

    call s:StartChat(lines)
endfunction

function ollama#review#Task(prompt) range
    let num_lines = a:lastline - a:firstline
    let lines = getline(a:firstline, a:lastline)

    call insert(lines, '"""', 0)
    call insert(lines, a:prompt, 1)
    call insert(lines, "```", 2)
    call add(lines, "```")
    call add(lines, '"""')

    call ollama#logger#Debug("Prompt:".join(lines, "\n"))

    call s:StartChat(lines)
endfunction

function ollama#review#Chat()
    call s:StartChat(v:null)
endfunction
