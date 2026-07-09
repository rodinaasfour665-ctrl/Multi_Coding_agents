import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# CONFIG - change these two lines for your setup
# ---------------------------------------------------------------------------

MODEL = ""   
OLLAMA_URL = ""

WORKSPACE = None                    
MEMORY_FILE = ".agent_memory.json"  


DANGEROUS = ["rm -rf", "sudo", "mkfs", "shutdown", "reboot", "format ", "del /f", ":(){"]


# ---------------------------------------------------------------------------
# TOOLS 
# ---------------------------------------------------------------------------

TOOLS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create a file, or overwrite an existing one (a backup is made automatically first).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "backup_file",
        "description": "Make a timestamped backup copy of a file without changing it.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List the files in the workspace.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "run_file",
        "description": "Run a code file (.py, .js, or .cpp) and return its output, so errors can be found and fixed.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a simple terminal command inside the workspace. Dangerous commands are refused.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]},
    }},
]


# ---------------------------------------------------------------------------
# WORKSPACE SECURITY
# ---------------------------------------------------------------------------

def safe_path(path_str):
    
    try:
        candidate = Path(path_str)
        if not candidate.is_absolute():
            candidate = WORKSPACE / candidate
        resolved = candidate.resolve()
        return resolved if resolved.is_relative_to(WORKSPACE) else None
    except Exception:
        return None


FILE_WORDS = ("explain", "read", "modify", "update", "edit", "fix", "change", "run", "open")


def precheck_file_reference(user_text):
    lower = user_text.lower()
    
    if any(word in lower for word in ("create", "make", "generate", "write")):
        return None
    
    if not any(w in lower for w in FILE_WORDS):
        return None

    for token in user_text.replace("\\", "/").split():
        token = token.strip(".,;:'\"")
        if "." in token or "/" in token:
            target = safe_path(token)
            if target is None:
                return "[ERROR] Access denied. Files outside the selected workspace are not allowed."
            if not target.exists():
                return "[ERROR] File not found inside workspace."
            return None 

    return None 


# ---------------------------------------------------------------------------
# MEMORY - one small JSON file inside the workspace
# ---------------------------------------------------------------------------

def load_memory():
    path = WORKSPACE / MEMORY_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"workspace": str(WORKSPACE), "recent_files": [], "operations": [],
            "last_error": None, "last_fix_attempt": None}


