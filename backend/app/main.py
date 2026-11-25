import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import db, llm
from .config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    llm.setup_cache()
    yield


app = FastAPI(title="LLM Chatbot with Key Failover and Caching", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str
    system_prompt: Optional[str] = None

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 4000:
            raise ValueError("message must be 1-4000 characters after trimming")
        return v


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.exception_handler(RequestValidationError)
async def validation(_: Request, exc: RequestValidationError):
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health")
def health():
    if not db.ping() or not settings.keys:
        return JSONResponse(status_code=503, content={"detail": "not ready"})
    return {"status": "ok", "keys_configured": len(settings.keys), "cache_enabled": llm.cache_enabled()}


@app.post("/chat")
def chat(req: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None)):
    started = time.perf_counter()

    stored_prompt = db.get_system_prompt(req.session_id)
    system_prompt = req.system_prompt if req.system_prompt is not None else stored_prompt
    effective_prompt = (system_prompt or "").strip() or settings.default_system_prompt

    messages = [{"role": "system", "content": effective_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in db.get_history(req.session_id)]
    messages.append({"role": "user", "content": req.message})

    try:
        result = llm.generate(messages, llm.parse_simulation(x_simulate_failure))
    except llm.AllProvidersUnavailable:
        return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})

    metadata = {
        "resolution_source": "LLM_CACHE" if result.cached else "LIVE_INFERENCE",
        "model": result.model,
        "latency_ms": 0,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "key_id": result.key_id,
        "fallback_attempts": result.fallback_attempts,
    }
    metadata["latency_ms"] = max(1, int((time.perf_counter() - started) * 1000))

    # Only successful exchanges reach history.
    db.save_exchange(req.session_id, req.system_prompt, req.message, result.reply, metadata)

    return {"session_id": req.session_id, "reply": result.reply, "metadata": metadata}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    history = db.get_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="session not found")
    out = []
    for m in history:
        item = {"role": m["role"], "content": m["content"]}
        if m["role"] == "assistant" and "metadata" in m:
            md = m["metadata"]
            item["metadata"] = {
                "resolution_source": md.get("resolution_source"),
                "input_tokens": md.get("input_tokens"),
                "output_tokens": md.get("output_tokens"),
            }
        out.append(item)
    return {"session_id": session_id, "messages": out}
