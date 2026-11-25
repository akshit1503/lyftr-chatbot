import { useEffect, useRef, useState } from "react";

const API_URL = (import.meta.env.VITE_API_URL !== undefined ? import.meta.env.VITE_API_URL : "http://localhost:8000").replace(/\/$/, "");

const newSessionId = () =>
  "s-" + (crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Math.random().toString(16).slice(2, 10));

const SIMULATIONS = [
  { label: "No simulated failure", value: "" },
  { label: "key_1 returns 429", value: "key_1=429" },
  { label: "key_1 returns 500", value: "key_1=500" },
  { label: "key_1 and key_2 fail", value: "key_1=429,key_2=500" },
  { label: "Every key returns 429", value: "*=429" },
];

function readableError(status, body) {
  if (status === 503) return "Every API key is unavailable right now. Try again in a moment.";
  if (status === 422) return "Messages must be between 1 and 4000 characters.";
  if (typeof body?.detail === "string") return body.detail;
  return "Something went wrong. Try sending your message again.";
}

function Meta({ m }) {
  const cached = m.resolution_source === "LLM_CACHE";
  return (
    <dl className="meta">
      <div>
        <dt>Source</dt>
        <dd>
          <span data-testid="meta-source" className={"pill " + (cached ? "pill-cache" : "pill-live")}>
            {m.resolution_source}
          </span>
        </dd>
      </div>
      <div>
        <dt>Model</dt>
        <dd data-testid="meta-model">{m.model}</dd>
      </div>
      <div>
        <dt>Latency</dt>
        <dd data-testid="meta-latency">{m.latency_ms} ms</dd>
      </div>
      <div>
        <dt>Input tokens</dt>
        <dd data-testid="meta-input-tokens">{m.input_tokens}</dd>
      </div>
      <div>
        <dt>Output tokens</dt>
        <dd data-testid="meta-output-tokens">{m.output_tokens}</dd>
      </div>
      <div>
        <dt>Key</dt>
        <dd>{m.key_id ?? "none (cache)"}</dd>
      </div>
      <div>
        <dt>Failed keys before this</dt>
        <dd>{m.fallback_attempts}</dd>
      </div>
    </dl>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [items, setItems] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setItems((prev) => [...prev, { kind: "user", text }]);
    setBusy(true);
    try {
      const headers = { "Content-Type": "application/json" };
      if (simulate) headers["X-Simulate-Failure"] = simulate;
      const body = { session_id: sessionId, message: text };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();
      const res = await fetch(`${API_URL}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
      let data = null;
      try {
        data = await res.json();
      } catch {
        /* non-JSON body */
      }
      if (!res.ok) {
        setItems((prev) => [...prev, { kind: "error", text: readableError(res.status, data) }]);
      } else {
        setItems((prev) => [...prev, { kind: "assistant", text: data.reply, meta: data.metadata }]);
      }
    } catch {
      setItems((prev) => [
        ...prev,
        { kind: "error", text: "Can't reach the server. Check your connection and try again." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function resetChat() {
    setSessionId(newSessionId());
    setItems([]);
  }

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Failover Chat</h1>
          <p className="sub">Session {sessionId}</p>
        </div>
        <div className="actions">
          <button className="ghost" onClick={() => setShowSettings((s) => !s)} aria-expanded={showSettings}>
            Session settings
          </button>
          <button className="ghost" onClick={resetChat}>
            New chat
          </button>
        </div>
      </header>

      {showSettings && (
        <section className="settings">
          <label>
            System prompt
            <textarea
              data-testid="system-prompt-input"
              rows={2}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Optional. Applies to this session."
            />
          </label>
          <label>
            Simulate key failure on the next messages
            <select value={simulate} onChange={(e) => setSimulate(e.target.value)}>
              {SIMULATIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </section>
      )}

      <main className="thread" aria-live="polite">
        {items.length === 0 && (
          <div className="empty">
            <p>Ask anything. Each reply shows where it came from, how long it took and what it cost in tokens.</p>
            <p>Send the same first message in a new chat to see a cache hit.</p>
          </div>
        )}
        {items.map((it, i) => {
          if (it.kind === "user")
            return (
              <div key={i} className="row user">
                <div className="bubble">{it.text}</div>
              </div>
            );
          if (it.kind === "error")
            return (
              <div key={i} className="row">
                <div className="bubble error" role="alert">
                  {it.text}
                </div>
              </div>
            );
          return (
            <div key={i} className="row">
              <div className="bubble assistant" data-testid="assistant-message">
                <div className="reply">{it.text}</div>
                <Meta m={it.meta} />
              </div>
            </div>
          );
        })}
        {busy && (
          <div className="row">
            <div className="bubble typing">Thinking…</div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      <footer className="composer">
        <textarea
          data-testid="chat-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Write a message"
          aria-label="Message"
        />
        <button data-testid="send-button" onClick={send} disabled={busy}>
          Send
        </button>
      </footer>
    </div>
  );
}
