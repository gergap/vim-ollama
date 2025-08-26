" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
let s:job = v:null
let s:chat_buf = -1
" buffer for displaying new AI generated code, instead of creating new splits
" all the time, which clutters the IDE
let s:code_bufnr = -1
let s:ollama_bufname = 'Ollama Codegen'
" this variable holds the last response of Ollama
let s:ollama_response = []
" list of AI projct files
let s:ollama_project_files = []
" Buffer partial lines
let s:partial_line = ""

" File status tracking for AI-generated files
let s:file_status = {}

" Define icons for different file states
let s:file_icons = {
    \ 'new': '✨',
    \ 'modified': '📝',
    \ 'unchanged': '📄',
    \ 'deleted': '❌'
    \ }

" Alternative icons (more NERDTree-like)
" let s:file_icons = {
"     \ 'new': '+',
"     \ 'modified': '~',
"     \ 'unchanged': ' ',
"     \ 'deleted': '!'
"     \ }

if !exists('g:ollama_codegen_logfile')
    let g:ollama_codegen_logfile = tempname() .. '-ollama-codegen.log'
endif

" Set file status (called by WriteFile when AI generates content)
function! s:SetFileStatus(filepath, status)
    let s:file_status[a:filepath] = a:status
endfunction

" Get file status with fallback to 'unchanged'
function! s:GetFileStatus(filepath)
    return get(s:file_status, a:filepath, 'unchanged')
endfunction

" Get the status icon for a file
function! s:GetFileStatusIcon(filepath)
    let status = s:GetFileStatus(a:filepath)
    return get(s:file_icons, status, s:file_icons['unchanged'])
endfunction

" Reset all tracked files to 'unchanged' status (called when starting AI conversation)
function! s:ResetAllFileStatus()
    if exists('s:ollama_project_files')
        for filepath in s:ollama_project_files
            let s:file_status[filepath] = 'unchanged'
        endfor
    endif
endfunction

func! ollama#codegen#KillChatBot()
    call ollama#logger#Debug("KillChatBot")

    " Stop the job if it exists
    if exists("s:job") && type(s:job) == v:t_job
        call ch_sendraw(s:job, "quit\n")
        call job_stop(s:job)
        while job_status(s:job) == 'run'
            sleep 1
        endwhile
        let s:chat_buf = -1
    else
        call ollama#logger#Debug("No job to kill")
    endif
endfunc

func! s:CloseWindowByBufNr(bufnr)
    for win in range(1, winnr('$'))
        if winbufnr(win) == a:bufnr
            execute win . 'close!'
            return
        endif
    endfor
endfunc

func! s:CreateScratchBuffer()
    vsplit
    enew
    setlocal buftype=nofile bufhidden=wipe nobuflisted noswapfile
    setlocal filetype=markdown
endfunc

func! s:CloseChat()
    call ollama#logger#Debug("CloseChat")
    if s:chat_buf != -1
        let ret = s:SwitchToBuffer(s:chat_buf)
        if ret == 0
            close
        endif
    else
        call ollama#logger#Debug("No chat window to close")
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

function! s:SwitchToBuffer(bufnr)
    let l:win = s:FindBufferWindow(a:bufnr)
    " switch to existing buffer
    if l:win != -1
        execute l:win  ..  'wincmd w'
    else
        try
            execute 'buffer' a:bufnr
        catch
            call ollama#logger#Debug('Buffer does not exist: '.. a:bufnr)
            return -1
        endtry
    endif
    return 0
endfunction

function! s:WriteFile(file) abort
    " Sanitize path: remove leading /, disallow .. to prevent directory escape
    let filepath = substitute(a:file.path, '^/*', '', '')
    if filepath =~# '\.\.'
        echoerr "Unsafe path: " . filepath
        return
    endif

    " Create directories if needed
    let dir = fnamemodify(filepath, ':h')
    if dir !=# '' && !isdirectory(dir)
        call mkdir(dir, 'p')
    endif

    " Clean and write content
    let content = CleanEscapes(a:file.content)
    call writefile(split(content, "\n"), filepath)
    echom "Wrote file: " . filepath

    " Avoid duplicate entries in tracked files
    if index(s:ollama_project_files, filepath) < 0
        " add to project files
        call add(s:ollama_project_files, filepath)
        call s:SetFileStatus(filepath, 'new')
    else
        call s:SetFileStatus(filepath, 'modified')
    endif

    let empty_buf = FindInitialEmptyBuffer()
    " Open or switch buffer smartly
    let bufnr = bufnr(filepath)
    if bufnr == -1
        echom "buffer does not exist yet"
        if empty_buf != -1 && bufexists(empty_buf)
