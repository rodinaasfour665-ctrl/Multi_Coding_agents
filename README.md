# Terminal Coding Agent (agent1.2.py)

A terminal-based coding agent that can create, explain, and modify code
files inside one selected workspace folder. The agent talks to a model
through **Ollama** and lets the model decide which tool to use
(`read_file`, `write_file`, or `run_command`).

---

## Requirements

- Python 3.9+
- The `requests` library
- [Ollama](https://ollama.com) installed and running
- A model pulled/available in Ollama (local or cloud-hosted)

Install the Python dependency:

```bash
pip install requests
```

---

## Setup

1. Make sure Ollama is installed and running, and check which models
   you have available:

   ```bash
   ollama list
   ```

2. Open `agent1.2.py` and set the `MODEL` constant near the top of the
   file to match a model from that list, for example:

   ```python
   MODEL = "gpt-oss:120b-cloud"
   ```

3. If you're using a cloud-hosted model that requires sign-in:

   ```bash
   ollama signin
   ```

4. If your model needs an API key, set it as an environment
   variable — the key is never hardcoded in the code:

   **macOS / Linux:**
   ```bash
   export OLLAMA_API_KEY="your-key-here"
   ```

   **Windows (PowerShell):**
   ```powershell
   $env:OLLAMA_API_KEY="your-key-here"
   ```

---

## Running the agent

```bash
python agent1.2.py
```

You'll be asked to enter a workspace folder path first:

```
Enter the workspace folder path: /home/user/my_project
workspace set to: /home/user/my_project

Type 'exit' to quit.
```

Then you can type requests freely, for example:

```
You> Create a python file that prints Hello World
Tool 1> write_file({'path': 'hello.py', 'content': "print('Hello World')"})
Result> wrote file: /home/user/my_project/hello.py
Agent> Created hello.py, which prints "Hello World".

You> Explain hello.py
Tool 1> read_file({'path': 'hello.py'})
Result> print('Hello World')
Agent> This file prints the text "Hello World" to the console.

You> Modify hello.py and add a comment above the print statement
Tool 1> read_file({'path': 'hello.py'})
Tool 2> write_file({'path': 'hello.py', 'content': "# Greets the user\nprint('Hello World')"})
Result> wrote file: /home/user/my_project/hello.py (backup created: hello.py.backup_20260701_101500)
Agent> Added a comment above the print statement and saved a backup.

You> exit
```

Type `exit` or `quit` at any prompt to stop the program.

---

## Example requests you can try

| Type    | Example |
|---------|---------|
| Create  | "Create a Python file that prints Hello World" |
| Create  | "Create a C++ file that implements a simple calculator" |
| Create  | "Create an HTML page with a title and a button" |
| Explain | "Explain main.py" |
| Modify  | "Modify app.py and add input validation" |

---

## Files

```
agent1.2.py             <- the agent (single Python file)
README.md               <- this file
MODEL_AND_DESIGN.md     <- which model/API is used and how the agent works
```
