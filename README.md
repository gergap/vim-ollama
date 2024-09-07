# Ollama Support for Vim

This plugin adds "Copilot" like code completion support to Vim.
It uses [Ollama](https://ollama.com) as a backend which can run locally and does not require a cloud
and thus has no privacy problems.

## Motivation

[Copilot.vim](https://github.com/github/copilot.vim) is an awesome plugin from Tim Pope which works in both Vim and
NeoVim, but it is limited to MS Copilot, which is a commercial cloud based AI and requires to send all your data to MS.

With Ollama and freely available LLMs (e.g. Llama3, codellama, deepseek-coder-v2, etc.) you can achieve similar results
without any cloud. There are other plugins available, but those require NeoVim, which is not an alternative for me. I
prefer to use Vim in the terminal and don't want to switch to NeoVim for various reasons.

## Features

* Intelligent AI based code completion
* Integrated chat support to do code reviews or other stuff.

## How it works

There are two python scripts `ollama.py` and `chat.py` which do the communication with the Ollama via its REST API.
The first one is intended for code completion tasks, the second script for interactive chat conversations.
The vim plugin uses these scripts via IO redirection to get the AI results into Vim.

This plugin only supports Vim, no NeoVim. If you are searching for a NeoVim plugin check out [LLM](https://github.com/huggingface/llm.nvim).

## Installation

Install `gergap/vim-ollama.vim` via vim-plug, or any other plugin manager.

vim-plug example:
```
call plug#begin()
...
Plug 'gergap/vim-ollama.vim'
call plug#end()
```

## Configuration

By default the plugin will use Ollama on localhost. You can change this by adding this variable to your `.vimrc`.

```vim
let g:ollama_host = 'http://tux:11434'
```

The next thing to configure are the LLM models to use as well as the according fill-in-the-middle tokens.
The variable `g:ollama_model` defines the LLM for code completion tasks. This must be a model with fill-in-the-middle
support, otherwise code completion will not work as one would expect.
The variable `g:ollama_chat_model` is used for interactive conversations similar to ChatGPT.


```vim
" default chat model
let g:ollama_chat_model = 'llama3'
" default code completion model (Codellama)
let g:ollama_model = 'codellama:13b-code'
let g:ollama_model = 'codellama:7b-code'
let g:ollama_model = 'codellama:code'
" Codegemma (small and fast)
let g:ollama_model = 'codegemma:2b'
let g:ollama_fim_prefix = '<|fim_prefix|>'
let g:ollama_fim_middle = '<|fim_middle|>'
let g:ollama_fim_suffix = '<|fim_suffix|>'
" Deepseek-coder-v2
let g:ollama_model = 'deepseek-coder-v2:16b-lite-base-q4_0'
let g:ollama_fim_prefix = '<｜fim▁begin｜>'
let g:ollama_fim_suffix = '<｜fim▁hole｜>'
let g:ollama_fim_middle = '<｜fim▁end｜>'
```

| Variable            | Default                | Description                            |
|---------------------|------------------------|----------------------------------------|
| g:ollama_host       | http://localhost:11434 | The URL of the Ollama server.          |
| g:ollama_chat_model | llama3                 | The LLM for interactive conversations. |
| g:ollama_model      | codellama:code         | The LLM for code completions.          |
| g:ollama_fim_prefix | `<PRE> `               | FIM prefix for codellama.              |
| g:ollama_fim_middle | ` <MID>`               | FIM middle for codellama.              |
| g:ollama_fim_suffix | ` <SUF>`               | FIM suffix for codellama.              |

When changing the code completion model, consult the models documentation to find out the correct FIM tokens.

## Usage

Simply start coding. The completions are shown as "ghost text" and be accepted by pressing `<tab>`.
To ignore them simply continue typing.

## Commands

### OllamaChat

Opens up a seperate chat window for chating with the LLM inside Vim.

### OllamaReview

You need to visually select some code and then run the command `:OllamaReview` to get a review of the selected code. The
result will be shown in a new buffer, which can then be reviewed or edited as needed.

### OllamaTask

Essentially it works the same as OllamaReview, except that you can specify a custom prompt instead of "review this
code".

E.g. you can select some code and then run `:OllamaTask 'convert this to python'`.


## Known Issues`

The integration with other tab-completions (e.g. Ultisnips) is nor perfect yet, but works for me.
I change the UltiSnips expand trigger to a different key for that.
I'm using CoC pluging with clang-based code completion for C/C++ and Ultisnips.
When pressing `<tab>` it checks first if an AI suggestion is available, otherwise it will forward the `<tab>`
to be handle by CoC. Any patches are welcome to improve this.
