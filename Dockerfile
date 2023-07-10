FROM python:3.11.4-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends gcc

ENV PYTHONUNBUFFERED=1 \
  PYTHONUSERBASE=/app/build

COPY requirements.txt /app/
RUN pip install --user --no-cache-dir --prefer-binary -r /app/requirements.txt

FROM python:3.11.4-slim

# required for opencv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

ARG USER_ID=1001
ARG GROUP_ID=1001
USER ${USER_ID}:${GROUP_ID}

WORKDIR /app/

ENV PYTHONUNBUFFERED=1 \
  PYTHONUSERBASE=/app/build \
  MODEL_PATH=/app/yolov8x-seg.pt

COPY --chown=${USER_ID}:${GROUP_ID} yolov8x-seg.pt /app/
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} /app/build /app/build
COPY --chown=${USER_ID}:${GROUP_ID} main.py /app/

CMD ["/app/build/bin/uvicorn", "--host", "0.0.0.0", "main:app"]
