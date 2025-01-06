# Ollama Support for Vim

This plugin adds Copilot-like code completion support to Vim. It uses [Ollama](https://ollama.com) as a backend, which
can run locally and does not require cloud services, thus preserving your privacy.

## Motivation

[Copilot.vim](https://github.com/github/copilot.vim) by Tim Pope is an excellent plugin for both Vim and NeoVim.
However, it is limited to Microsoft's Copilot, a commercial cloud-based AI that requires sending all your data to
Microsoft.

With Ollama and freely available LLMs (e.g., Llama3, Codellama, Deepseek-coder-v2), you can achieve similar results
without relying on the cloud. While other plugins are available, they typically require NeoVim, which isn't an
alternative for me. I prefer using Vim in the terminal and do not want to switch to NeoVim for various reasons.

## Features

- Intelligent AI-based code completion
- Integrated chat support for code reviews and other interactions

![Demo](screenshots/game.gif)

## Screencasts

### Creating a C application with command line option parsing using AI

[![AI based code completion](screenshots/screenshot1.png)](https://www.youtube.com/watch?v=zhahVd8ibRM)

### Creating Enum to String Conversion function using AI

[![Enum to String Conversion](screenshots/screenshot2.png)](https://www.youtube.com/watch?v=G-ivVUXCKQk)

### Code Review

[![Code Review](screenshots/screenshot3.png)](https://www.youtube.com/watch?v=kLkFr4rbPUo)

### Custom Prompts - Spellcheck Example

[![Custom Prompts](screenshots/screenshot4.png)](https://www.youtube.com/watch?v=aWEQTktv6fs)

## How It Works

The plugin uses two Python scripts, `complete.py` and `chat.py`, to communicate with Ollama via its REST API. The first
script handles code completion tasks, while the second script is used for interactive chat conversations. The Vim plugin
uses these scripts via I/O redirection to integrate AI results into Vim.

This plugin supports Vim only, not NeoVim. If you're looking for a NeoVim plugin, check out
[LLM](https://github.com/huggingface/llm.nvim).

## Requirements

- Python 3.x
- Python package: `httpx>=0.23.3`, `requests`

### Debian-based Systems

If you're using a Debian-based distribution, you can install the required library directly:

```sh
sudo apt install python3-httpx
```

### Other systems

System wide installation using `pip install` is not recommended,
use a virtual environment instead.

You need to run Vim from a shell with this Python environment to make this working.

Example:
```sh
python -m venv $HOME/vim-ollama
source $HOME/vim-ollama/bin/activate
pip install httpx>=0.23.3
pip install requests
```

Testing: You can test the python script on the shell to verify that it is working and all requirements are found.
The script should output a completion as shown below:

```sh
$> cd path/to/vim-ollama/python
$> echo -e '<PRE> def compute_gcd(x, y): <SUF>return result <MID>' | ./complete.py -u http://localhost:11434 -m codellama:7b-code
  if x == 0:
    return y
  else:
    return compute_gcd(y % x, x)

def compute_lcm(x, y):
  result = (x * y) / compute_gcd(x, y)
```

## Installation

Install `gergap/vim-ollama` using vim-plug or any other plugin manager.

vim-plug example:
```vim
call plug#begin()
...
Plug 'gergap/vim-ollama'
call plug#end()
```

## Configuration

By default, the plugin uses Ollama on localhost. You can change this by adding the following variable to your `.vimrc`:

```vim
let g:ollama_host = 'http://tux:11434'
```

Next, configure the LLM models and the corresponding fill-in-the-middle (FIM) tokens. The variable `g:ollama_model`
defines the LLM for code completion tasks. This must be a model with fill-in-the-middle support; otherwise, code
completion may not work as expected. The variable `g:ollama_chat_model` is used for interactive conversations, similar
to ChatGPT.

Example configuration:

```vim
" Default chat model
let g:ollama_chat_model = 'llama3'

" Codellama models
let g:ollama_model = 'codellama:13b-code'
let g:ollama_model = 'codellama:7b-code'
let g:ollama_model = 'codellama:code'

" Codegemma (small and fast)
let g:ollama_model = 'codegemma:2b'
let g:ollama_fim_prefix = '<|fim_prefix|>'
let g:ollama_fim_middle = '<|fim_middle|>'
let g:ollama_fim_suffix = '<|fim_suffix|>'

" qwen2.5-coder (0.5b, 1.5b, 3b, 7b, 14b, 32b)
" smaller is faster, bigger is better"
" https://ollama.com/library/qwen2.5-coder
let g:ollama_model = 'qwen2.5-coder:3b'
let g:ollama_fim_prefix = '<|fim_prefix|>'
let g:ollama_fim_middle = '<|fim_middle|>'
let g:ollama_fim_suffix = '<|fim_suffix|>'

" Deepseek-coder-v2
let g:ollama_model = 'deepseek-coder-v2:16b-lite-base-q4_0'
let g:ollama_fim_prefix = '<｜fim▁begin｜>'
let g:ollama_fim_suffix = '<｜fim▁hole｜>'
let g:ollama_fim_middle = '<｜fim▁end｜>'
```

| Variable              | Default                  | Description                            |
|-----------------------|--------------------------|----------------------------------------|
| `g:ollama_host`       | `http://localhost:11434` | The URL of the Ollama server.          |
| `g:ollama_chat_model` | `llama3`                 | The LLM for interactive conversations. |
| `g:ollama_model`      | `codellama:code`         | The LLM for code completions.          |
| `g:ollama_fim_prefix` | `<PRE> `                 | FIM prefix for Codellama.              |
| `g:ollama_fim_middle` | ` <MID>`                 | FIM middle for Codellama.              |
| `g:ollama_fim_suffix` | ` <SUF>`                 | FIM suffix for Codellama.              |

When changing the code completion model, consult the model’s documentation to find the correct FIM tokens.

## Usage

Simply start coding. The completions will appear as "ghost text" and can be accepted by pressing `<tab>`. To ignore
them, just continue typing or press `<C-]>` to dismiss the suggestion.

See `:help vim-ollama` for more information.
