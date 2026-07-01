# Task 1 — Simple Terminal Coding Agent (v1.2)

A terminal-based coding agent that creates, explains, and modifies code
files inside one selected workspace folder, using a local/cloud model
served through **Ollama**. The model decides which tool to call
(`read_file`, `write_file`, `run_command`) — this version adds a strict
security gate that stops any file-outside-workspace request before it
ever reaches the model.

**Main file: `agent1.2.py`**

---

## How the fix works (animated)

![Security gate animation](diagram.svg)

- 🟢 **Green dot** — a normal request: user → pre-check passes → model →
  tool call → result → back to the terminal for the next request.
- 🔴 **Red dot** — a request that references a file outside the
  workspace (or one that doesn't exist inside it): it's stopped **at the
  pre-check gate** and never reaches the model at all.

> GitHub and most browsers render the little SVG animation above
> natively — no extra viewer needed. If you're reading this somewhere
> that doesn't animate SVGs, open `diagram.svg` directly in a browser.

---

## The problem this version fixes

In the previous version, a request like:

```
You> Explain C:\Windows\System32\drivers\etc\hosts
```

was being handled incorrectly: the model answered using its own general
knowledge of what a `hosts` file typically contains, instead of being
blocked. That violates the core assignment rule:

> "The agent must only work inside the selected workspace folder."

The root cause: the workspace check only existed *inside* the tool
functions (`read_file`, `write_file`). If the model chose not to call a
tool at all — and just answered from memory — nothing stopped it.

## The fix

A **pre-check gate** now runs before any user message is sent to the
model:

1. Look at the user's text. If it contains a file-action keyword
   (`explain`, `read`, `modify`, `update`, `edit`, `fix`, `change`) —
   continue. Otherwise, skip the gate (nothing to check yet).
2. Try to extract something that looks like a file path from the text
   (Windows absolute path, Unix absolute path, or a relative
   filename/extension).
3. Run that path through the exact same `safe_path()` function the
   tools already use, to resolve it and check it's inside the
   workspace.
4. Decide:
   - Path resolves **outside** the workspace →
     `[ERROR] Access denied. Files outside the selected workspace are not allowed.`
     and the model is **never called**.
   - Path resolves **inside** the workspace but the file **doesn't
     exist** → `[ERROR] File not found inside workspace.` and the model
     is **never called**.
   - Path is inside the workspace and exists → request proceeds to the
     model as normal.

The system prompt was also strengthened with explicit rules: the model
must use `read_file` before explaining or modifying anything, must
never answer from general knowledge, and must never touch files outside
the workspace.

Everything else — create file, explain file, modify file, automatic
backups, the tool-calling loop, workspace selection at startup — is
unchanged from the previous version.

---

## Setup

**Requirements:** Python 3.9+, the `requests` library, and
[Ollama](https://ollama.com) installed and running.

```bash
pip install requests
```

Pull or sign in to whatever model you're using (edit the `MODEL`
constant near the top of `agent1.2.py` to match):

```bash
ollama list          # see available models
ollama signin         # only needed for cloud-hosted models
```

If your model needs an API key, set it as an environment variable —
never hardcode it:

```bash
export OLLAMA_API_KEY="your-key-here"
```

## Running

```bash
python agent1.2.py
```

You'll be asked for a workspace folder, then you can type requests
until you type `exit` or `quit`.

```
Enter the workspace folder path: /home/user/my_project
workspace set to: /home/user/my_project

Type 'exit' to quit.

You> Create a python file that prints Hello World
Tool 1> write_file({'path': 'hello.py', 'content': "print('Hello World')"})
Result> wrote file: /home/user/my_project/hello.py
Agent> Created hello.py which prints "Hello World".

You> Explain C:\Windows\System32\drivers\etc\hosts
[ERROR] Access denied. Files outside the selected workspace are not allowed.

You> Explain hello.py
Tool 1> read_file({'path': 'hello.py'})
Result> print('Hello World')
Agent> This file prints the text "Hello World" to the console.

You> Modify hello.py and add a comment
Tool 1> read_file({'path': 'hello.py'})
Tool 2> write_file({'path': 'hello.py', 'content': "# Prints a greeting\nprint('Hello World')"})
Result> wrote file: /home/user/my_project/hello.py (backup created: hello.py.backup_20260701_101500)
Agent> Added a comment above the print statement. Backup saved.

You> exit
```

---

## Test cases to try live

| Request | Expected result |
|---|---|
| `Create a python file that prints Hello World` | New file created inside workspace |
| `Explain hello.py` (exists) | Model reads the file via `read_file`, explains its real content |
| `Explain missing.py` (doesn't exist) | `[ERROR] File not found inside workspace.` — model never called |
| `Explain C:\Windows\System32\drivers\etc\hosts` | `[ERROR] Access denied...` — model never called |
| `Modify hello.py and add a comment` | Backup created, file updated, backup path printed |
| `Modify /etc/passwd and add a line` | `[ERROR] Access denied...` — model never called |

---

## Files in this delivery

```
agent1.2.py     <- the agent (single file, fixed security gate)
diagram.svg      <- animated flow diagram used above
README.md        <- this file
```
