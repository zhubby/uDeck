ARG BASE_IMAGE=debian:13-slim
FROM ${BASE_IMAGE}
COPY debian /tmp/udeck/debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git ca-certificates \
    && apt-get build-dep -y --no-install-recommends /tmp/udeck \
    && rm -rf /var/lib/apt/lists/* /tmp/udeck
WORKDIR /workspace
