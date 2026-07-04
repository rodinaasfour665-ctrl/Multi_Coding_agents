import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# CONFIG - change these two lines for your setup
# ---------------------------------------------------------------------------

MODEL = "gpt-oss:120b-cloud"   
OLLAMA_URL = "http://localhost:11434/api/chat"

WORKSPACE = None


# ---------------------------------------------------------------------------
# TOOL DEFINITIONS - this is just a description sent to the model so it
# knows what actions it is allowed to request.
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create a new code file or overwrite an existing one inside "
                "the workspace. Choose a sensible filename and extension "
                "based on what the user asked for. If the file already "
                "exists, it will be backed up automatically before being "
                "overwritten."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Filename, relative to the workspace."},
                    "content": {"type": "string", "description": "Full content to write to the file."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the text content of an existing file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Filename, relative to the workspace."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a terminal command inside the workspace folder (e.g. to list files).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# WORKSPACE SECURITY HELPER
# ---------------------------------------------------------------------------

def safe_path(path_str):
    
    try:
        candidate = Path(path_str)
        if not candidate.is_absolute():
            candidate = WORKSPACE / candidate
        resolved = candidate.resolve()
        if resolved.is_relative_to(WORKSPACE):
            return resolved
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PRE-MODEL SECURITY GATE
# ---------------------------------------------------------------------------

FILE_ACTION_KEYWORDS = ("explain", "read", "modify", "update", "edit", "fix", "change")

PATH_PATTERN = re.compile(
    r"[A-Za-z]:\\\S+|/\S+|(?:\.{1,2}[/\\])?[\w\-./\\]+\.[A-Za-z0-9]{1,10}"
)


def extract_referenced_path(text):
    """Try to find something that looks like a file path in the user's text."""
    match = PATH_PATTERN.search(text)
    if match:
        return match.group(0).strip().strip(".,;:'\"")
    return None


def precheck_file_reference(user_text):
   
    lower = user_text.lower()
    if not any(keyword in lower for keyword in FILE_ACTION_KEYWORDS):
        return None  # not a file-referencing request

    referenced = extract_referenced_path(user_text)
    if referenced is None:
        return None  # no path-like token found, let the model ask for clarification

    target = safe_path(referenced)
    if target is None:
        return "[ERROR] Access denied. Files outside the selected workspace are not allowed."

    if not target.exists():
        return "[ERROR] File not found inside workspace."

    return None  # path is valid and inside the workspace, safe to proceed


# ---------------------------------------------------------------------------
# TOOL IMPLEMENTATIONS - this is where tool calls become real actions.
# Every function returns a short text string that gets sent back to the
# model as the tool's result.
# ---------------------------------------------------------------------------

def write_file(path, content):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace, request refused."

    try:
        backup_note = ""
        if target.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target.with_name(target.name + f".backup_{timestamp}")
            try:
                shutil.copy2(target, backup_path)
                backup_note = f" (backup created: {backup_path.name})"
            except OSError as e:
                return f"error: backup creation failed, file NOT modified: {e}"

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote file: {target}{backup_note}"

    except OSError as e:
        return f"error writing file: {e}"


def read_file(path):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace, request refused."

    if not target.exists():
        return f"error: file does not exist: {target}"

    try:
        return target.read_text(encoding="utf-8")
    except OSError as e:
        return f"error reading file: {e}"


def run_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,          # always run inside the workspace folder
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"tool error: {e}"


def run_tool(name, args):
    
    if name == "write_file":
        return write_file(args["path"], args["content"])
    if name == "read_file":
        return read_file(args["path"])
    if name == "run_command":
        return run_command(args["command"])
    return f"unknown tool: {name}"


# ---------------------------------------------------------------------------
# TALKING TO THE MODEL
# ---------------------------------------------------------------------------

def ask_ollama(messages):
    
    headers = {}
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
            },
            headers=headers,
            timeout=300,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"could not reach Ollama at {OLLAMA_URL}: {e}")

    if response.status_code == 401 or response.status_code == 403:
        raise RuntimeError(
            "authentication failed - if you're using a cloud model, make "
            "sure you're signed in (`ollama signin`) or that OLLAMA_API_KEY "
            "is set correctly."
        )

    if response.status_code != 200:
        raise RuntimeError(f"Ollama returned an error (status {response.status_code}): {response.text}")

    try:
        data = response.json()
        message = data["message"]
    except (ValueError, KeyError):
        raise RuntimeError("invalid response from the model (could not parse JSON / missing 'message').")

    if not message.get("content") and not message.get("tool_calls"):
        raise RuntimeError("empty response from the model.")

    return message


# ---------------------------------------------------------------------------
# WORKSPACE SETUP
# ---------------------------------------------------------------------------

def get_workspace():
   
    while True:
        raw = input("Enter the workspace folder path: ").strip()
        if raw.lower() in ("exit", "quit"):
            raise SystemExit()

        path = Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"error: that folder does not exist: {path}")
            continue
        if not path.is_dir():
            print(f"error: that path is not a folder: {path}")
            continue

        print(f"workspace set to: {path}\n")
        return path


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------

def main():
    global WORKSPACE

    print(f"Simple coding agent - model={MODEL}")
    WORKSPACE = get_workspace()
    print("Type 'exit' to quit.\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a coding agent working ONLY inside one workspace folder. "
                "Use the write_file tool to create or modify code files - pick a "
                "sensible filename and extension based on the user's request. "
                "Use the read_file tool before explaining or modifying a file. "
                "Use run_command only for simple things like listing files. "
                "Never try to access paths outside the workspace. "
                "You MUST use read_file before explaining any file's content - "
                "never explain a file from general knowledge, even if you "
                "recognize its name or path. "
                "You MUST use read_file before modifying a file, so you edit "
                "the real current content, not an assumed version. "
                "If a file cannot be read through the tool, report that error "
                "instead of guessing or making up its contents. "
                "Never access, describe, or reference files outside the "
                "workspace, even well-known system files. "
                "When the task is finished, reply with a short final answer "
                "describing what you did."
            ),
        }
    ]

    while True:
        user_text = input("You> ").strip()

        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text:
            continue

        precheck_error = precheck_file_reference(user_text)
        if precheck_error:
            print(precheck_error + "\n")
            continue

        messages.append({"role": "user", "content": user_text})

        for step in range(1, 11):
            try:
                assistant_message = ask_ollama(messages)
            except RuntimeError as e:
                print(f"error: {e}\n")
                messages.pop()  
                break

            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls", [])

            if not tool_calls:
                print("Agent>", assistant_message.get("content", ""))
                print()
                break

            for tool_call in tool_calls:
                function = tool_call["function"]
                tool_name = function["name"]
                tool_args = function["arguments"]

                print(f"Tool {step}> {tool_name}({tool_args})")
                tool_result = run_tool(tool_name, tool_args)
                print(f"Result> {tool_result[:300]}")  

                messages.append({"role": "tool", "content": tool_result})
        else:
            print("Agent> stopped after too many tool steps\n")


if __name__ == "__main__":
    main()
