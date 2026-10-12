" Anthropic Claude through its OpenAI-compatible API.
" Despite this filename, these settings use the Claude API, not the Claude
" Code CLI. Copy the settings you want to ~/.vim/config/ollama.vim.
" NOTE: This should work in theory, have not tested it.
"
" Anthropic's compatibility layer supports chat completions and tool calls.
" Vim-Ollama therefore uses its 'openai' provider for all three features.
let g:ollama_openai_baseurl = 'https://api.anthropic.com/v1/'
let g:ollama_openai_credentialname = 'api-tokens/anthropic'
let g:ollama_model_provider = 'openai'
let g:ollama_model = 'claude-sonnet-4-6'
let g:ollama_chat_provider = 'openai'
let g:ollama_chat_model = 'claude-sonnet-4-6'
let g:ollama_edit_provider = 'openai'
let g:ollama_edit_model = 'claude-sonnet-4-6'
"
" OllamaEdit can consume CLAUDE.md project instructions. This setting is
" enabled by default, but can be made explicit:
let g:ollama_use_claude_md_file = v:true
"
" The compatibility layer is intended mainly for testing and comparison.
" Native Claude API features such as full thinking support are not exposed
" through the OpenAI-compatible interface.
