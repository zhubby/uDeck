"""[INPUT]: 依赖 ACP v1 会话元数据和共享语言目录。
[OUTPUT]: 将会话元数据、结束原因和动作转换为会话组件。
[POS]: Conversation 与会话组件之间的数据契约。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json

from udeck.i18n import Msg, tr

from .content import string

METADATA_EVENTS = {
    "available_commands_update": "commands",
    "current_mode_update": "mode",
    "config_option_update": "config",
    "session_info_update": "session_info",
    "usage_update": "usage",
}


def records(value):
    return [item for item in value[:64] if isinstance(item, dict)] if isinstance(value, list) else []


def action(label, operation, arguments, *, detail="", selected=False):
    return {
        "type": "action", "text": label, "action": operation, "arguments": arguments,
        "description": detail, "status": "selected" if selected else "",
    }


def text_block(text, name=""):
    return {"type": "text", "text": text, "name": name}


def display_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)[:16000]


def metadata_row(kind, data):
    row = {"text": "", "detail": "", "status": "", "blocks": []}
    if kind == "commands":
        for item in records(data.get("availableCommands")):
            if name := string(item.get("name"), 120):
                schema = item.get("input")
                hint = string(schema.get("hint"), 240) if isinstance(schema, dict) else ""
                row["blocks"].append(action("/" + name, "command", {"name": name, "hint": hint},
                                            detail=string(item.get("description"), 1000)))
    elif kind == "mode":
        current = string(data.get("currentModeId"), 240)
        row["text"] = current
        for mode in records(data.get("availableModes")):
            if identifier := string(mode.get("id"), 240):
                name = string(mode.get("name"), 240) or identifier
                selected = identifier == current
                if selected:
                    row["text"] = name
                row["blocks"].append(action(name, "mode", {"modeId": identifier}, selected=selected,
                                            detail=string(mode.get("description"), 1000)))
    elif kind == "config":
        for item in records(data.get("configOptions")):
            if isinstance(item.get("id"), str) and item["id"]:
                row["blocks"].extend(config_blocks(item))
    elif kind == "session_info":
        row["text"] = string(data.get("title"), 1000)
        row["detail"] = string(data.get("updatedAt"), 100)
    elif kind == "usage":
        used, size = data.get("used"), data.get("size")
        if type(used) is int and type(size) is int:
            row["text"] = tr(Msg.AGENT_CONTEXT_USAGE, used=used, size=size)
            row["blocks"] = [{"type": "usage", "used": used, "size": size}]
        cost = data.get("cost")
        if isinstance(cost, dict) and type(cost.get("amount")) in (int, float):
            row["detail"] = f'{cost["amount"]:g} {string(cost.get("currency"), 20)}'.strip()
    return row


def config_blocks(item):
    key = string(item["id"], 240)
    name = string(item.get("name"), 240) or key
    description = string(item.get("description"), 1000)
    current = item.get("currentValue")
    if item.get("type") == "boolean" and type(current) is bool:
        return [action(name, "config", {"configId": key, "value": not current},
                       detail=description, selected=current)]
    if item.get("type") != "select":
        return [text_block(description, name)]
    options = []
    for option in records(item.get("options")):
        if isinstance(option.get("options"), list):
            group = string(option.get("name"), 240)
            options.extend((group, value) for value in records(option["options"]))
        else:
            options.append(("", option))
    result = [text_block(description, name)]
    for group, option in options[:64]:
        value = string(option.get("value"), 240)
        if value:
            label = string(option.get("name"), 240) or value
            result.append(action(" · ".join(filter(None, (group, label))), "config",
                                 {"configId": key, "value": value}, selected=value == current,
                                 detail=string(option.get("description"), 1000)))
    return result


def result_row(result, error, *, stopping=False):
    reason = result.get("stopReason") if isinstance(result, dict) else None
    if stopping or reason == "cancelled":
        reason, label = "cancelled", Msg.AGENT_STOPPED
    elif error:
        reason, label = "failed", Msg.AGENT_PROMPT_ERROR
    else:
        label = {
            "end_turn": Msg.AGENT_END_TURN,
            "max_tokens": Msg.AGENT_MAX_TOKENS,
            "max_turn_requests": Msg.AGENT_MAX_REQUESTS,
            "refusal": Msg.AGENT_REFUSAL,
        }.get(reason if isinstance(reason, str) else "", Msg.AGENT_PROMPT_ERROR)
    return {"kind": "result", "text": tr(label), "status": string(reason, 80) or "failed",
            "detail": string(error.get("message"), 1000) if isinstance(error, dict) else ""}


def child_result_blocks(state):
    if not isinstance(state, dict) or not state.get("stopReason"):
        return []
    error = state.get("error") or ({"message": ""} if state["stopReason"] == "error" else None)
    report = result_row(state, error)
    return [text_block(report["detail"], report["text"])] if report["detail"] else [text_block(report["text"])]
