"""
[INPUT]: 依赖构建器写入的包内源码身份和唯一版本源。
[OUTPUT]: 提供不执行 Git 的构建身份快照。
[POS]: 桌面与应用诊断共用；源码运行明确标记未记录身份。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from . import __version__


def snapshot():
    try:
        from ._build_identity import BUILD_IDENTITY
    except ModuleNotFoundError as error:
        if error.name != __package__ + '._build_identity':
            raise
        return {'schema': 1, 'recorded': False, 'version': __version__, 'buildId': None,
                'sourceRevision': None, 'sourceDirty': None, 'sourceContentSha256': None}
    return dict(BUILD_IDENTITY)
