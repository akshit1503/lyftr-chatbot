# ---- build stage ----
FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- runtime stage ----
FROM python:3.12-slim
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 DATABASE_URL=sqlite:////data/app.db
RUN useradd -m app && mkdir -p /data && chown app:app /data
COPY --from=builder /venv /venv
WORKDIR /srv
COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
