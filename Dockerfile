# PermaInfer — open-weight inference with verifiable receipts
# Build: docker build -t ghcr.io/YUSMARA/permainfer:0.1.0 .
# The model weights (~491 MB, Apache 2.0, Qwen) are downloaded at build
# time so the image is self-contained on any Nosana node.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PERMAINFER_MODEL=models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    PERMAINFER_LEDGER=data/ledger.jsonl \
    PERMAINFER_STORE_PLAINTEXT=0

WORKDIR /app

# Build tools needed only for the llama-cpp-python wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY pyproject.toml README.md ./
RUN pip install --no-deps -e .

RUN python scripts/download_model.py && \
    sha256sum models/qwen2.5-0.5b-instruct-q4_k_m.gguf | tee models/SHA256SUMS && \
    mkdir -p data

# Drop build tools to keep the runtime image small.
RUN apt-get purge -y build-essential cmake && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["python", "-m", "permainfer.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
