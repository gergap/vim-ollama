" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:buf = -1
let s:ollama_bufname = 'Ollama Chat'
" this variable holds the last response of Ollama
let s:ollama_response = []
let g:ollama_project_files = []

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
    " Function handling a line of text that has been typed.
    func! TextEntered(text)
        call ollama#logger#Debug("TextEntered: " .. a:text)
        if a:text == ''
            " don't send empty messages
            return
        endif
        " Reset last response
        let s:ollama_response = []
        " Send the text to a shell with Enter appended.
        call ollama#logger#Debug("ch_sendraw... (TextEntered)")
        call ch_sendraw(s:job, a:text .. "\n")
    endfunc

    " Function handling output from the shell: Add it above the prompt.
    func! GotOutput(channel, msg)
        call ollama#logger#Debug("GotOutput: " .. a:msg)

        " append lines
        let l:lines = split(a:msg, "\n")
        for l:line in l:lines
            " when we received <EOT> start insert mode again
            let l:idx = stridx(l:line, "<EOT>")
            if l:idx != -1
                call ollama#logger#Debug("Stripping <EOT> at idx=" .. l:idx)
                let l:line = strpart(l:line, 0, l:idx)
                " append last line
                call add(s:ollama_response, l:line)
                call ollama#review#ProcessResponse()
            else
                " append lines to ollama_response
                call add(s:ollama_response, l:line)
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

    " Function handling output from the shell: Add it above the prompt.
    func! GotErrors(channel, msg)
        call ollama#logger#Debug("GotErrors: " .. a:msg)

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
    call ollama#logger#Debug("Connecting to Ollama on " .. g:ollama_host .. " using model " .. g:ollama_model)
    call ollama#logger#Debug("model_options=" .. l:model_options)
    let s:ollama_response = []

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
        execute 'vnew' l:bufname
    else
        execute 'new' l:bufname
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
        call ollama#logger#Debug("Sending text... (StartChat)")
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

" Quick hack for decoding some escaped characters, because json_decode doesn't
" do it. TODO: add better solution which works more generic.
function! CleanEscapes(s)
    let s = substitute(a:s, '\\u003c', '<', 'g')
    let s = substitute(s, '\\u003e', '>', 'g')
    let s = substitute(s, '\\n', "\n", 'g')
    return s
endfunction

" Process JSON response intended for the plugin.
function! ollama#review#ProcessResponse()
    " Get last chat response
    let lines = s:ollama_response
    call ollama#logger#Debug("ProcessResponse:\n" .. join(lines, "\n"))

    " Find JSON array boundaries
    let start_idx = -1
    let end_idx = -1
    for i in range(len(lines))
        if lines[i] =~ '^\s*\['
            let start_idx = i
            break
        endif
    endfor
    for i in range(len(lines)-1, -1, -1)
        if lines[i] =~ '\]\s*$'
            let end_idx = i
            break
        endif
    endfor

    if start_idx == -1 || end_idx == -1 || end_idx < start_idx
        echoerr 'Could not find JSON array in buffer'
        return
    endif

    let json_lines = lines[start_idx : end_idx]
    let json_text = join(json_lines, "\n")

    " Decode JSON
    try
        let files = json_decode(json_text)
    catch /^Vim\%((\a\+)\)\=:E\%(\d\+\)/
        echoerr 'Failed to decode JSON'
        return
    endtry

    " Check that files is a list
    if type(files) != type([])
        echoerr 'Decoded JSON is not a list'
        return
    endif

    " Write each file
    for file in files
        if !has_key(file, 'path') || !has_key(file, 'content')
            echoerr 'Invalid file object in JSON'
            continue
        endif

        " Sanitize path: remove leading /, disallow .. to prevent directory escape
        let filepath = substitute(file['path'], '^/*', '', '')
        if filepath =~# '\.\.'
            echoerr 'Unsafe path detected, skipping: ' . filepath
            continue
        endif

        " Create directories if needed
        let dir = fnamemodify(filepath, ':h')
        if dir !=# '' && !isdirectory(dir)
            call mkdir(dir, 'p')
        endif

        " Clean and write content
        let content = CleanEscapes(file['content'])
        try
            call writefile(split(content, "\n"), filepath)
            echom 'Wrote file: ' . filepath
            " Avoid duplicate entries in tracked files
            if index(g:ollama_project_files, filepath) < 0
                call add(g:ollama_project_files, filepath)
            endif
        catch
            echoerr 'Failed to write file: ' . filepath
            continue
        endtry

        " Close chat window, open new file buffer
