" Vim-Ollama provider example for a local LM Studio OpenAI-compatible server.
" Copy the settings you want to ~/.vim/config/ollama.vim.

let g:ollama_openai_baseurl = 'http://127.0.0.1:1234/v1'
" LM Studio commonly accepts a dummy key; omit this unless your server needs it.
" let g:ollama_openai_credentialname = 'api-tokens/lmstudio'

" OpenAI chat-completions are used for all three features.
let g:ollama_model_provider = 'openai'
let g:ollama_model = 'your-loaded-model'
let g:ollama_chat_provider = 'openai'
let g:ollama_chat_model = 'your-loaded-model'
let g:ollama_edit_provider = 'openai'
let g:ollama_edit_model = 'your-loaded-model'
