"""[INPUT]: 依赖每个 Agent 的本地连接配置与原子 JSON 写入。
[OUTPUT]: 读写连接配置，并生成 ACP 进程使用的供应商参数。
[POS]: 模型、API 地址和凭据从设置进入启动环境的边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
import json
from urllib.parse import urlsplit

from udeck.apps.common.state import atomic_json
from udeck.i18n import Msg, tr

from .catalog import AGENTS

PROVIDER = "udeck-custom"
KEY_ENV = "UDECK_AGENT_PROVIDER_KEY"
FIELDS = ("url", "model", "key")


def _profile_path(root, identifier):
    if identifier not in AGENTS:
        raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
    return root / f"{identifier}-connection.json"


def load_profile(root, identifier):
    try:
        value = json.loads(_profile_path(root, identifier).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return _validate(identifier, value)


def _validate(identifier, value):
    if not isinstance(value, dict):
        raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
    profile = {}
    for field, limit in zip(FIELDS, (2048, 256, 4096), strict=True):
        raw = value.get(field, "")
        if not isinstance(raw, str) or len(raw) > limit or (raw and not raw.isprintable()):
            raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
        profile[field] = raw.strip()
    try:
        address = urlsplit(profile["url"])
        port = address.port
        valid = (address.scheme in ("http", "https") and address.hostname and address.username is None
                 and port != 0
                 and not address.query and not address.fragment
                 and not any(c.isspace() or c in "\\{}?#" for c in profile["url"]))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(tr(Msg.AGENT_API_ADDRESS_INVALID))
    if any(c.isspace() or c in "{}" for c in profile["model"]) or not profile["model"] or not profile["key"]:
        raise ValueError(tr(Msg.AGENT_CONNECTION_REQUIRED_FIELDS))
    if identifier == "claude":
        auth = value.get("auth", "key")
        if auth not in ("key", "bearer"):
            raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
        profile["auth"] = auth
    return profile


def save_profile(root, identifier, profile):
    path = _profile_path(root, identifier)
    if profile:
        atomic_json(path, _validate(identifier, profile))
    else:
        path.unlink(missing_ok=True)


def connection_environment(root, identifier):
    profile = load_profile(root, identifier)
    if not profile:
        return {}
    url, model, key = (profile[field] for field in FIELDS)
    if identifier == "claude":
        bearer = profile["auth"] == "bearer"
        return {"ANTHROPIC_BASE_URL": url, "ANTHROPIC_MODEL": model,
                "ANTHROPIC_AUTH_TOKEN": key if bearer else "", "ANTHROPIC_API_KEY": "" if bearer else key,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_HAIKU_MODEL": model}
    if identifier == "codex":
        config = {"model": model, "model_provider": PROVIDER, "model_providers": {PROVIDER: {
            "name": "uDeck", "base_url": url, "env_key": KEY_ENV, "wire_api": "responses",
        }}}
        return {KEY_ENV: key, "MODEL_PROVIDER": PROVIDER, "CODEX_CONFIG": json.dumps(config)}
    if identifier == "opencode":
        config = {"model": f"{PROVIDER}/{model}", "providers": {PROVIDER: {
            "name": "uDeck", "package": "aisdk:@ai-sdk/openai-compatible", "env": [KEY_ENV],
            "settings": {"baseURL": url}, "models": {model: {"name": model}},
        }}}
        return {KEY_ENV: key, "OPENCODE_CONFIG_CONTENT": json.dumps(config)}
    identity = hashlib.sha256(json.dumps([url, model]).encode()).hexdigest()
    directory = root / "pi-connection" / identity
    atomic_json(directory / "models.json", {"providers": {PROVIDER: {
        "baseUrl": url, "api": "openai-completions", "apiKey": "$" + KEY_ENV,
        "models": [{"id": model, "name": model}],
    }}})
    atomic_json(directory / "settings.json", {"defaultProvider": PROVIDER, "defaultModel": model,
                                               "sessionDir": str(root.resolve() / "pi-connection" / "sessions")})
    return {KEY_ENV: key, "PI_CODING_AGENT_DIR": str(directory)}
