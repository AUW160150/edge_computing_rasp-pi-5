import os
import uuid
import json
import time
import threading
from queue import Queue
from functools import wraps
from flask import Flask, request, jsonify, Response, stream_with_context
from google.cloud import secretmanager

app = Flask(__name__)

# In-memory task store and queue (single pod — fine for this project scale)
tasks = {}
task_queue = Queue()

# Secrets loaded at startup
_secrets = {}


def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get("GCP_PROJECT_ID", "rodela-trial-project")
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()


def load_secrets():
    for key in ["gke-api-key", "pi-tunnel-url", "pi-execute-token", "anthropic-api-key"]:
        _secrets[key] = get_secret(key)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key or key != _secrets.get("gke-api-key"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def worker():
    """Background thread: pulls tasks off queue and runs the agent."""
    from agent import run_agent
    while True:
        task_id = task_queue.get()
        tasks[task_id]["status"] = "running"
        try:
            result = run_agent(
                task_description=tasks[task_id]["description"],
                pi_url=_secrets["pi-tunnel-url"],
                pi_token=_secrets["pi-execute-token"],
                anthropic_api_key=_secrets["anthropic-api-key"],
            )
            tasks[task_id]["status"] = "done"
            tasks[task_id]["result"] = result
        except Exception as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["result"] = {"error": str(e)}
        finally:
            task_queue.task_done()


@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "pi-agent-api"})


@app.route("/tasks", methods=["POST"])
@require_auth
def create_task():
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "Missing 'description' field"}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "description": data["description"],
        "status": "queued",
        "result": None,
    }
    task_queue.put(task_id)
    return jsonify({"task_id": task_id, "status": "queued"}), 202


@app.route("/tasks/<task_id>", methods=["GET"])
@require_auth
def get_task(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/tasks", methods=["GET"])
@require_auth
def list_tasks():
    return jsonify(list(tasks.values()))


@app.route("/pi/status", methods=["GET"])
@require_auth
def pi_status():
    import requests
    proxies = {"http": "socks5h://localhost:1055", "https": "socks5h://localhost:1055"}
    try:
        resp = requests.get(
            f"{_secrets['pi-tunnel-url']}/status",
            headers={"X-Pi-Token": _secrets["pi-execute-token"]},
            timeout=10,
            proxies=proxies,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": f"Could not reach Pi: {e}"}), 503


@app.route("/tasks/<task_id>/stream", methods=["GET"])
@require_auth
def stream_task(task_id):
    """
    SSE endpoint — developer connects once and gets pushed updates
    as the task moves through queued → running → done/error.
    """
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    def event_stream():
        last_status = None
        while True:
            task = tasks.get(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                break

            current_status = task["status"]

            if current_status != last_status:
                yield f"data: {json.dumps(task)}\n\n"
                last_status = current_status

            if current_status in ("done", "error"):
                break

            time.sleep(1)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    load_secrets()
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
