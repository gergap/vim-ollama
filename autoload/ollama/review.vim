let s:job = v:null
let s:bufnr = -1

" Define a function to start the chat session
"function! s:StartChat()
"    " Create a new named buffer
"    let l:bufname = 'Ollama Chat'
"    let l:bufnr = bufnr(l:bufname)
"    if l:bufnr == -1
"        call ollama#logger#Debug("Creating new chat buffer")
"        " Create a new buffer
"        execute 'new' l:bufname
"        " Set the filetype to ollama-chat
"        setlocal filetype=ollama-chat
"        setlocal buftype=nofile
"        setlocal bufhidden=hide
"        setlocal noswapfile
"        setlocal modifiable
"        setlocal wrap
"        " Add a title to the chat buffer
"        call append(0, "Chat with Bot")
"        call append(1, "--------------------")
"    else
"        call ollama#logger#Debug("Switching to existing chat buffer")
"        " Switch to the existing buffer
"        execute 'buffer' l:bufnr
"    endif
"
"    " Start the Python script as a job
"    let job_options = {
"        \ 'out_mode': 'raw',
"        \ 'out_cb': function('s:OnChatBotOutput'),
"        \ 'exit_cb': function('s:OnChatBotExit')
"        \ }
"    ""\ 'stderr_cb': 'OnChatBotError',
"
"    let l:command = printf('python3 %s/python/chat.py -m %s -u %s', expand('<sfile>:h:h'), g:ollama_chat_model, g:ollama_host)
"
"    call ollama#logger#Debug("Starting chat job: ".l:command)
"    let s:job = job_start(l:command, job_options)
"
"    " Get the job channel
"    let s:channel = job_getchannel(s:job)
"
"    " Store the channel in a buffer-local variable
"    let b:chatbot_channel = s:channel
"endfunction

function! s:StartChat(lines) abort
    " Create a channel log so we can see what happens.
    call ch_logfile('logfile', 'w')

    " Function handling a line of text that has been typed.
    func TextEntered(text)
        call ollama#logger#Debug("TextEntered: ".a:text)
        " Send the text to a shell with Enter appended.
        call ch_sendraw(s:job, a:text .. "\n")
    endfunc

    " Function handling output from the shell: Add it above the prompt.
    func GotOutput(channel, msg)
        call ollama#logger#Debug("GotOutput: ".a:msg)
        call append(line("$") - 1, a:msg)
"        call appendbufline(s:buf, '$', split(a:msg, "\n"))
    endfunc

    " Function handling the shell exits: close the window.
    func JobExit(job, status)
        call ollama#logger#Debug("JobExit: ".a:status)
        " set to nofile to avoid saveing prompts
        setlocal buftype=nofile
"        quit!
        bd!
    endfunc

    " Redirect job's IO to buffer
    let job_options = {
        \ 'out_cb': function('GotOutput'),
        \ 'err_cb': function('GotOutput'),
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
        " Buffer already exists, make it visible
        execute 'buffer' l:bufnr
        return
    endif

    " Create new chat buffer
    execute 'new' l:bufname
    " Set the filetype to ollama-chat
"    setlocal filetype=ollama-chat
    setlocal filetype=markdown
    setlocal buftype=prompt
    setlocal bufhidden=wipe
    setlocal noswapfile
    setlocal modifiable
    setlocal wrap
    let buf = bufnr('')
    let s:buf = buf
    " Add a title to the chat buffer
    call append(0, "Chat with Bot")
    call append(1, "--------------------")
    call append(2, a:lines)
    call ch_sendraw(s:job, join(a:lines, "\n") .. "\n")

    " connect buffer with job
    call prompt_setcallback(buf, function("TextEntered"))
    eval prompt_setprompt(buf, ">>> ")

    " start accepting shell commands
    startinsert
endfunction

" Define a callback function for handling chatbot output
function! s:OnChatBotOutput(job, data)
    call ollama#logger#Debug("Received response: ".a:data)
    " Append each line of output from the chatbot to the buffer
    for line in split(a:data, "\n")
        if !empty(line)
            call append(line('$'), line)
        endif
    endfor
    " Keep the cursor at the end
    call cursor(line('$'), 1)
endfunction

" Define a callback function for handling chatbot errors
function! s:OnChatBotError(job, data)
    call ollama#logger#Debug("Received stderr: ".a:data)
    " Append each line of error output to the buffer
    for line in a:data
        if !empty(line)
            call append(line('$'), 'Error: ' . line)
        endif
    endfor
    " Keep the cursor at the end
    call cursor(line('$'), 1)
endfunction

" Define a callback function for handling chatbot exit
function! s:OnChatBotExit(job, exit_code)
    call ollama#logger#Debug("Process exited: ".a:exit_code)
    call append(line('$'), "Chatbot has exited.")
    " Keep the cursor at the end
    call cursor(line('$'), 1)
endfunction

" Define a function to send user input to the chatbot
function! s:SendInputToChatBot()
    " Get the user input
    let user_input = input("You: ")

    " Append the user's input to the buffer
    call append(line('$'), "You: " . user_input)

    " Send the input to the chatbot
    call ch_sendraw(b:chatbot_channel, user_input . "\n")
endfunction

" Map a key to send user input to the chatbot
nnoremap <buffer> <silent> <Enter> :call <sid>SendInputToChatBot()<CR>

function ollama#review#Review() range
    let num_lines = a:lastline - a:firstline
    let lines = getline(a:firstline, a:lastline)

    let prompt ="Please review the following code:"
    call insert(lines, prompt, 0)
    call insert(lines, "```", 1)
    call add(lines, "```")

    call ollama#logger#Debug("Prompt:".join(lines, "\n"))

    call s:StartChat(lines)
endfunction

function ollama#review#Chat() range
    call s:StartChat([])
endfunction

