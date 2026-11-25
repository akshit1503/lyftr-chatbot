import os

import pytest

os.environ.update({
    "LLM_API_KEYS": "test-key-1,test-key-2",
    "ENABLE_FAILURE_SIMULATION": "true",
    "MOCK_LLM": "true",
    "ALLOWED_ORIGINS": "http://localhost:3000",
})


@pytest.fixture()
def client(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    from fastapi.testclient import TestClient
    from app import llm
    from app.main import app

    with TestClient(app) as c:  # lifespan: init db + fresh cache
        llm.setup_cache()
        yield c
