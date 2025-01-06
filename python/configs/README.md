# Model Configuration Files

This folder contains config files for code completion models.
Only models that support _FIM_ tokens (fill-in-the-middle) can be used,
generic chat models like _llama3_ will not work.

## How it works

Assume you want to complete this line:

    printf("Hello<FILL_IN_HERE>");

and the model should just fill in the missing part at the location marked with
`<FILL_IN_HERE>`, which is your cursor position in Vim's insert mode.

The plugin needs to convert this to a prompt using the correct _FIM_ tokens
used in the training of the _LLM_. This could look like this:

    <PRE> printf("Hello <SUF>"); <MID>

But the tokens to use are model specific, hence we need these configuration
files. Note also, that the middle-token is at the end, and not in the middle. This
is correct and will not work the other way around!

The answer often contains an ` <EOT>` (end-of-text) marker that needs to be removed
by _vim-ollama_. If the model does not use such a marker simply omit it in the config.

## Example config

This is a configuration for codellama. The spaces inside the strings are **important**!

```json
{
    "pre": "<PRE> ",
    "middle": " <MID>",
    "suffix": " <SUF>",
    "eot": " <EOT>"
}
```


