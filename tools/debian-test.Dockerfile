ARG BASE_IMAGE=debian:13-slim
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 dpkg-dev \
    && curl -fsSL --retry 3 --connect-timeout 20 \
       https://archive.raspberrypi.com/debian/pool/main/r/raspberrypi-archive-keyring/raspberrypi-archive-keyring_2025.1+rpt1_all.deb \
       -o /tmp/raspberrypi-archive-keyring.deb \
    && echo '2e727149d7acb8cc7f604e66d0049161039c8aa1eaf1175e54f9e69d963d60e4  /tmp/raspberrypi-archive-keyring.deb' | sha256sum --check - \
    && dpkg --install /tmp/raspberrypi-archive-keyring.deb \
    && rm /tmp/raspberrypi-archive-keyring.deb \
    && echo 'deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] https://archive.raspberrypi.com/debian trixie main' > /etc/apt/sources.list.d/udeck-test-raspberrypi.list \
    && apt-get update \
    && rm -rf /var/lib/apt/lists/*
# Keep the suite's documentation and notices during installation verification.
RUN rm -f /etc/dpkg/dpkg.cfg.d/docker
WORKDIR /tmp