"            echom "Use initial empty buffer"
            " Use initial empty buffer if it exists
            call s:SwitchToBuffer(empty_buf)
            call s:OpenGeneratedFile(filepath)
        elseif s:code_bufnr != -1
            " Reuse last code buffer, and don't open a new split for each new file
            call s:SwitchToBuffer(s:code_bufnr)
            call s:OpenGeneratedFile(filepath)
        else
"            echom "Use split"
            " Open in a new vertical split
            vertical leftabove split
            call s:OpenGeneratedFile(filepath)
        endif
    else
"        echom "Switch to existing buffer"
        " File is already loaded, switch to it
        call s:SwitchToBuffer(bufnr)
        call s:OpenGeneratedFile(filepath)
    endif

    " Remember the buffer for future reuse
    let s:code_bufnr = bufnr('%')

    call s:RefreshProjectView()
endfunction

function! s:HandleNDJSONLine(line) abort
    " remove any warapping ```json ... ``` text
    let l:json_match = matchstr(a:line, '{\s*".\{-}"\s*}')
    if empty(l:json_match)
        " this is normal with incomplete lines and should not be a error trace
        " for this reason
        call ollama#logger#Debug("Invalid NDJSON line: " . a:line)
        return -1
    endif

    try
        let l:file = json_decode(l:json_match)
        call ollama#logger#Debug("JSON parsing succeeded.")
    catch
        call ollama#logger#Error("Failed to decode JSON: " . l:json_match)
        return -1
    endtry

    if has_key(l:file, 'path') && has_key(l:file, 'content')
        call s:WriteFile(l:file)
    else
        call ollama#logger#Error("NDJSON missing keys: " . a:line)
    endif
    return 0
endfunction

