import os
import uuid
import json
import time
import logging
import threading
from queue import Queue
from functools import wraps
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from google.cloud import secretmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["X-API-Key", "Content-Type"]}})

# In-memory task store and queue (single pod — fine for this project scale)
tasks = {}
task_queue = Queue()

# Secrets loaded at startup
_secrets = {}

# Pi liveness state
pi_health = {"online": False, "last_checked": None, "error": "not yet checked"}


def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get("GCP_PROJECT_ID", "rodela-trial-project")
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()


def load_secrets():
    for key in ["gke-api-key", "pi-tunnel-url", "pi-execute-token", "anthropic-api-key"]:
        _secrets[key] = get_secret(key)
    logger.info("Secrets loaded successfully")


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key or key != _secrets.get("gke-api-key"):
            logger.warning("Unauthorized request to %s from %s", request.path, request.remote_addr)
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def pi_monitor():
    """Background thread: checks Pi reachability every 30 seconds."""
    import requests
    proxies = {"http": "socks5h://localhost:1055", "https": "socks5h://localhost:1055"}
    # Wait for secrets to be loaded before first check
    while not _secrets.get("pi-tunnel-url"):
        time.sleep(1)

    while True:
        try:
            resp = requests.get(
                f"{_secrets['pi-tunnel-url']}/status",
                headers={"X-Pi-Token": _secrets["pi-execute-token"]},
                timeout=10,
                proxies=proxies,
            )
            if resp.status_code == 200:
                if not pi_health["online"]:
                    logger.info("Pi is back online")
                pi_health["online"] = True
                pi_health["error"] = None
            else:
                raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            if pi_health["online"]:
                logger.error("Pi went offline: %s", e)
            pi_health["online"] = False
            pi_health["error"] = str(e)
        pi_health["last_checked"] = time.time()
        time.sleep(30)


def worker():
    """Background thread: pulls tasks off queue and runs the agent."""
    from agent import run_agent
    while True:
        task_id = task_queue.get()
        tasks[task_id]["status"] = "running"
        description = tasks[task_id]["description"]
        logger.info("Task %s started: %s", task_id, description)
        try:
            def emit(event_type, data):
                tasks[task_id]["logs"].append({"type": event_type, "data": data})
                if event_type == "command":
                    logger.info("Task %s agent running command: %s", task_id, data.get("command"))
                elif event_type == "output" and data.get("output", "").startswith("Connection error"):
                    logger.error("Task %s Pi connection error: %s", task_id, data.get("output"))

            result = run_agent(
                task_description=description,
                pi_url=_secrets["pi-tunnel-url"],
                pi_token=_secrets["pi-execute-token"],
                anthropic_api_key=_secrets["anthropic-api-key"],
                emit=emit,
            )
            tasks[task_id]["status"] = "done"
            tasks[task_id]["result"] = result
            logger.info("Task %s completed successfully", task_id)
        except Exception as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["result"] = {"error": str(e)}
            logger.error("Task %s failed: %s", task_id, e)
        finally:
            task_queue.task_done()


@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "pi-agent-api"})


@app.route("/health")
def health():
    return jsonify({
        "api": "ok",
        "pi": {
            "online": pi_health["online"],
            "last_checked": pi_health["last_checked"],
            "error": pi_health["error"],
        },
    })


@app.route("/tasks", methods=["POST"])
@require_auth
def create_task():
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "Missing 'description' field"}), 400

    if not pi_health["online"]:
        logger.warning("Task rejected — Pi is offline: %s", pi_health["error"])
        return jsonify({"error": "Pi is offline", "detail": pi_health["error"]}), 503

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "description": data["description"],
        "status": "queued",
        "result": None,
        "logs": [],
    }
    task_queue.put(task_id)
    logger.info("Task %s queued: %s", task_id, data["description"])
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
        logger.error("Pi unreachable at %s: %s", _secrets.get("pi-tunnel-url"), e)
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
        last_log_idx = 0
        while True:
            task = tasks.get(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                break

            # Emit any new log entries since last poll
            logs = task.get("logs", [])
            for entry in logs[last_log_idx:]:
                yield f"data: {json.dumps({'type': 'log', 'entry': entry})}\n\n"
            last_log_idx = len(logs)

            # Emit status changes
            current_status = task["status"]
            if current_status != last_status:
                yield f"data: {json.dumps({'type': 'status', 'id': task['id'], 'status': current_status})}\n\n"
                last_status = current_status

            if current_status in ("done", "error"):
                yield f"data: {json.dumps({'type': 'result', 'result': task['result']})}\n\n"
                break

            time.sleep(0.5)

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
    threading.Thread(target=pi_monitor, daemon=True).start()
    logger.info("pi-agent-api started")
    app.run(host="0.0.0.0", port=8080)
