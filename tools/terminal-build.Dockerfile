FROM debian:13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential qt6-base-dev qt6-declarative-dev libutempter-dev \
    python3 python3-pyside6.qtwidgets python3-pyside6.qtquick python3-pyside6.qtqml \
    python3-pyside6.qtdbus python3-pyside6.qtquickcontrols2 python3-pyside6.qttest python3-pyside6.qtmultimedia python3-pytest \
    python3-dbus-next python3-evdev python3-gi gir1.2-glib-2.0 \
    qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-layouts \
    qml6-module-qtquick-window qml6-module-qtqml-workerscript qml6-module-qtquick-templates \
    dbus-x11 xvfb xauth xdg-terminal-exec xterm tmux vim-tiny less \
    fonts-noto-cjk locales ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
ENV QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software PYTHONPATH=/workspace/src LANG=C.UTF-8
CMD ["python3", "-m", "pytest", "-q"]
