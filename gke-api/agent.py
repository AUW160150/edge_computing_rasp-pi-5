import anthropic
import requests


def run_agent(task_description: str, pi_url: str, pi_token: str, anthropic_api_key: str, emit=None) -> dict:
    """
    Uses Claude to interpret a task description, then executes shell commands
    on the Raspberry Pi via its /execute HTTP endpoint.
    Returns a dict with the final result and all commands run.
    """
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    tools = [
        {
            "name": "run_command",
            "description": (
                "Execute a shell command on the Raspberry Pi edge device and return its output. "
                "Use this to inspect the device, run scripts, or perform compute tasks."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run on the Raspberry Pi.",
                    }
                },
                "required": ["command"],
            },
        }
    ]

    messages = [
        {
            "role": "user",
            "content": (
                "You are an agent with access to a Raspberry Pi 5 edge device. "
                "Use the run_command tool to complete the following task. "
                "When done, summarize what you did and the outcome.\n\n"
                f"Task: {task_description}"
            ),
        }
    ]

    commands_run = []

    for _ in range(10):  # max 10 tool-use rounds
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            summary = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "Task completed.",
            )
            if emit:
                emit("summary", {"text": summary})
            return {"summary": summary, "commands_run": commands_run}

        if response.stop_reason == "tool_use":
            # Emit any text Claude produced before calling a tool (its reasoning)
            for block in response.content:
                if hasattr(block, "text") and block.text and emit:
                    emit("thought", {"text": block.text})

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use" and block.name == "run_command":
                    command = block.input["command"]
                    if emit:
                        emit("command", {"command": command})
                    output = _execute_on_pi(command, pi_url, pi_token)
                    if emit:
                        emit("output", {"command": command, "output": output})
                    commands_run.append({"command": command, "output": output})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": output,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

    return {"summary": "Reached max iterations.", "commands_run": commands_run}


def _execute_on_pi(command: str, pi_url: str, pi_token: str) -> str:
    """POST a command to the Pi's /execute endpoint and return the output string."""
    # Route Pi traffic through Tailscale SOCKS5 proxy
    proxies = {"http": "socks5h://localhost:1055", "https": "socks5h://localhost:1055"}
    try:
        resp = requests.post(
            f"{pi_url}/execute",
            json={"command": command},
            headers={"X-Pi-Token": pi_token},
            timeout=60,
            proxies=proxies,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("output", "").strip() or f"(exit code {data.get('exit_code', '?')})"
        return f"Error: HTTP {resp.status_code} — {resp.text}"
    except requests.Timeout:
        return "Error: command timed out after 60s"
    except Exception as e:
        return f"Connection error: {e}"
