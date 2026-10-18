" SPDX-License-Identifier: GPL-3.0-or-later
" OllamaEdit status parts for Vim Airline.

function! airline#extensions#ollama#init(ext) abort
    if !exists('*airline#parts#define_function')
        return
    endif
    call airline#parts#define_function('ollama_context', 'ollama#edit#ContextStatus')
    call airline#parts#define_function('ollama_context_budget', 'ollama#edit#ContextBudgetStatus')
    call airline#parts#define_function('ollama_context_progress', 'ollama#edit#ContextProgressStatus')
    call airline#parts#define_function('ollama_task_topic', 'ollama#edit#TaskTopicStatus')
endfunction
