FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies against the locked versions first (better layer caching).
COPY pyproject.toml uv.lock ./
COPY carrion ./carrion
RUN uv sync --frozen --no-dev

# Mount a host directory of resumes at /data (read-write: the log is written here).
# Default command batch-processes /data; override to run the phone lookup, e.g.:
#   docker run --env-file .env <img> carrion 4045551234 "Atlanta, GA"
# --no-sync: deps are already installed above; don't re-sync (or pull dev deps)
# at runtime, which would require network on every run.
ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["carrion-vet", "/data"]
