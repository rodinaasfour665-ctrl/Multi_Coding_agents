# Terminal Coding Agent — agent1.2.py vs agent2.1.py

This project has two versions of the same terminal coding agent:

- **`agent1.2.py`** — Task 1: a simple agent that creates, explains,
  and modifies code files inside a workspace folder.
- **`agent2.1.py`** — Task 2: builds on agent1.2 by adding the ability
  to **run** code, **detect errors**, and **fix them**, plus a small
  project memory file and clearer terminal logs.

Both run from the terminal, both talk to a model through **Ollama**,
and both only ever touch files inside one workspace folder you choose
at startup.

---

## Requirements (both versions)

- Python 3.9+
- The `requests` library
- [Ollama](https://ollama.com) installed and running, with a model
  available (local or cloud-hosted)
- Only for `agent2.1.py`, if you want to run those file types:
  - **Node.js** (`node`) to run `.js` files
  - **g++** to compile and run `.cpp` / `.cc` files

```bash
pip install requests
```

## Setup (both versions)

1. Check available models:
   ```bash
   ollama list
   ```
2. Open the agent file and set the `MODEL` constant near the top to
   match one of them, e.g. `MODEL = "gpt-oss:120b-cloud"`.
3. If it's a cloud-hosted model: `ollama signin`.
4. If your model needs an API key, set it as an environment variable
   (never hardcoded in the code):
   ```bash
   export OLLAMA_API_KEY="your-key-here"
   ```

## Running

```bash
python agent1.2.py     # Task 1 version
```
```bash
python agent2.1.py     # Task 2 version
```

Either way, you'll be asked for a workspace folder first, then you can
type requests until you type `exit` or `quit`.

---

## Main differences

| | `agent1.2.py` (Task 1) | `agent2.1.py` (Task 2) |
|---|---|---|
| **Tools** | `write_file`, `read_file`, `run_command` | `write_file`, `read_file`, `backup_file`, `list_files`, `run_file`, `run_command` |
| **Running code** | Not supported | `run_file` executes `.py`, `.js`, and `.cpp` files and returns real output |
| **Fixing errors** | Not supported | System prompt defines a full read → run → detect error → fix → run again loop |
| **Listing the workspace** | Not supported | `list_files` shows what's in the workspace |
| **Standalone backups** | Not supported | `backup_file` makes a backup without editing the file |
| **Dangerous commands** | Not checked | `run_command` refuses commands like `rm -rf`, `sudo`, `shutdown`, etc. |
| **Project memory** | None | `.agent_memory.json` saved in the workspace — recent files, last operations, last error, last fix attempt |
| **Terminal logging** | Basic (`Tool>`, `Result>`) | Structured (`[USER REQUEST]`, `[TOOL SELECTED]`, `[TARGET]`, `[RESULT]`, `[ERROR DETECTED]`, `[FIX ATTEMPT]`, `[FINAL STATUS]`) |
| **System prompt** | Short — workspace rules + when to use each tool | Longer — adds the explicit run/fix sequence and safety rules |
| **Security gate before the model sees a request** | Yes — blocks file-outside-workspace requests before calling the model | Same gate, kept in the Task 2 version |

In short: **agent1.2.py** can create, read, and edit files.
**agent2.1.py** can do all of that *plus* run the code, notice when it
fails, fix it, and remember what happened — while staying just as
simple to read through line by line.

---

## Example: what agent2.1.py can do that agent1.2.py can't

```
You> Open app.py, run it, find the error, fix it, and run it again.
[USER REQUEST] Open app.py, run it, find the error, fix it, and run it again.
[TOOL SELECTED] read_file
[TARGET] app.py
[RESULT] def add(a, b)
    return a + b
...
[TOOL SELECTED] run_file
[TARGET] app.py
[RESULT] File "app.py", line 1
    def add(a, b)
                 ^
SyntaxError: expected ':'
[ERROR DETECTED] File "app.py", line 1...
[TOOL SELECTED] write_file
[TARGET] app.py
[RESULT] wrote file: app.py (backup created: app.py.backup_20260704_101108)
[FIX ATTEMPT] Edited app.py after an error
[TOOL SELECTED] run_file
[TARGET] app.py
[RESULT] 5
Agent> Found a missing colon after the function signature in app.py, fixed it, and re-ran it — it now prints 5 successfully. A backup of the original file was saved.
[FINAL STATUS] done

You> exit
```

Trying the same request with `agent1.2.py` would fail after the first
step — it has no `run_file` tool, so it can't execute the code or see
the error at all.

---



Note: running `agent2.1.py` creates a `.agent_memory.json` file inside
whichever workspace folder you choose — that's expected, it's the
project memory file described in `MODEL_AND_DESIGN.md`.
