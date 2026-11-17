"""
[INPUT]: 无运行时依赖；构建器通过 AST 读取版本。
[OUTPUT]: 提供桌面、独立应用和 setuptools 共用的 __version__。
[POS]: uDeck 的唯一版本源；Debian changelog 和发布标签与其一致。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

__version__ = "1.0.0"
