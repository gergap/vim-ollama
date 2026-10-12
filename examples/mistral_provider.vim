" Vim-Ollama provider example for Mistral.
" Copy the settings you want to ~/.vim/config/ollama.vim.

" Mistral's native provider is recommended for FIM completion.
let g:ollama_model_provider = 'mistral'
let g:ollama_model = 'codestral-latest'
let g:ollama_mistral_credentialname = 'api-tokens/mistral-ai'

" Chat and edit use Mistral's OpenAI-compatible endpoint.
let g:ollama_openai_baseurl = 'https://api.mistral.ai/v1'
let g:ollama_openai_credentialname = 'api-tokens/mistral-ai'
let g:ollama_chat_provider = 'openai'
let g:ollama_chat_model = 'codestral-latest'
let g:ollama_edit_provider = 'openai'
let g:ollama_edit_model = 'codestral-latest'
