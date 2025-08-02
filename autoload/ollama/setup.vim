" autoload/ollama.vim
" SPDX-License-Identifier: GPL-3.0-or-later
" SPDX-CopyrightText: 2024 Gerhard Gappmeier <gappy1502@gmx.net>
" SPDX-CopyrightTdxt: Copyright (C) 2023 GitHub, Inc. - All Rights Reserved
" This file started as a copy of copilot.vim but was rewritten entirely,
" because of the different concept of talking with Ollama instead of MS
" copilot. Still it can contain tiny fragments of the original code.
scriptencoding utf-8

" Retrives the list of installed Ollama models
function! ollama#setup#GetModels(url)
    if has('win32') || has('win64')
        let l:null_redirect = '2>nul'
    else
        let l:null_redirect = '2>/dev/null'
    endif
    " Construct the shell command to call list_models.py with the provided URL
    let l:script_path = printf('%s/python/list_models.py', g:ollama_plugin_dir)
    let l:command = [ g:ollama_python_interpreter, l:script_path, '-u', shellescape(a:url), l:null_redirect ]
    " list to string conversion
    let l:command = join(l:command, ' ')

    " Execute the shell command and capture the output
    let l:output = system(l:command)

    " Check for errors during the execution
    if v:shell_error != 0
        echom "Error: Failed to fetch models from " . a:url . ". Check if the URL is correct, Ollama is running and try again."
        "echoerr "Output: " . l:output
        return [ 'error' ]
    endif

    " Split the output into lines and return as a list
    return split(l:output, "\n")
endfunction

" Process Pull Model stdout
function! s:PullOutputCallback(job_id, data)
    if !empty(a:data)
        call ollama#logger#Debug("Pull Output: " . a:data)
        let l:output = split(a:data, '\\n')

        " Update the popup with progress
        if exists('s:popup_id') && s:popup_id isnot v:null
            call popup_settext(s:popup_id, l:output)
        endif
    endif
endfunction

" Process Pull Model stderr
function! s:PullErrorCallback(job_id, data)
    if !empty(a:data)
        " Log the error
        call ollama#logger#Error("Pull Error: " . a:data)
        let l:output = split(a:data, '\\n')

        " Display the error in the popup
        if exists('s:popup_id') && s:popup_id isnot v:null
            call popup_settext(s:popup_id, 'Error: ' . l:output)
        endif
    endif
endfunction

" Deferred close of progress popup window
function! s:ClosePopup(timer_id)
    call popup_close(s:popup_id)
    let s:popup_id = v:null
    " Continue with setup process
    call s:ExecuteNextSetupTask()
endfunction

" Process pull process exit code
function! s:PullExitCallback(job_id, exit_code)
    call ollama#logger#Debug("PullExitCallback: ". a:exit_code)
    if a:exit_code == 0
        " Log success
        call ollama#logger#Debug("Pull job completed successfully.")

        " Update the popup with success message
        if exists('s:popup_id') && s:popup_id isnot v:null
            call popup_settext(s:popup_id, 'Model pull completed successfully!')
        endif
    else
        " Log failure
        call ollama#logger#Error("Pull job failed with exit code: " . a:exit_code)

        " Update the popup with failure message
        if exists('s:popup_id') && s:popup_id isnot v:null
            call popup_settext(s:popup_id, 'Model pull failed. See logs for details.')
        endif
    endif

    " Close the popup after a delay
    if exists('s:popup_id') && s:popup_id isnot v:null
        call timer_start(2000, function('s:ClosePopup'))
    endif

    " Clear the pull job reference
    let s:pull_job = v:null
endfunction