def update_memory(memory, tool_name, tool_args, result):
    path_arg = tool_args.get("path")
    if path_arg:
        if path_arg in memory["recent_files"]:
            memory["recent_files"].remove(path_arg)
        memory["recent_files"] = [path_arg] + memory["recent_files"][:9]

    memory["operations"] = memory["operations"][-19:] + [{
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tool": tool_name, "args": tool_args, "result": result[:200],
    }]

    if tool_name in ("run_file", "run_command"):
        lower = result.lower()
        is_error = "error" in lower or "traceback" in lower or "exception" in lower
        memory["last_error"] = result[:500] if is_error else None

    if tool_name == "write_file" and memory.get("last_error"):
        memory["last_fix_attempt"] = f"Edited {path_arg} after an error"

    try:
        (WORKSPACE / MEMORY_FILE).write_text(json.dumps(memory, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[WARN] could not save memory file: {e}")
    return memory


# ---------------------------------------------------------------------------
# TOOL IMPLEMENTATIONS 
# ---------------------------------------------------------------------------

def backup(target):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_name(target.name + f".backup_{stamp}")
    try:
        shutil.copy2(target, backup_path)
        return f" (backup created: {backup_path.name})"
    except OSError as e:
        return f"error: backup failed, file NOT changed: {e}"


def write_file(path, content):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace."

    note = ""
    if target.exists():
        note = backup(target)
        if note.startswith("error"):
            return note

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote file: {target}{note}"
    except OSError as e:
        return f"error writing file: {e}"


def read_file(path):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace."
    if not target.exists():
        return f"error: file does not exist: {target}"
    try:
        return target.read_text(encoding="utf-8")
    except OSError as e:
        return f"error reading file: {e}"


def backup_file(path):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace."
    if not target.exists():
        return f"error: file does not exist, nothing to backup: {target}"
    return f"backup created for {target}{backup(target)}"


def list_files():
    try:
        names = [p.name for p in sorted(WORKSPACE.iterdir())
                 if MEMORY_FILE not in p.name and ".backup_" not in p.name]
        return "\n".join(names) if names else "(workspace is empty)"
    except OSError as e:
        return f"error listing files: {e}"


def run_file(path):
    target = safe_path(path)
    if target is None:
        return f"error: '{path}' is outside the workspace."
    if not target.exists():
        return f"error: file does not exist: {target}"

    ext = target.suffix.lower()
    try:
        if ext == ".py":
            cmd = [sys.executable, str(target)]
        elif ext == ".js":
            cmd = ["node", str(target)]
        elif ext in (".cpp", ".cc"):
            exe = target.with_suffix(".out")
            build = subprocess.run(["g++", str(target), "-o", str(exe)],
                                    cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
            if build.returncode != 0:
                return f"compile error:\n{build.stderr}"
            cmd = [str(exe)]
        else:
            return f"error: unsupported file type for running: {ext}"

        result = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        return output if output else "(ran successfully, no output)"

    except subprocess.TimeoutExpired:
        return "error: execution timed out (30s limit)"
    except FileNotFoundError as e:
        return f"error: required interpreter/compiler not found: {e}"
    except Exception as e:
        return f"error running file: {e}"


def run_command(command):
    if any(bad in command.lower() for bad in DANGEROUS):
        return f"error: this command was refused for safety reasons: {command}"
    try:
        result = subprocess.run(command, shell=True, cwd=WORKSPACE,
                                 capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "error: command timed out (60s limit)"
    except Exception as e:
        return f"tool error: {e}"


def run_tool(name, args):
    if name == "write_file":
        return write_file(args["path"], args["content"])
    if name == "read_file":
        return read_file(args["path"])
    if name == "backup_file":
        return backup_file(args["path"])
    if name == "list_files":
        return list_files()
    if name == "run_file":
        return run_file(args["path"])
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
        response = requests.post(OLLAMA_URL, headers=headers, timeout=300, json={
            "model": MODEL, "messages": messages, "tools": TOOLS, "stream": False})
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"could not reach Ollama at {OLLAMA_URL}: {e}")

    if response.status_code in (401, 403):
        raise RuntimeError("authentication failed - sign in (`ollama signin`) or check OLLAMA_API_KEY.")
    if response.status_code != 200:
        raise RuntimeError(f"Ollama returned an error (status {response.status_code}): {response.text}")

    try:
        message = response.json()["message"]
    except (ValueError, KeyError):
        raise RuntimeError("invalid response from the model.")

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
        elif not path.is_dir():
            print(f"error: that path is not a folder: {path}")
        else:
            print(f"workspace set to: {path}\n")
            return path


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a terminal coding agent working ONLY inside one workspace folder. "
    "Never access, describe, or reference any path outside it.\n"
    "Use read_file before explaining or editing a file - never answer from "
    "general knowledge. Use write_file to create or update a file (it backs "
    "up automatically). Use list_files if unsure what exists. Use run_file "
    "to execute a file and check its real output.\n"
    "If a request is unclear or a tool returns an error, say so plainly "
    "instead of guessing.\n"
    "To fix broken code: read_file, run_file, find the cause of the error, "
    "write_file with the corrected version, run_file again to confirm it "
    "works, then report what was wrong and what you changed. If it still "
    "fails, repeat rather than giving up after one try.\n"
    "Never attempt destructive or system-altering commands. "
    "When done, give a short final answer with the result."
)


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------

def main():
    global WORKSPACE

    print(f"Simple coding agent - model={MODEL}")
    WORKSPACE = get_workspace()
    print("Type 'exit' to quit.\n")

    memory = load_memory()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True: #طول ما اليوزر بيكتب
        user_text = input("You> ").strip()
        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text: # لو مكتبش حاجه سطر فاضي 
            continue

        print(f"[USER REQUEST] {user_text}")

        precheck_error = precheck_file_reference(user_text) # بيتاكد انه مطلعش برا الورك سبيس
        if precheck_error:
            print(precheck_error + "\n")
            continue

        messages.append({"role": "user", "content": user_text})
        status = "unknown"

        for step in range(20):
            try:
                assistant_message = ask_ollama(messages) # بيبعت ل اولاما البرومبت و مستنين الرد ب التولز و الارجيومنت
            except RuntimeError as e:
                print(f"[ERROR] {e}\n")
                messages.pop()
                status = "failed"
                break

            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls", [])

            if not tool_calls: # لو مفيش تولز رجعت بسبب مثلا بعتله رساله فيها هاي
                print("Agent>", assistant_message.get("content", ""))
                status = "done"
                break

            for call in tool_calls:
                name = call["function"]["name"] # بنتستخرج اسم التول  
                args = call["function"]["arguments"]  #"arguments":{ "path":"app.py"
                
                target = args.get("path") or args.get("command") or "-"

                print(f"[TOOL SELECTED] {name}")
                print(f"[TARGET] {target}")

                result = run_tool(name, args)
                print(f"[RESULT] {result[:300]}")

                memory = update_memory(memory, name, args, result)
                if memory.get("last_error") and name in ("run_file", "run_command"):
                    print(f"[ERROR DETECTED] {memory['last_error'][:200]}")
                if name == "write_file" and memory.get("last_fix_attempt"):
                    print(f"[FIX ATTEMPT] {memory['last_fix_attempt']}")

                messages.append({"role": "tool", "content": result})
                if memory.get("last_error") and name in ("run_file", "run_command"):
                    messages.append({
                        "role": "user",
                        "content": (
                            "Execution failed. Automatically read the file, "
                            "diagnose the error, create a backup, fix the code, "
                            "run it again, and verify the result."
        )
    })
        else:
            print("Agent> stopped after too many tool steps")
            status = "stopped (too many steps)"

        print(f"[FINAL STATUS] {status}\n")


if __name__ == "__main__":
    main()
