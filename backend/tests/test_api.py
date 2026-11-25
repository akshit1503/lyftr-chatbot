def chat(client, sid, msg, headers=None, **extra):
    return client.post("/chat", json={"session_id": sid, "message": msg, **extra}, headers=headers or {})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_chat_live_then_cache_in_new_session(client):
    a = chat(client, "s-1", "What is the capital of France?")
    assert a.status_code == 200
    ma = a.json()["metadata"]
    assert ma["resolution_source"] == "LIVE_INFERENCE"
    assert ma["key_id"] == "key_1" and ma["fallback_attempts"] == 0
    assert ma["input_tokens"] > 0 and ma["output_tokens"] > 0

    b = chat(client, "s-2", "What is the capital of France?")
    mb = b.json()["metadata"]
    assert mb["resolution_source"] == "LLM_CACHE"
    assert mb["key_id"] is None and mb["fallback_attempts"] == 0
    assert b.json()["reply"] == a.json()["reply"]
    assert mb["input_tokens"] == ma["input_tokens"]
    assert isinstance(mb["latency_ms"], int)


def test_different_message_never_cached(client):
    chat(client, "s-1", "hello there")
    r = chat(client, "s-2", "something else entirely")
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_failover_key1_429(client):
    r = chat(client, "s-f", "failover one", {"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    md = r.json()["metadata"]
    assert md["key_id"] == "key_2" and md["fallback_attempts"] == 1
    assert md["resolution_source"] == "LIVE_INFERENCE"


def test_failover_key1_500(client):
    r = chat(client, "s-f", "failover two", {"X-Simulate-Failure": "key_1=500"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_all_keys_fail_503_and_history_untouched(client):
    r = chat(client, "s-503", "will fail", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/s-503/messages").status_code == 404


def test_both_keys_listed_503(client):
    r = chat(client, "s-503b", "will fail", {"X-Simulate-Failure": "key_1=429,key_2=500"})
    assert r.status_code == 503


def test_simulation_disabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "false")
    r = chat(client, "s-off", "no simulation", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200


def test_validation_errors(client):
    assert client.post("/chat", json={"session_id": "s", "message": "   "}).status_code == 422
    assert client.post("/chat", json={"session_id": "s", "message": "x" * 4001}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 422
    assert client.post("/chat", json={"session_id": "", "message": "hi"}).status_code == 422
    r = client.post("/chat", content="{bad json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()


def test_multi_turn_history_and_isolation(client):
    chat(client, "s-a", "first message")
    chat(client, "s-a", "second message")
    chat(client, "s-b", "other session")
    h = client.get("/sessions/s-a/messages").json()
    assert h["session_id"] == "s-a"
    assert [m["role"] for m in h["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in h["messages"] if m["role"] == "user"] == ["first message", "second message"]
    assert h["messages"][1]["metadata"].keys() >= {"resolution_source", "input_tokens", "output_tokens"}
    assert len(client.get("/sessions/s-b/messages").json()["messages"]) == 2


def test_system_prompt_changes_cache_key(client):
    a = chat(client, "s-p1", "same text", system_prompt="You are a pirate.")
    b = chat(client, "s-p2", "same text", system_prompt="You are a poet.")
    assert b.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert a.status_code == 200


def test_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}