" Pulls the given model in Ollama asynchronously
function! ollama#setup#PullModel(url, model)
    " Construct the shell command to call the Python script
    let l:script_path = printf('%s/python/pull_model.py', g:ollama_plugin_dir)
    let l:command = [ g:ollama_python_interpreter, l:script_path, '-u', a:url, '-m', a:model ]

    " Log the command being run
    call ollama#logger#Debug("command=". join(l:command, " "))

    " Define job options
    let l:job_options = {
                \ 'in_mode': 'nl',
                \ 'out_mode': 'nl',
                \ 'err_mode': 'nl',
                \ 'out_cb': function('s:PullOutputCallback'),
                \ 'err_cb': function('s:PullErrorCallback'),
                \ 'exit_cb': function('s:PullExitCallback')
                \ }

    " Kill any running pull job and replace with new one
    if exists('s:pull_job') && s:pull_job isnot v:null
        call ollama#logger#Debug("Terminating existing pull job.")
        call job_stop(s:pull_job)
    endif

    " Create a popup window for progress
    let s:popup_id = popup_dialog('Pulling model: ' . a:model . '\n', {
                \ 'padding': [0, 1, 0, 1],
                \ 'zindex': 1000
                \ })

    " Save the popup ID for updates in callbacks
    let s:popup_model = a:model

    " Start the new job and keep a reference to it
    call ollama#logger#Debug("Starting pull job for model: " . a:model)
    let s:pull_job = job_start(l:command, l:job_options)
endfunction

function! ollama#setup#ListModels(models, default)
    " Display available models to the user
    echon "Available Models:\n"
    let l:idx = 1
    let l:ret = -1
    for l:model in a:models
        if l:model == a:default
            echon "  [" .. l:idx .. "] " .. l:model .. " (default)\n"
            let l:ret = l:idx
        else
            echon "  [" .. l:idx .. "] " .. l:model .. "\n"
        endif
        let l:idx += 1
    endfor
    echon "\n"
    " Return index of default model if it exists
    return l:ret
endfunction

function! ollama#setup#SelectModel(kind, models, default)
    " Display model list
    let l:default_idx = ollama#setup#ListModels(a:models, a:default)
    " Select model
    while 1
        if l:default_idx == -1
            let l:msg = "Choose " . a:kind . " model: "
        else
            let l:msg = "Choose " . a:kind . " model (Press enter for '" . a:default . "'): "
        endif
        let l:ans = input(l:msg)
        echon "\n"
        " Check if input is a number
        if l:ans =~ '^\d\+$'
            let l:ans = str2nr(l:ans)
            " Check range
            if l:ans > 0 && l:ans <= len(a:models)
                return l:ans
            endif
        elseif l:ans == "" && l:default_idx != -1
            return l:default_idx
        endif
        echon "error: invalid index\n"
    endwhile
endfunction

" Main Setup routine which helps the user to get started
function! ollama#setup#Setup()
    " setup default local URL
    "let g:ollama_host = "http://localhost:11434"
    let l:ans = input("The default Ollama base URL is '" . g:ollama_host . "'. Do you want to change it? (y/N): ")
    if tolower(l:ans) == 'y'
        let g:ollama_host = input("Enter Ollama base URL: ")
    endif
    echon "\n"

    " get all available models (and test if connection works)
    let l:models = ollama#setup#GetModels(g:ollama_host)

    " create async tasks
    let s:setup_tasks = [function('s:PullCompletionModelTask'), function('s:PullEditModelTask'), function('s:PullChatModelTask'), function('s:FinalizeSetupTask')]
    let s:current_task = 3 " start with Finalize if no pulling is required

    if !empty(l:models)
        " There are already Ollama models available, so we can use them
        if l:models[0] == 'error'
            " loading models failed, abort
            echo "setup aborted due to a Ollama connection error"
            return
        endif
        while 1
            echon "  [1] Select an existing model\n"
            echon "  [2] Pull default models for automatic setup\n"
            let l:ans = input("Your choice: ")
            echon "\n"
            " Check if input is a number
            if l:ans =~ '^\d\+$'
                let l:ans = str2nr(l:ans)
                " Check range
                if l:ans == 1
                    let l:pull_models = 0
                    break
                elseif l:ans == 2
                    let l:pull_models = 1
                    let s:current_task = 0
                    break
                endif
            endif
            echo "error: invalid index"
        endwhile
    else
        let l:ans = input("No models found. Should I load a sane default configuration? (Y/n): ")
        echon "\n"
        if tolower(l:ans) != 'n'
            let s:current_task = 0
        else
            echo "setup aborted"
            return
        endif
        let l:pull_models = 1
    endif

    if l:pull_models == 0
        " Do not pull, select existing models
        let l:ans = ollama#setup#SelectModel("tab completion", l:models, "starcoder2:3b")
        let g:ollama_model = l:models[l:ans - 1]
        echon "Configured '" . g:ollama_model . "' as tab completion model.\n"
        echon "------------------------------------------------------------\n"

        let l:ans = ollama#setup#SelectModel("code edit", l:models, "qwen2.5-coder:7b")
        let g:ollama_edit_model = l:models[l:ans - 1]
        echon "Configured '" . g:ollama_edit_model . "' as code edit model.\n"
        echon "------------------------------------------------------------\n"

        let l:ans = ollama#setup#SelectModel("chat", l:models, "llama3.1:8b")
        let g:ollama_chat_model = l:models[l:ans - 1]
        echon "Configured '" . g:ollama_chat_model . "' as chat model.\n"
    endif

    call s:ExecuteNextSetupTask()