"        if winnr('$') > 1
"            execute ':q!'
"        endif
        execute ':edit! ' . filepath
    endfor
    " Open NERDTree to show he new files if this plugin is loaded
"    if exists('g:NERDTree')
"        execute ':NERDTreeCWD'
"    endif
    call s:RefreshProjectView()
endfunction

function! s:BuildContextForFiles(files) abort
    let l:context = []

    for filepath in a:files
        " Only add if the file still exists
        if filereadable(filepath)
            " Read from buffer if loaded, else from disk
            if bufloaded(filepath)
                let bufnr = bufnr(filepath)
                let lines = getbufline(bufnr, 1, '$')
            else
                let lines = readfile(filepath)
            endif

            " Get filetype
            let ext = fnamemodify(filepath, ':e')
            let ft = ext != '' ? ext : 'text'

            " Format as markdown code block
            call extend(l:context, [
                        \ '# ' . filepath,
                        \ '```' . ft,
                        \ ] + lines + ['```', ''])
        endif
    endfor

    return l:context
endfunction

" Create chat window with custom prompt
function! ollama#review#CreateCode(prompt) range
    " Prompt template as a list of lines
    let l:prompt_lines = [
                \ "\"\"\"",
                \ "You are a code generation tool inside a Vim plugin. You do not ask questions. You do not respond with any explanation. You already received the user's instruction.",
                \ "Your task is to generate a list of files with full content in response to the instruction below.",
                \ "",
                \ "Instruction:",
                \ a:prompt,
                \ "",
                \ "Respond only in the following JSON format. Do not include any extra explanation:",
                \ "[",
                \ "  {",
                \ "    \"path\": \"example.txt\",",
                \ "    \"content\": \"Example file content here.\"",
                \ "  },",
                \ "  {",
                \ "    \"path\": \"another.txt\",",
                \ "    \"content\": \"Another file...\"",
                \ "  }",
                \ "]",
                \ "\"\"\""
                \ ]

    " Start the chat
    call s:StartChat(l:prompt_lines)
endfunction

" A function for modifying tracked (AI generated) files
function! ollama#review#ModifyCode(prompt)
    if !exists('g:ollama_project_files') || empty(g:ollama_project_files)
        echoerr "No project files tracked. Run OllamaCreate first."
        return
    endif

    " Build the full prompt
    let l:header = [
                \ "\"\"\"",
                \ "You are modifying an existing codebase inside a Vim plugin.",
                \ "Instruction: " . a:prompt,
                \ "",
                \ "The current files are provided below. Respond ONLY with modified files using the exact JSON format:",
                \ "[",
                \ "  { \"path\": \"file.ext\", \"content\": \"New content\" }",
                \ "]",
                \ "Below is the current project state:"
                \ ]

    let l:file_context = s:BuildContextForFiles(g:ollama_project_files)
    " add file context to prompt
    let l:prompt_lines = l:header + l:file_context
    " close multiline prompt
    let l:prompt_lines += ["\"\"\""]

    call s:StartChat(l:prompt_lines)
endfunction

" This function adds all open buffers to the list of tracked files,
" which are used as file context in ModifyCode
function! ollama#review#TrackOpenBuffers()
    if !exists('g:ollama_project_files')
        let g:ollama_project_files = []
    endif

    for bufnr in range(1, bufnr('$'))
        if bufexists(bufnr) && buflisted(bufnr)
            let filepath = bufname(bufnr)

            " Skip unnamed or non-file buffers
            if filepath ==# '' || !filereadable(filepath)
                continue
            endif

            " Normalize path
            let filepath = fnamemodify(filepath, ':.')

            " Avoid duplicates
            if index(g:ollama_project_files, filepath) == -1
                call add(g:ollama_project_files, filepath)
                echom "Tracked: " . filepath
            endif
        endif
    endfor
    call ollama#review#ShowProjectView()
