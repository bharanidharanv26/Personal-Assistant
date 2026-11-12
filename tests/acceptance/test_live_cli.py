import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def test_installed_cli_with_real_loopback_server(config, tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {
        **os.environ,
        "NILA_API_TOKEN": config.api_token.get_secret_value(),
        "NILA_DATA_DIR": str(config.data_dir),
        "NILA_LLM_PROVIDER": "demo",
        "NILA_PORT": str(port),
        "PYTHONIOENCODING": "utf-8",
    }
    cli = Path(sys.executable).parent / ("nila.exe" if os.name == "nt" else "nila")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "nila.api.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )

    def run(*args, input_text=None):
        result = subprocess.run(
            [str(cli), *args],
            cwd=tmp_path,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    try:
        deadline = time.monotonic() + 20
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={"Authorization": f"Bearer {env['NILA_API_TOKEN']}"},
            timeout=1,
            trust_env=False,
        ) as client:
            while True:
                assert server.poll() is None, server.communicate(timeout=5)[0]
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "Local service did not become ready"
                time.sleep(0.05)

        assert json.loads(run("status"))["automation"] == "dry_run_only"
        memory = json.loads(run("memory", "add", "I prefer jasmine tea", "--kind", "preference"))
        chat = json.loads(run("chat", "What tea do I prefer?"))
        assert chat["memory_ids"] == [memory["id"]]
        plan = json.loads(run("task", "plan", "Simulate a tea break"))
        run("action", "approve", plan["actions"][0]["id"], input_text="y\n")
        task = json.loads(run("task", "run", plan["id"]))
        assert task["status"] == "succeeded"
        assert task["actions"][0]["result"]["simulated"] is True
        run("feedback", "task", plan["id"], "--rating", "1")
        assert json.loads(run("evaluate"))["positive_feedback"] == 1
    finally:
        server.terminate()
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate(timeout=5)