endfunction

function! s:PullCompletionModelTask()
    " Set the default tab completion model
    let g:ollama_model = "starcoder2:3b"
    call ollama#setup#PullModel(g:ollama_host, g:ollama_model)
endfunction

function! s:PullChatModelTask()
    " Set the default chat model
    let g:ollama_chat_model = "llama3.1:8b"
    call ollama#setup#PullModel(g:ollama_host, g:ollama_chat_model)
endfunction

function! s:PullEditModelTask()
    " Set the default code edit model
    let g:ollama_edit_model = "qwen2.5-coder:7b"
    call ollama#setup#PullModel(g:ollama_host, g:ollama_edit_model)
endfunction

" Finalize setup task is called after all setup tasks are completed
" This creates the ollama.vim config file.
function! s:FinalizeSetupTask()
    " Save the URL to a configuration file
    let l:config_dir = expand('~/.vim/config')
    if !isdirectory(l:config_dir)
        call mkdir(l:config_dir, 'p') " Create the directory if it doesn't exist
    endif
    let l:config_file = l:config_dir . '/ollama.vim'

    " Write the configuration to the file
    let l:config = [
                \ "\" Use Python virtual environment (and install packages via pip)",
                \ "let g:ollama_use_venv = " . g:ollama_use_venv,
                \ "\" Ollama base URL",
                \ "let g:ollama_host = '" . g:ollama_host . "'",
                \ "\" tab completion model",
                \ "let g:ollama_model = '" . g:ollama_model . "'",
                \ "\" number of context lines to use for code completion",
                \ "\"let g:ollama_context_lines = 10",
                \ "\" debounce time to wait before triggering a completion",
                \ "\"let g:ollama_debounce_time = 300",
                \ "\" If you want to enable completion for a limited set of",
                \ "\" filetypes only, list them here.",
                \ "\"let g:ollama_completion_allowlist_filetype = []",
                \ "\" If you do not want to run completion for certain ",
                \ "\" filetypes, list them here.",
                \ "\"let g:ollama_completion_denylist_filetype = []",
                \ "",
                \ "\" chat model",
                \ "let g:ollama_chat_model = '" . g:ollama_chat_model . "'",
                \ "\" override chat system prompt",
                \ "\"let g:ollama_chat_systemprompt = 'Give funny answers.'",
                \ "",
                \ "\" edit model",
                \ "let g:ollama_edit_model = '" . g:ollama_edit_model . "'",
                \ "\" when disabled, LLM changs are applied directly. Useful when tracking changes via Git.",
                \ "\"let g:ollama_use_inline_diff = 0",
                \ "",
                \ "\" debug settings",
                \ "\"let g:ollama_debug = 4",
                \ "\" general log file location",
                \ "\"let g:ollama_logfile = '/tmp/logs/vim-ollama.log'",
                \ "\" ollama chat conversation log",
                \ "\"let g:ollama_review_logfile = '/tmp/logs/vim-ollama-review.log'",
                \ "",
                \ "\" vim: filetype=vim.ollama" ]
    call writefile(l:config, l:config_file)
    echon "Configuration saved to " . l:config_file . "\n"
    call popup_notification("Setup complete", #{ pos: 'center'})
endfunction

" Function to execute the next task
function! s:ExecuteNextSetupTask()
    if !exists('s:setup_tasks') || s:setup_tasks == v:null
        return
    endif
    if s:current_task < len(s:setup_tasks)
        " Get the current task function and execute it
        let l:Task = s:setup_tasks[s:current_task]
        let s:current_task = s:current_task + 1
        call call(l:Task, [])
    else
        " All tasks are completed
        let s:setup_taks = v:null
    endif
endfunction

" Install all dependencies using Pip
function! ollama#setup#PipInstall() abort
    let l:venv_path = expand('$HOME/.vim/venv/ollama')
    let l:pip_path = l:venv_path . '/bin/pip'
    let l:reqs = ["'httpx>=0.23.3'", 'requests', 'jinja2']

    if !g:ollama_use_venv
        echon "Error: you need to enable ollama_use_venv and restart Vim first."
        return
    endif

    " Check if pip exists in venv
    if !filereadable(l:pip_path)
        echon "Error: Failed to create virtual environment.\n"
        return
    endif

    echon "Installing dependencies...\n"
    call system(l:pip_path . ' install ' . join(l:reqs, ' '))
    echon "Dependencies installed successfully.\n"
endfunction

" Creates a Python virtual environment and installs all depedencies
function! ollama#setup#EnsureVenv() abort
    let l:venv_path = expand('$HOME/.vim/venv/ollama')

    " Check if virtual environment already exists
    if !isdirectory(l:venv_path)
        echon "Setting up Python virtual environment for Vim-Ollama...\n"
        call system('python3 -m venv ' . shellescape(l:venv_path))
        echon "Succeeded.\n"

        call ollama#setup#PipInstall()
    endif

    " Change path to python to venv
    let g:ollama_python_interpreter = l:venv_path . '/bin/python'
endfunction

" Loads the plugin's python modules
function! s:LoadPluginPyModules() abort
    python3 << EOF
import os
import sys
import vim

# Adjust the path to point to the plugin's Python directory
plugin_python_path = os.path.join(vim.eval("g:ollama_plugin_dir"), "python")
if plugin_python_path not in sys.path:
    sys.path.append(plugin_python_path)

try:
    # Import your CodeEditor module
    import CodeEditor
    import VimHelper
except ImportError as e:
    print(f'Error importing CodeEditor module:\n{e}')
EOF
endfunction

" Initializes venv for python.
" This must be done before loading the plugin's py modules,
" to ensure the plugin's python requirements are available.
function! s:SetupPyVEnv() abort
    python3 << EOF
import os
import sys
import vim
# Check if venv is enabled
use_venv = vim.eval('g:ollama_use_venv') or 0

# Should we use a venv?
if use_venv:
    # Create default venv path
    venv_path = os.path.join(os.environ['HOME'], '.vim', 'venv', 'ollama')
    # Check if the venv path exists
    if os.path.exists(venv_path):
        #print('Found venv:', venv_path)

        venv_bin = os.path.join(venv_path, 'bin', 'python3')
        venv_site_packages = os.path.join(venv_path, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')

        # Ensure the virtual environment's site-packages is in sys.path
        if venv_site_packages not in sys.path:
            #print(f'Adding venv site-packages to path: {venv_site_packages}')
            sys.path.insert(0, venv_site_packages)
    else:
        print('Venv not found: '. venv_path)
else:
    print('Venv disabled')
EOF
endfunction

function! ollama#setup#Init() abort
    let l:ollama_config = expand('$HOME/.vim/config/ollama.vim')

    " check if config file exists
    if !filereadable(l:ollama_config)
        echon "Welcome to Vim-Ollama!\n"
        echon "----------------------\n"
        let l:ans = input("This is the first time you are using this plugin. Should I help you setting up everything? (Y/n): ")
        if tolower(l:ans) == 'n'
            return
        endif
        echon "\n"

        " select Python configuration
        let l:ans = input("Create a Python virtual environment and install all required packages? (Y/n): ")
        if tolower(l:ans) != 'n'
            echon "let g:ollama_use_venv=1\n"
            let g:ollama_use_venv = 1
        endif
        echon "\n"

        if g:ollama_use_venv
            " Ensure venv and dependencies are set up
            call ollama#setup#EnsureVenv()
            call s:SetupPyVEnv()
        endif
        call ollama#setup#Setup()
        call s:LoadPluginPyModules()
    else
        " load the config file
        execute 'source' l:ollama_config
        if g:ollama_use_venv
            " Ensure venv and dependencies are set up
            call ollama#setup#EnsureVenv()
            call s:SetupPyVEnv()
        endif
        call s:LoadPluginPyModules()
    endif
endfunction