function! s:StartChat(lines) abort
    " Reset all file status to 'unchanged' when starting new AI conversation
    call s:ResetAllFileStatus()
    call s:RefreshProjectView()

    func! GotOutput(channel, msg) abort
        call ollama#logger#Debug("GotOutput: " .. a:msg)

        " Debug/View im Chat Buffer
        call appendbufline(s:chat_buf, "$", a:msg)
        if bufname() == s:ollama_bufname
            if mode() ==# 'i'
                call feedkeys("\<Esc>")
            endif
            call feedkeys("G")
        endif

        " concatenate string parts
        let s:partial_line .= a:msg

        let l:line = s:partial_line
        " check for EOT marker
        let l:idx = stridx(l:line, "<EOT>")
        if l:idx != -1
            call ollama#logger#Debug("Got <EOT>")
            let l:line = strpart(l:line, 0, l:idx)
            if !empty(l:line)
                " process final line
                call s:HandleNDJSONLine(l:line)
            endif
            call s:CloseChat()
            echom "Generatation Complete."
            return
        endif

        " process line
        let l:ret = s:HandleNDJSONLine(l:line)
        if l:ret == 0
            let s:partial_line = ""
        endif
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
    endfunc

    " Function handling the shell exits: close the window.
    func! JobExit(job, status)
        call ollama#logger#Debug("JobExit: " .. a:status)
        call s:CloseChat()
        if status != 0
            echom "Generatation Failed."
        endif
        return
    endfunc

    let l:model_options = json_encode(g:ollama_chat_options)
    call ollama#logger#Debug("Connecting to Ollama on " .. g:ollama_host .. " using model " .. g:ollama_model)
    call ollama#logger#Debug("model_options=" .. l:model_options)
    let s:ollama_response = []

    " Convert plugin debug level to python logger levels
    let l:log_level = ollama#logger#PythonLogLevel(g:ollama_debug)

    let l:script_path = printf('%s/python/chat.py', g:ollama_plugin_dir)
    " Create the Python command
    let l:command = [ g:ollama_python_interpreter,
                \ l:script_path,
                \ '-m', g:ollama_edit_model,
                \ '-u', g:ollama_host,
                \ '-o', l:model_options,
                \ '-t', g:ollama_chat_timeout,
                \ '-l', l:log_level ]
    " Check if a system prompt was configured
    if g:ollama_chat_systemprompt != ''
         " add system prompt option
        let l:command += [ '-s', g:ollama_chat_systemprompt ]
    endif

    " Redirect job's IO to buffer
    let job_options = {
        \ 'out_cb': function('GotOutput'),
        \ 'err_cb': function('GotErrors'),
        \ 'exit_cb': function('JobExit'),
        \ }

    " reset partial line
    let s:partial_line = ""
    " Start a shell in the background.
    let s:job = job_start(l:command, l:job_options)
    " Create chat buffer
    let l:bufname = s:ollama_bufname
    if (s:chat_buf != -1)
        " send lines
        if a:lines isnot v:null
            call appendbufline(s:chat_buf, "$", a:lines)
            let l:prompt = join(a:lines, "\n")
            call ollama#logger#Debug("Sending prompt '" .. l:prompt .. "'...")
            call ch_sendraw(s:job, l:prompt .. "\n")
        endif
        return
    endif

    " Create new chat buffer
    call s:CreateScratchBuffer()
    let l:buf = bufnr('')
    let s:chat_buf = l:buf
    let b:coc_enabled = 0 " disable CoC in chat buffer
    " Create a channel log so we can see what happens.
    if g:ollama_debug >= 4
        call ch_logfile(g:ollama_codegen_logfile, 'w')
    endif

    " Add a title to the chat buffer
    if a:lines isnot v:null
        call append(2, a:lines)
        call ollama#logger#Debug("Sending text... (StartChat)")
        call ch_sendraw(s:job, join(a:lines, "\n") .. "\n")
    endif

    " add key mapping for CTRL-C to terminate the chat script
    execute 'nnoremap <buffer> <C-C> :call ollama#codegen#KillChatBot()<CR>'
    execute 'inoremap <buffer> <C-C> <esc>:call ollama#codegen#KillChatBot()<CR>'

    " hide chat window
    hide
    echo "Sent LLM Request. Waiting for response..."
endfunction

" Quick hack for decoding some escaped characters, because json_decode doesn't
" do it. TODO: add better solution which works more generic.
" Clean and escape JSON/LLM string for C code
function! CleanEscapes(s) abort
    let s = substitute(a:s, '\\u003c', '<', 'g')
    let s = substitute(s, '\\u003e', '>', 'g')

    let result = ''
    let rest = s
    let pattern = '\v"([^"\\]|\\.)*"'

    while len(rest) > 0
        let match = matchstr(rest, pattern)

        if match ==# ''
            let result .= rest
            break
        endif

        let start = match(rest, pattern)
        let end = start + len(match)

        " Append non-matching prefix
        let result .= strpart(rest, 0, start)

        " Extract content inside quotes
        let inner = strpart(match, 1, len(match) - 2)

        " First, escape single backslashes not followed by 'n'
        let escaped = substitute(inner, '\\\(.\)', '\=submatch(1) ==# "n" ? "\\n" : "\\\\" . submatch(1)', 'g')

        " Then, replace real newlines with \n (but not already escaped ones)
        let escaped = substitute(escaped, '\([^\]\)\n', '\1\\n', 'g')

        " Reassemble string literal
        let result .= '"' . escaped . '"'

        " Advance rest
        let rest = strpart(rest, end)
    endwhile

    return result
endfunction

" When starting Vim, we have an initial empty buffer.
" We should use it to generate code instead of creating unnecessary splits.
function! FindInitialEmptyBuffer()
    for buf in getbufinfo({'buflisted': 1})
        if buf.name ==# '' && !buf.changed
            let lines = getbufline(buf.bufnr, 1, '$')
            if len(lines) == 1 && lines[0] ==# ''
                return buf.bufnr
            endif
        endif
    endfor
    return -1
