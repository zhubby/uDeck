"""Shared interface translations; unmarked user and system content stays literal.

Messages retain their source and arguments until a view is serialized. This lets
open prompts and background status change language without recreating state.
"""

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "zh_CN": "简体中文"}


def language_code(value):
    return value if isinstance(value, str) and value in LANGUAGES else DEFAULT_LANGUAGE


@lru_cache(maxsize=2)
def catalog(language):
    path = Path(__file__).with_name("locales") / (language_code(language) + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


class Message(str):
    """A marked string compatible with existing service state and exceptions."""

    def __new__(cls, source, values=None, parts=None):
        values = values or {}
        original = "".join(str(part) for part in parts) if parts is not None else source.format_map(values)
        instance = super().__new__(cls, original)
        instance.source, instance.values, instance.parts = source, values, parts
        return instance

    def __add__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        return Message("", parts=(self, other))

    def __radd__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        return Message("", parts=(other, self))

    def __getnewargs__(self):
        return self.source, self.values, self.parts

    def translated(self, language):
        if self.parts is not None:
            return "".join(render(part, language) for part in self.parts)
        template = catalog(language).get(self.source, self.source)
        return template.format_map({key: render(value, language) for key, value in self.values.items()})


def tr(source, **values):
    return Message(source, {key: error_text(value) if isinstance(value, BaseException) else value
                            for key, value in values.items()})


def error_text(error):
    """Preserve marked exception text instead of flattening it with str()."""
    if len(error.args) == 1 and isinstance(error.args[0], Message):
        return error.args[0]
    if isinstance(getattr(error, "strerror", None), Message):
        return error.strerror
    return str(error)


def render(value, language=DEFAULT_LANGUAGE):
    if isinstance(value, Message):
        return value.translated(language)
    if isinstance(value, BaseException):
        return render(error_text(value), language)
    if isinstance(value, dict):
        return {key: render(item, language) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [render(item, language) for item in value]
    return value
