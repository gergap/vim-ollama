" Vim-Ollama example configuration for a local Ollama server.
" Copy the settings you want to ~/.vim/config/ollama.vim.

" General configuration
let g:ollama_use_venv = 1
let g:ollama_host = 'http://localhost:11434'

" Use the secure build helper for Vim's :make command.
let &makeprg = shellescape(g:ollama_plugin_dir .. '/scripts/mk')

"""""""""""""""""""""""""""""""""""""""""
" Code Completion
"""""""""""""""""""""""""""""""""""""""""
" Tab completion model. It must have a matching FIM config in python/configs/.
let g:ollama_model_provider = 'ollama'
let g:ollama_model = 'qwen2.5-coder:7b'
let g:ollama_model_options = {
            \ 'temperature': 0,
            \ 'top_p': 0.95,
            \ 'num_predict': 128,
            \ }
" Number of context lines before and after the cursor.
let g:ollama_context_lines = 30
" Delay after the last keystroke before triggering completion, in milliseconds.
let g:ollama_debounce_time = 500
" Number of alternative completions. Alternatives can be cycled with <M-Down>
" and <M-Up>. This only affects the Ollama provider.
let g:ollama_completion_candidates = 3
" Filetypes where code completion should be explicitly allowed.
" let g:ollama_completion_allowlist_filetype = ['c', 'cpp']
" Filetypes where automatic code completion should be disabled.
let g:ollama_completion_denylist_filetype = ['fuf']

"""""""""""""""""""""""""""""""""""""""""
" Chat.
"""""""""""""""""""""""""""""""""""""""""
let g:ollama_chat_provider = 'ollama'
let g:ollama_chat_model = 'gpt-oss:20b'
" Timeout for receiving individual streaming response fragments, in seconds.
let g:ollama_chat_timeout = 10
" Override the chat model's system prompt.
" let g:ollama_chat_systemprompt = 'You are a coding assistant.'

"""""""""""""""""""""""""""""""""""""""""
" OllamaEdit. The model must support tool calls.
"""""""""""""""""""""""""""""""""""""""""
let g:ollama_edit_provider = 'ollama'
let g:ollama_edit_model = 'qwen3.8:27b'
" Model options. OllamaEdit needs enough context and output space for tool calls.
let g:ollama_edit_options = {
            \ 'temperature': 0,
            \ 'top_p': 0.95,
            \ 'num_predict': 4096,
            \ 'num_ctx': 65536,
            \ 'keep_alive': 1800,
            \ }
" Maximum number of model tool calls allowed in one edit request.
let g:ollama_edit_max_operations = 64

"""""""""""""""""""""""""""""""""""""""""
" Sandbox (bubblewrap) configuration
"""""""""""""""""""""""""""""""""""""""""
" Run execute and vim-check inside bubblewrap. It is enabled automatically when
" bubblewrap is available on Unix systems.
" Allow network access to sandboxed tools. Keep disabled unless required.
" Can be also enabled for individual tools, see below.
let g:ollama_bwrap_network = v:false
" Ask for confirmation before launching sandboxed execute and vim-check tools.
let g:ollama_bwrap_confirm = v:true
" Allow sandboxed execute commands to write below the current project directory.
" Maybe necessary for running/testing your programs.
let g:ollama_bwrap_execute_allow_project_write = v:false
" Whitelist executables that may be run by the execute tool.
let g:ollama_execute_allowlist = ['/usr/bin/clang-format', '/usr/bin/glab']
" Whitelist executables that may access the network inside bubblewrap.
" glab needs this for GitLab API calls; network access remains denied for all
" other executables.
let g:ollama_bwrap_network_allowlist = ['/usr/bin/glab']
" Expose selected files or directories read-only inside bubblewrap.
let g:ollama_bwrap_readonly_paths = [expand('~/.config/glab-cli')]

"""""""""""""""""""""""""""""""""""""""""
" Provider alternatives
"""""""""""""""""""""""""""""""""""""""""
" See openai_provider.vim, mistral_provider.vim, claude_code_provider.vim,
" lmstudio_provider.vim, and openwebui_provider.vim. Do not source more than
" one provider example at a time unless you intend to override these values.

"""""""""""""""""""""""""""""""""""""""""
" Debug settings
"""""""""""""""""""""""""""""""""""""""""
" Without an explicit logfile, Vim creates a random log in the temp directory.
" Python logs are written to /tmp/logs/complete.log and /tmp/logs/chat.log.
" Set 0=off, 1=errors, 2=warnings, 3=info, or 4=debug.
let g:ollama_debug = 0
" Show complete LLM requests in folded diagnostics when troubleshooting.
let g:ollama_show_llm_request = v:false
" Show streamed thinking progress during OllamaEdit requests
let g:ollama_edit_show_thinking = v:false