endfunction

" this function trys to open a file in a useable buffer,
" switches to existing windows or creates a new window if necessary
" It also set autoread for automatic reload of changes
function! s:OpenFileSmartly(filename)
    let abspath = fnamemodify(a:filename, ':p')

    if !filereadable(abspath)
        echoerr "File does not exist: " . filename
        return
    endif

    " Check if buffer is already visible in a window
    for winnr in range(1, winnr('$'))
        let bufnr = winbufnr(winnr)
        if fnamemodify(bufname(bufnr), ':p') ==# abspath
            execute winnr . 'wincmd w'
            return
        endif
    endfor

    " Try to find a usable window
    let usable_win = -1
    for winnr in range(1, winnr('$'))
        if s:IsWindowUsable(winnr)
            let usable_win = winnr
            break
        endif
    endfor

    let filepath = fnameescape(abspath)

    if usable_win != -1
        execute usable_win . 'wincmd w'
        execute 'edit! ' . filepath
    else
        vertical leftabove split
        execute 'edit! ' . filepath
    endif

    setlocal autoread
endfunction

" Opens/reloads the given file in the current buffer
function! s:OpenGeneratedFile(filepath)
    call s:OpenFileSmartly(a:filepath)
"    execute 'edit! ' . a:filepath
"    setlocal autoread
endfunction

function! s:BuildContextForFiles(files) abort
    let l:entries = []

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

            " Join lines with newline characters
            let content = join(lines, "\n")

            " Create dict for JSON
            call add(l:entries, {
                        \ 'path': filepath,
                        \ 'content': content
                        \ })
        endif
    endfor

    " Convert list of dicts to JSON string (compact)
    let l:json = json_encode(l:entries)

    " Pipe through jq for pretty-printing
    let l:pretty = system('jq .', l:json)

    return l:pretty
endfunction

function! ollama#codegen#CreateCode(...) range
    " if not prompt was given, open a scratch buffer
    if a:0 == 0 || empty(a:1)
        " open a new vertical window with the scratch buffer
        call CreateScratchBuffer()
        call setline(1, ['# Enter your instruction prompt below:', ''])
        normal! G
        echo "Write your instruction, then run :call SavePromptAndStartChat()"
        return
    endif

    " Wenn ein Prompt übergeben wurde, direkt starten
    call s:BuildPromptAndStartChat(a:1)
endfunction

function! ollama#codegen#SavePromptAndStartChat()
    " Get the content of the current buffer (without comment line)
    let l:lines = getline(2, '$')
    let l:prompt = join(l:lines, "\n")
    if empty(l:prompt)
        echo "Prompt is empty!"
        return
    endif
    " close scratch buffer
    close
    " start chat with prompt
    call s:BuildPromptAndStartChat(l:prompt)
endfunction

function! ollama#codegen#UsePromptAndStartChat()
    " Get the content of the current buffer
    let l:lines = getline(1, '$')
    let l:prompt = join(l:lines, "\n")
    if empty(l:prompt)
        echo "Prompt is empty!"
        return
    endif
    " start chat with prompt
    call s:BuildPromptAndStartChat(l:prompt)
endfunction

function! s:BuildPromptAndStartChat(prompt)
    let l:prompt_lines = [
                \ "\"\"\"",
                \ "You are a code generation tool inside a Vim plugin. You do not ask questions. You do not respond with any explanation. You already received the user's instruction.",
                \ "Your task is to generate a list of files with full content in response to the instruction below.",
                \ "",
                \ "Instruction:",
                \ a:prompt,
                \ "",
                \ "Respond only in the following NDJSON format without array brackets. Do not include any extra explanation:",
                \ "{\"path\": \"example.txt\", \"content\": \"Example file content here.\"}",
                \ "{\"path\": \"another.txt\", \"content\": \"Another file content.\"}",
                \ "\"\"\""
                \ ]
    call s:StartChat(l:prompt_lines)
endfunction