endfunction

" Adds the current buffer to the project file list
function! ollama#review#TrackCurrentBuf()
    let filepath = expand('%:p')
    if filepath ==# '' || !filereadable(filepath)
        echoerr "No valid file in current buffer."
        return
    endif

    let relpath = fnamemodify(filepath, ':.')
    if !exists('g:ollama_project_files')
        let g:ollama_project_files = []
    endif

    if index(g:ollama_project_files, relpath) == -1
        call add(g:ollama_project_files, relpath)
        echom "Tracked: " . relpath
        call ollama#review#ShowProjectView()
    else
        echom "Already tracked: " . relpath
    endif
endfunction

" Removes the current buffer from the project file list
function! ollama#review#UntrackCurrentBuf()
    let filepath = expand('%:p')
    if filepath ==# ''
        echoerr "No valid file in current buffer."
        return
    endif

    let relpath = fnamemodify(filepath, ':.')
    if exists('g:ollama_project_files')
        let g:ollama_project_files = filter(g:ollama_project_files, { _, val -> val !=# relpath })
        echom "Untracked: " . relpath
    else
        echo "No files are currently tracked."
    endif
endfunction

" Opens a NERDTree like project view of tracked files
function! ollama#review#ShowProjectView()
    if !exists('g:ollama_project_files') || empty(g:ollama_project_files)
        echo "No files tracked yet."
        return
    endif

    " Open a vertical split with fixed width (e.g., 30 columns)
    execute 'vertical ' . 30 . 'vsplit OllamaProjectView'
    enew
    setlocal buftype=nofile
    setlocal bufhidden=wipe
    setlocal noswapfile
    setlocal nobuflisted
    setlocal filetype=ollama_project
    setlocal modifiable
    syntax match OllamaProjectHeader /^# AI context/
    highlight link OllamaProjectHeader String

    let l:header = ['# AI context']  " Use '#' as comment style
    let l:lines = l:header + g:ollama_project_files
    call setline(1, l:lines)
    setlocal nomodifiable

    nnoremap <buffer> <CR> :call ollama#review#OpenTrackedFile()<CR>
endfunction

" Refresh the project file list after changing it
function! s:RefreshProjectView()
    if !exists('g:ollama_project_files') || empty(g:ollama_project_files)
        echo "No files tracked yet."
        return
    endif

    let l:header = ['# AI context']  " Use '#' as comment style
    " Find the existing project view buffer
    for buf in range(1, bufnr('$'))
        if bufloaded(buf) && getbufvar(buf, '&filetype') ==# 'ollama_project'
            " Make the buffer modifiable to update content
            call setbufvar(buf, '&modifiable', 1)

            " Replace buffer lines with tracked files
            let l:lines = l:header + g:ollama_project_files
            call setbufline(buf, 1, l:lines)

            " Delete any extra lines beyond tracked files
            let l:num_tracked = len(g:ollama_project_files)
            let l:num_lines = line('$', buf)
            if l:num_lines > l:num_tracked
                call deletebufline(buf, l:num_tracked + 1, l:num_lines)
            endif

            " Set buffer back to nomodifiable
            call setbufvar(buf, '&modifiable', 0)

            " Optionally, you could redraw or refresh the window here if needed
            return
        endif
    endfor

    " If no project view buffer found, open it anew
    call ollama#review#ShowProjectView()
endfunction

" Opens the selected file in project view
function! ollama#review#OpenTrackedFile()
    let relpath = getline('.')
    let abspath = fnamemodify(relpath, ':p')

    if !filereadable(abspath)
        echoerr "File does not exist: " . relpath
        return
    endif

    " Check if buffer is already open in a window
    for winnr in range(1, winnr('$'))
        let bufnr = winbufnr(winnr)
        if fnamemodify(bufname(bufnr), ':p') ==# abspath
            execute winnr . 'wincmd w'
            return
        endif
    endfor

    " Open in split
    execute 'vsplit ' . fnameescape(abspath)
endfunction
