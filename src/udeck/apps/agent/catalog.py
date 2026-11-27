"""[INPUT]: 依赖 ACP Registry 和 npm 的稳定版元数据。
[OUTPUT]: 提供四种固定分发、启动与登录入口。
[POS]: 安装器和会话控制器共用的来源约束。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlparse

REGISTRY = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"
NPM = "https://registry.npmjs.org"
NODE_VERSION = "24.22.3"
NODE_ARCHIVE = f"node-v{NODE_VERSION}-linux-arm64.tar.xz"
NODE_SHA256 = "6e51a2ada00f0011cc266f65d98922b403d7ad88f809ca2aa615a5fe1ce6e86c"
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


@dataclass(frozen=True)
class Agent:
    name: str
    registry: str
    binary: str
    login: tuple[str, ...]
    npm: tuple[str, ...] = ()
    repository: str = ""
    args: tuple[str, ...] = ()


AGENTS = {
    "codex": Agent("Codex", "codex-acp", "codex-acp", ("codex", "login"),
                   ("@agentclientprotocol/codex-acp",)),
    "claude": Agent("Claude Code", "claude-acp", "claude-agent-acp", ("claude", "auth", "login"),
                    repository="agentclientprotocol/claude-agent-acp"),
    "opencode": Agent("OpenCode", "opencode", "opencode", ("opencode", "acp", "--login"),
                      repository="anomalyco/opencode", args=("acp",)),
    "pi": Agent("Pi Agent", "pi-acp", "pi-acp", ("pi-acp", "--terminal-login"),
                ("pi-acp", "@earendil-works/pi-coding-agent")),
}


def version(value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value) or len(value) > 25:
        raise ValueError("Invalid stable version")
    return tuple(map(int, value.split(".")))


def open_url(url, hosts):
    response = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "uDeck-Agent"}), timeout=20)
    final = urlparse(response.geturl())
    if final.scheme != "https" or final.hostname not in hosts:
        response.close()
        raise ValueError("Unrecognized download host")
    return response


def _json(url):
    with open_url(url, {"cdn.agentclientprotocol.com", "registry.npmjs.org"}) as response:
        return json.loads(response.read(8 * 1024 * 1024))


def available(identifier, registry=None):
    agent = AGENTS[identifier]
    if registry is None:
        registry = _json(REGISTRY)
    entry = next((item for item in registry["agents"] if item["id"] == agent.registry), None)
    if not entry:
        raise ValueError("Agent distribution unavailable")
    release = entry["version"]
    version(release)
    if agent.npm:
        if entry["distribution"]["npx"]["package"] != f"{agent.npm[0]}@{release}":
            raise ValueError("Agent npm package changed")
        packages = {agent.npm[0]: release}
        for name in agent.npm[1:]:
            encoded = quote(name, safe="@")
            companion = _json(f"{NPM}/{encoded}/latest")
            if companion["name"] != name:
                raise ValueError("Invalid companion package")
            version(companion["version"])
            packages[name] = companion["version"]
        return {"version": release, "packages": packages}

    binary = entry["distribution"]["binary"]["linux-aarch64"]
    url = binary["archive"]
    prefix = f"https://github.com/{agent.repository}/releases/download/v{release}/"
    if (not url.startswith(prefix) or not re.fullmatch(r"[a-zA-Z0-9._-]+\.tar\.gz",
                                                       url.removeprefix(prefix))
            or not re.fullmatch(r"[a-f0-9]{64}", binary["sha256"])
            or binary["cmd"] != f"./{agent.binary}"
            or tuple(binary.get("args", ())) != agent.args):
        raise ValueError("Unexpected Agent release")
    return {"version": release, "url": url, "sha256": binary["sha256"]}
