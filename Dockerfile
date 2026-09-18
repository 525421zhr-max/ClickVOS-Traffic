ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}

ARG SAM2_COMMIT=2b90b9f5ceec907a1c18123530e92e794ad901a4

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    CLICKVOS_HOST=0.0.0.0 \
    CLICKVOS_PORT=7860 \
    CLICKVOS_CONFIG=/app/configs/default.json \
    CLICKVOS_CHECKPOINT=/models/sam2.1_hiera_tiny.pt

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg git python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv \
    && python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir \
       torch==2.11.0+cu128 torchvision==0.26.0+cu128 \
       --index-url https://download.pytorch.org/whl/cu128

RUN git clone --filter=blob:none https://github.com/facebookresearch/sam2.git /opt/sam2 \
    && git -C /opt/sam2 checkout --detach "${SAM2_COMMIT}" \
    && SAM2_BUILD_CUDA=0 python -m pip install --no-cache-dir --no-build-isolation /opt/sam2

WORKDIR /app
COPY requirements-app.txt pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements-app.txt \
    && python -m pip install --no-cache-dir --no-deps .

COPY configs ./configs
COPY scripts ./scripts
RUN mkdir -p /app/outputs/tasks /models

EXPOSE 7860
VOLUME ["/app/outputs/tasks", "/models"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('CLICKVOS_PORT', '7860') + '/', timeout=3)" || exit 1

CMD ["sh", "-c", "python scripts/verify_deployment.py --config \"$CLICKVOS_CONFIG\" --checkpoint \"$CLICKVOS_CHECKPOINT\" && exec python -m clickvos.web_app"]
