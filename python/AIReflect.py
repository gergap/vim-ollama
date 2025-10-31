#!/home/gergap/.vim/venv/ollama/bin/python3
# Test program for testin Mistral tool support
import vim
import json
from mistralai import Mistral
from OllamaLogger import OllamaLogger
from OllamaCredentials import OllamaCredentials

# create logger
log = None

def CreateLogger():
    global log
    log = OllamaLogger('/tmp/logs', 'reflect.log')
    log.setLevel(0)

def SetLogLevel(level):
    if log == None:
        CreateLogger()
    log.setLevel(level)

# --- Tools definieren ---
def get_lsp_diagnostics(file_path: str) -> str:
    """Holt die aktuellen Coc/Clangd Diagnosen aus Vim."""
    diagnostics = vim.eval("CocAction('diagnosticList')")
    relevant = [d for d in diagnostics if d["file"] == file_path]
    return json.dumps(relevant, indent=2)


def update_code_in_vim(new_code: str):
    """Ersetzt den aktuellen Buffer-Inhalt mit neuem Code."""
    buf = vim.current.buffer
    buf[:] = new_code.splitlines()
    return json.dumps({"status": "updated"})

def update_line_in_vim(new_line: str, line_no: int):
    """Replaces one line of code."""
    buf = vim.current.buffer
    buf[line_no - 1] = new_line
    return json.dumps({"status": "updated"})

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_lsp_diagnostics",
            "description": "Get current LSP diagnostics for a file via Coc/Clangd.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_code_in_vim",
            "description": "Replace the complete code in Vim buffer with corrected code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_code": {"type": "string"},
                },
                "required": ["new_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_line_in_vim",
            "description": "Replace one line of code in Vim buffer with corrected code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_line": {"type": "string"},
                    "line_no": {"type": "int"},
                },
                "required": ["new_line", "line_no"],
            },
        },
    },
]

names_to_functions = {
    "get_lsp_diagnostics": get_lsp_diagnostics,
    "update_code_in_vim": update_code_in_vim,
    "update_line_in_vim": update_line_in_vim,
}

# --- Reflexions-Loop ---
def ai_reflective_fix_code(base_url, model, credentialname):
    if log == None:
        CreateLogger()
    log.debug(f'*** ai_reflective_fix_code')

    buf = vim.current.buffer
    file_path = vim.eval('expand("%:p")')
    code = "\n".join(buf[:])

    cred = OllamaCredentials()
    api_key = cred.GetApiKey(base_url, credentialname)

    # connect to Mistral
    if base_url:
        log.info('Using Mistral endpoint '+base_url)
        client = Mistral(server_url=base_url, api_key=api_key)
    else:
        log.info('Using official Mistral endpoint')
        client = Mistral(api_key=api_key)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert C/C++ compiler assistant. "
                "When you generate new code you must request LSP diagnostics via the tool API,"
                "analyze them, and propose a fixed version of the code. "
                "When you are confident, call update_code_in_vim or update_line_invim to apply your fix."
            ),
        },
        {
            "role": "user",
            "content": f"The current file is {file_path}. "
                       "Start by checking for LSP diagnostics using the available tool, "
                       "then propose a fix if needed.\n\nCode:\n```cpp\n" + code + "\n```",
        },
    ]
    log.debug(json.dumps(tools, indent=4))

    for _ in range(3):  # max 3 Reflexionsschleifen
        log.debug("⚙️  Starting a new round of reflection. Current messages:")
        log.debug(json.dumps(messages, indent=4))

        response = client.chat.complete(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="any",
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not hasattr(msg, "tool_calls") or not msg.tool_calls:
            log.debug("✅ No more tool calls. Final message:")
            log.debug(msg.content)
            break

        for tool_call in msg.tool_calls:
            fn = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            log.debug(f"⚙️  Running tool: {fn}({args})")
            result = names_to_functions[fn](**args)
            messages.append(
                {
                    "role": "tool",
                    "name": fn,
                    "content": result,
                    "tool_call_id": tool_call.id,
                }
            )

        # Nach jedem Tool-Call: neue Runde mit aktualisierten Nachrichten
        response = client.chat.complete(model=model, messages=messages)
        msg = response.choices[0].message
        messages.append(msg)
        log.debug(f"🧠 Model output: {msg.content[:300]}...")

