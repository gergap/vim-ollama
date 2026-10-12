" Vim-Ollama provider example for an Open WebUI OpenAI-compatible endpoint.
" Copy the settings you want to ~/.vim/config/ollama.vim.

" Open WebUI normally exposes its OpenAI-compatible API below /api.
let g:ollama_openai_baseurl = 'http://127.0.0.1:3000/api'
let g:ollama_openai_credentialname = 'api-tokens/openwebui'

let g:ollama_model_provider = 'openai'
let g:ollama_model = 'your-loaded-model'
let g:ollama_chat_provider = 'openai'
let g:ollama_chat_model = 'your-loaded-model'
let g:ollama_edit_provider = 'openai'
let g:ollama_edit_model = 'your-loaded-model'
