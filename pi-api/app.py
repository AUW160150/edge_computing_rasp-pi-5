import os
import subprocess
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)

PI_TOKEN = os.environ.get("PI_EXECUTE_TOKEN", "")


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Pi-Token")
        if not PI_TOKEN or token != PI_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return jsonify({"status": "ok", "device": "raspberry-pi-5"})


@app.route("/ping")
def ping():
    return "pong"


@app.route("/execute", methods=["POST"])
@require_token
def execute():
    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "Missing 'command' field"}), 400

    command = data["command"]

    # Run command in an isolated throwaway container:
    # --rm            destroyed immediately after exit
    # --network=none  no internet access
    # --memory=512m   killed if it exceeds 512MB RAM
    # --cpus=0.5      capped at half a CPU core
    # --user=nobody   runs as unprivileged user
    # --stop-timeout  gives Docker 55s to stop before force kill
    sandbox_cmd = [
        "docker", "run", "--rm",
        "--network=none",
        "--memory=512m",
        "--cpus=0.5",
        "--user=nobody",
        "--stop-timeout=55",
        "python:3.11-slim",
        "sh", "-c", command,
    ]

    try:
        result = subprocess.run(
            sandbox_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 137:
            return jsonify({"error": "Command killed — exceeded 512MB memory limit"}), 400
        if result.returncode == 124:
            return jsonify({"error": "Command timed out after 60s"}), 408

        return jsonify({
            "command": command,
            "output": result.stdout + result.stderr,
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Command timed out after 60s"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status")
@require_token
def status():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return jsonify({
            "cpu_percent": cpu,
            "memory": {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "percent": disk.percent,
            },
        })
    except ImportError:
        return jsonify({"error": "psutil not installed"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
# updated
