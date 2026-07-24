# Agent Instructions

## Repository Shape

- This is a Vim plugin, not a Neovim plugin. The runtime entrypoint is `plugin/ollama.vim`; Vim functions live under `autoload/ollama/`, and Python helpers under `python/` are invoked by the plugin.
- There is no package manifest, lockfile, CI workflow, or project-wide build system. Do not infer JavaScript/Python packaging commands for this repository.
- The plugin requires Vim 8.0+ with `InsertLeavePre` and Python 3 support (`+python3` or `+python3_dynamic`); Neovim is explicitly disabled.
- `python/CodeEditor.py` implements OllamaEdit and its file/tool operations; `tests/` contains the pytest unit tests for that logic.

## Setup And Dependencies

- The setup wizard writes user configuration to `~/.vim/config/ollama.vim` and, when enabled, creates `~/.vim/venv/ollama`. These are outside the repository and should not be added as project files.
- Python runtime dependencies are `httpx>=0.23.3`, `requests`, and `jinja2`; `mistralai` and `openai` are optional provider dependencies. The setup wizard can create and populate the plugin venv.
- Ollama-backed behavior requires a reachable Ollama server, normally `http://localhost:11434`; provider integration tests may also require API keys or UNIX `pass` credentials.
- OllamaEdit workspace mode can modify project files and run configured tools; review changes and use the documented bubblewrap-secured build helper (`scripts/mk`) when configuring AI-driven builds.

## Model Configs

- Ollama code completion models must support fill-in-the-middle tokens and have a matching JSON file under `python/configs/`; generic chat-only models do not work for completion.
- `python/configs/README.md` defines the model-name fallback lookup. Preserve the exact whitespace in FIM token values because it affects prompts.

## Verification

- Run `pytest -q tests/test_codeeditor_tools.py` for the dependency-mocked unit tests.
- Run `python3 -m compileall -q python` for a dependency-free Python syntax check.
- Run `bash -n test/docker/build.sh test/docker/run.sh` for the Docker helper syntax check.
- Run the live completion integration test from `python/`: `./test-completion.py [provider [model]]`. It calls configured external services and credentials, and reports per-model failures without making the whole script fail reliably.
- The container smoke test must be run from `test/docker/`: `./build.sh` then `./run.sh`. Both scripts use `sudo docker`; `run.sh` expects the image built by `build.sh`, mounts the repository into the container, and uses host networking.
