"""Normalize PulseAudio/PipeWire devices using stable server-provided names."""

AUDIO_ACTIONS = frozenset({"volume", "mute", "audio_output", "audio_input", "audio_input_volume",
                           "audio_input_mute", "audio_profile"})


def _bluetooth(entry):
    properties = entry.get("properties", {})
    return (properties.get("device.api") == "bluez5" or properties.get("device.bus") == "bluetooth"
            or entry.get("name", "").startswith(("bluez_", "bluez.")))


def _volume(entry):
    values = [channel["value"] / 65536 for channel in entry.get("volume", {}).values()
              if isinstance(channel, dict) and isinstance(channel.get("value"), (int, float))]
    return max(0, min(1, sum(values) / len(values))) if values else None


def audio_state(sinks, sources, cards, default_sink, default_source):
    card_map = {}
    bluetooth_cards = []
    for card in cards:
        name = card.get("name")
        if not name:
            continue
        card_map[name] = card
        if card.get("index") is not None:
            card_map[card["index"]] = card
        if not _bluetooth(card):
            continue
        active = card.get("active_profile", "")
        if isinstance(active, dict):
            active = active.get("name", "")
        profiles = card.get("profiles", {})
        if isinstance(profiles, list):
            profiles = {profile["name"]: profile for profile in profiles if profile.get("name")}
        choices = []
        for identifier, profile in profiles.items():
            if identifier == "off" or not (profile.get("sinks", 0) or profile.get("sources", 0)):
                continue
            choices.append({"id": identifier, "name": profile.get("description", identifier),
                            "active": identifier == active, "microphone": bool(profile.get("sources", 0)),
                            "available": profile.get("available") not in (False, "no", 0)})
        bluetooth_cards.append({"id": name, "name": card.get("properties", {}).get("device.description", name),
                                "profiles": choices})

    def endpoints(entries, default, inputs=False):
        result = []
        for entry in entries:
            name = entry.get("name")
            if not name:
                continue
            if inputs and (name.endswith(".monitor")
                           or entry.get("monitor_of_sink") not in (None, "n/a", 4294967295, "4294967295")
                           or entry.get("properties", {}).get("device.class") == "monitor"):
                continue
            properties = entry.get("properties", {})
            card = card_map.get(entry.get("card")) or card_map.get(properties.get("device.name"), {})
            result.append({"id": name, "name": entry.get("description", name), "active": name == default,
                           "bluetooth": _bluetooth(entry) or _bluetooth(card), "cardId": card.get("name", ""),
                           "volume": _volume(entry), "muted": bool(entry.get("mute", False))})
        return result

    outputs, inputs = endpoints(sinks, default_sink), endpoints(sources, default_source, inputs=True)
    active_output = next((output for output in outputs if output["active"]), {})
    return {"available": True, "outputs": outputs, "inputs": inputs, "cards": bluetooth_cards,
            "volume": active_output.get("volume") or 0, "muted": active_output.get("muted", False)}
