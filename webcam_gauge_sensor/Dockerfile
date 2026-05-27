ARG BUILD_FROM=debian:bookworm-slim
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        python3 \
        python3-numpy \
        python3-opencv \
        python3-paho-mqtt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY download_image.py prepare_image.py process_image.py run.py /app/

CMD ["python3", "/app/run.py"]
