import json

from fastapi.testclient import TestClient

from nila.api.app import create_app


def test_full_workflow_persists_across_restart(config):
    headers = {"Authorization": f"Bearer {config.api_token.get_secret_value()}"}
    with TestClient(create_app(config), base_url="http://127.0.0.1", headers=headers) as client:
        memory = client.post("/memories", json={
            "content": "I prefer jasmine tea", "kind": "preference"
        })
        assert memory.status_code == 201
        assert memory.json()["allow_remote"] is False

        chat = client.post("/chat", json={"message": "What tea do I prefer?"})
        assert chat.status_code == 200
        assert "jasmine tea" in chat.json()["reply"]
        assert chat.json()["provider"] == "demo"
        assert chat.json()["memory_ids"] == [memory.json()["id"]]

        response = client.post("/tasks", json={"objective": "Plan a tea break"})
        assert response.status_code == 201
        task = response.json()
        action = task["actions"][0]
        assert client.post(f"/tasks/{task['id']}/run").status_code == 409
        assert client.post(f"/actions/{action['id']}/approve", json={
            "digest": "0" * 64
        }).status_code == 409
        assert client.post(f"/actions/{action['id']}/approve", json={
            "digest": action["digest"]
        }).status_code == 200
        result = client.post(f"/tasks/{task['id']}/run")
        assert result.status_code == 200
        assert result.json()["status"] == "succeeded"
        assert result.json()["actions"][0]["result"]["simulated"] is True
        assert client.post(f"/actions/{action['id']}/execute").status_code == 409

        assert client.post("/feedback", json={
            "target_type": "task", "target_id": task["id"], "rating": 1
        }).status_code == 200
        assert client.get("/evaluation").json()["positive_feedback"] == 1
        audit = client.get("/audit").json()
        assert "action_started" in {event["event"] for event in audit}
        assert "jasmine tea" not in json.dumps(audit)

    with TestClient(create_app(config), base_url="http://127.0.0.1", headers=headers) as restarted:
        assert restarted.get(f"/tasks/{task['id']}").json()["status"] == "succeeded"
        assert restarted.get("/memories/search", params={"q": "jasmine"}).json()[0]["id"] == (
            memory.json()["id"]
        )
        assert restarted.get("/evaluation").json()["positive_feedback"] == 1


def test_token_and_host_required(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"Authorization": ""}).status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/health", headers={"Host": "untrusted.example"}).status_code == 400
    assert client.post("/memories", headers={"Authorization": ""}, json={
        "content": "unauthorized"
    }).status_code == 401
    assert client.get("/memories").json() == []


def test_unknown_fields_and_invalid_feedback_are_rejected(client):
    assert client.post("/tasks", json={
        "objective": "hello", "approved": True
    }).status_code == 422
    assert client.post("/feedback", json={
        "target_type": "action", "target_id": "missing", "rating": 0
    }).status_code == 422
    assert client.post("/feedback", json={
        "target_type": "action", "target_id": "missing", "rating": 1
    }).status_code == 404


def test_feedback_updates_do_not_duplicate_or_create_memories(client):
    reply = client.post("/chat", json={"message": "hello"}).json()
    payload = {
        "target_type": "message", "target_id": reply["message_id"],
        "rating": 1, "correction": "I prefer brief replies",
    }
    first = client.post("/feedback", json=payload).json()
    payload["rating"] = -1
    second = client.post("/feedback", json=payload).json()
    assert first["id"] == second["id"]
    counts = client.get("/evaluation").json()
    assert counts["positive_feedback"] == 0
    assert counts["negative_feedback"] == 1
    assert client.get("/memories").json() == []