" A function for modifying tracked (AI generated) files
function! ollama#codegen#ModifyCode(prompt)
    if !exists('s:ollama_project_files') || empty(s:ollama_project_files)
        echoerr "No project files tracked. Run OllamaCreate first."
        return
    endif

    let l:file_context = s:BuildContextForFiles(s:ollama_project_files)

    " Build the full prompt
    let l:prompt_lines = [
                \ "\"\"\"",
                \ "You are a code generation tool inside a Vim plugin. You do not ask questions. You do not respond with any explanation. You already received the user's instruction.",
                \ "Your task is to modify a list of files with full content in response to the instruction below.",
                \ "",
                \ "Instruction:",
                \ a:prompt,
                \ "",
                \ "Below is the current project state:",
                \ l:file_context,
                \ "",
                \ "Respond only in the following NDJSON format without array brackets.",
                \ "{\"path\": \"example.txt\", \"content\": \"new content.\"}",
                \ "{\"path\": \"another.txt\", \"content\": \"Another file content.\"}",
                \ "",
                \ "Do NOT output unchanged files.",
                \ "\"\"\""
                \ ]

    call s:StartChat(l:prompt_lines)
endfunction

" This function adds all open buffers to the list of tracked files,
" which are used as file context in ModifyCode
function! ollama#codegen#TrackOpenBuffers()
    if !exists('s:ollama_project_files')
        let s:ollama_project_files = []
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
            if index(s:ollama_project_files, filepath) == -1
                call add(s:ollama_project_files, filepath)
"                echom "Tracked: " . filepath
            endif
        endif
    endfor
    call ollama#codegen#ShowProjectView()
endfunction

" Adds the current buffer to the project file list
function! ollama#codegen#TrackCurrentBuf()
    let filepath = expand('%:p')
    if filepath ==# '' || !filereadable(filepath)
        echoerr "No valid file in current buffer."
        return
    endif

    let relpath = fnamemodify(filepath, ':.')
    if !exists('s:ollama_project_files')
        let s:ollama_project_files = []
    endif

    if index(s:ollama_project_files, relpath) == -1
        call add(s:ollama_project_files, relpath)
"        echom "Tracked: " . relpath
        call ollama#codegen#ShowProjectView()
    else
        echom "Already tracked: " . relpath
    endif
endfunction

