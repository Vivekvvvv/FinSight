# FinSight Backend — Production Dockerfile
# Python 3.11-slim + all ML deps (bge-m3, FlagEmbedding, torch)
ARG PYTHON_IMAGE=python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93
FROM ${PYTHON_IMAGE} AS builder

# Build-only dependencies stay out of the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies first (layer cache)
COPY requirements.txt /tmp/requirements.txt

# Pre-install CPU-only torch to avoid downloading CUDA packages (~3 GB saved on CPU-only servers)
# BGE_M3_DEVICE=cpu so we never need CUDA at runtime
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system finsight \
    && useradd --system --gid finsight --home-dir /app --shell /usr/sbin/nologin finsight

COPY --from=builder /opt/venv /opt/venv

# Runtime never installs packages; remove installers and unused base packaging tools.
RUN /usr/local/bin/python -m pip uninstall --yes setuptools \
    && /opt/venv/bin/python -m pip uninstall --yes pip \
    && /usr/local/bin/python -m pip uninstall --yes pip

WORKDIR /app
COPY . .

# Create persistent data directories
RUN mkdir -p data/langgraph data/memory backend/data logs \
    && chown -R finsight:finsight /app/data /app/backend/data /app/logs

# Model cache stays in a named volume (mounted at runtime)
RUN mkdir -p /app/.cache/huggingface /app/.cache/torch \
    && chown -R finsight:finsight /app/.cache

USER finsight

# Expose backend port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["python", "-m", "uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-keep-alive", "300"]
