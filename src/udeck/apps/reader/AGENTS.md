# reader/
> L2 | Parent: ../AGENTS.md

__init__.py: 阅读器应用包入口。
controller.py: PDF 图像和文档导航；返回桌面前保存阅读进度。
mobi.py: 限制 MOBI 文件体积与切片大小，拒绝文件替换。
server.py: 隔离 EPUB、MOBI 和 TXT 资源，只读取已选文档。
style.py: 阅读字体、行高、宽度和配色的统一校验。
qml/: PDF 与隔离 WebEngine 阅读表面；拒绝系统协议和原生选择器。
web/: 阅读页面、控制器桥接与带来源记录的 Foliate 资源。

[PROTOCOL]: Update this header on change, then check AGENTS.md
