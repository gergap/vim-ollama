" Vim-Ollama provider example for OpenAI.
" Copy the settings you want to ~/.vim/config/ollama.vim.

let g:ollama_openai_baseurl = 'https://api.openai.com/v1'
" Prefer pass(1) over putting API keys in Vim configuration.
let g:ollama_openai_credentialname = 'api-tokens/openai'

" OpenAI chat-completions are used for chat and edit tasks.
let g:ollama_chat_provider = 'openai'
let g:ollama_chat_model = 'gpt-4.1-mini'
let g:ollama_edit_provider = 'openai'
let g:ollama_edit_model = 'gpt-4.1-mini'

" The legacy completions endpoint is the better OpenAI option for FIM-style
" completion. The model and endpoint must still be available to your account.
let g:ollama_model_provider = 'openai_legacy'
let g:ollama_model = 'gpt-3.5-turbo-instruct'