" Removes the current buffer from the project file list
function! ollama#codegen#UntrackCurrentBuf()
    let filepath = expand('%:p')
    if filepath ==# ''
        echoerr "No valid file in current buffer."
        return
    endif

    let relpath = fnamemodify(filepath, ':.')
    if exists('s:ollama_project_files')
        let s:ollama_project_files = filter(s:ollama_project_files, { _, val -> val !=# relpath })
        echom "Untracked: " . relpath
    else
        echo "No files are currently tracked."
    endif
endfunction

" Opens a NERDTree like project view of tracked files
function! ollama#codegen#ShowProjectView()
    if !exists('s:ollama_project_files') || empty(s:ollama_project_files)
        echo "No files tracked yet."
        return
    endif

    " Open a vertical split with fixed width
    execute 'vertical ' . 65 . 'vsplit OllamaProjectView'
    enew
    setlocal buftype=nofile
    setlocal bufhidden=wipe
    setlocal noswapfile
    setlocal nobuflisted
    setlocal filetype=ollama_project
    setlocal modifiable
    setlocal nonumber
    setlocal cursorline

    " Enhanced syntax highlighting
    syntax match OllamaProjectHeader /^# AI context/
    syntax match OllamaProjectNew /✨.*$/
    syntax match OllamaProjectModified /📝.*$/
    syntax match OllamaProjectDeleted /❌.*$/
    syntax match OllamaProjectUnchanged /📄.*$/

    " Color highlighting
    highlight link OllamaProjectHeader String
    highlight link OllamaProjectNew DiffAdd
    highlight link OllamaProjectModified DiffChange
    highlight link OllamaProjectDeleted DiffDelete
    highlight link OllamaProjectUnchanged Comment

    let l:header = ['# AI context']
    let l:lines = l:header[:]

    " Add files with status icons
    for filepath in s:ollama_project_files
        let icon = s:GetFileStatusIcon(filepath)
        call add(l:lines, icon . ' ' . filepath)
    endfor

    call setline(1, l:lines)
    setlocal nomodifiable

    " Enhanced key mappings
    nnoremap <buffer> <CR> :call ollama#codegen#OpenTrackedFile()<CR>
    " Open file on double-click (LMB)
    nnoremap <buffer> <2-LeftMouse> :call ollama#codegen#OpenTrackedFile()<CR>
    nnoremap <buffer> r :call ollama#codegen#RefreshProjectView()<CR>
    nnoremap <buffer> ? :call <SID>ShowProjectViewHelp()<CR>
endfunction

" Refresh the project file list with updated icons
function! s:RefreshProjectView()
    if !exists('s:ollama_project_files') || empty(s:ollama_project_files)
        echo "No files tracked yet."
        return
    endif

    let l:header = ['# AI context']

    " Find the existing project view buffer
    for buf in range(1, bufnr('$'))
        if bufloaded(buf) && getbufvar(buf, '&filetype') ==# 'ollama_project'
            " Make the buffer modifiable to update content
            call setbufvar(buf, '&modifiable', 1)

            " Build lines with updated status icons
            let l:lines = l:header[:]
            for filepath in s:ollama_project_files
                let icon = s:GetFileStatusIcon(filepath)
                call add(l:lines, icon . ' ' . filepath)
            endfor

            " Replace buffer content
            call setbufline(buf, 1, l:lines)

            " Delete any extra lines
            let l:total_lines = len(l:lines)
            let l:buf_lines = line('$', buf)
            if l:buf_lines > l:total_lines
                call deletebufline(buf, l:total_lines + 1, l:buf_lines)
            endif

            " Set buffer back to nomodifiable
            call setbufvar(buf, '&modifiable', 0)
            return
        endif
    endfor

    " If no project view buffer found, open it anew
    call ollama#codegen#ShowProjectView()
endfunction

" Show help for project view
function! s:ShowProjectViewHelp()
    echo "Project View Help:"
    echo "✨ - New file (generated by AI)"
    echo "📝 - Modified file (changed by AI)"
    echo "📄 - Unchanged file"
    echo "❌ - Deleted file"
    echo ""
    echo "Keys: <Enter> - Open file, 'r' - Refresh view, '?' - This help"
endfunction

function! s:IsWindowUsable(winnr)
    " Temporarily switch to the window
    execute a:winnr . 'wincmd w'

    " Get window and buffer properties
    let buftype = &buftype
    let preview = &previewwindow
    let modified = &modified

    " Return to previous window
    wincmd p

    " Special buffers like quickfix, help, or preview are not usable
    if buftype !=# '' || preview
        return 0
    endif

    " If buffer is not modified or hidden buffers are allowed, reuse it
    return !modified || &hidden
endfunction

" Opens the selected file in project view
function! ollama#codegen#OpenTrackedFile()
    let line = getline('.')
    " Skip header line
    if line =~# '^# AI context'
        return
    endif

    " Extract filename by removing the icon and space
    let filepath = substitute(line, '^[✨📝📄❌] ', '', '')
    if !empty(filepath)
        call s:OpenFileSmartly(filepath)
    endif
endfunction

" Function to manually set file status (for future use)
function! ollama#codegen#SetFileStatus(filepath, status)
    if index(['new', 'modified', 'unchanged', 'deleted'], a:status) >= 0
        call s:SetFileStatus(a:filepath, a:status)
        call s:RefreshProjectView()
        echom "Set " . a:filepath . " status to: " . a:status
    else
        echoerr "Invalid status: " . a:status . ". Use: new, modified, unchanged, deleted"
    endif
endfunction

" Function to get current file status (for debugging)
function! ollama#codegen#GetFileStatus(filepath)
    return s:GetFileStatus(a:filepath)
endfunction

" Function to clear all file status (useful for testing)
function! ollama#codegen#ClearFileStatus()
    let s:file_status = {}
    call s:RefreshProjectView()
    echo "File status cleared and project view refreshed"
endfunction

" Command to manually set file status
command! -nargs=1 OllamaSetStatus call ollama#codegen#SetFileStatus(<f-args>)
command! OllamaRefreshProject call s:RefreshProjectView()
