# uDeck 品牌标识

正式标识是圆形鸭子徽章，使用护目镜、鸭嘴和颈部轮廓。
产品不使用旧设计迭代图作为界面入口。

- [正式 SVG](../../../src/udeck/assets/branding/udeck.svg)：独立展示的灰白原色。
- [安装图标](../../../packaging/udeck.svg)：桌面安装入口。
- [BrandLogo.qml](../../../src/udeck/qml/BrandLogo.qml)：运行时主题配色。

`BrandLogo.qml` 保持正式 SVG 几何，映射两种颜色角色。
Classic 使用暖色强调与当前表面背景。
Dark 使用正文浅色与当前表面背景。
主题切换立即更新颜色，不重建应用窗口或会话。
壳标题、启动等待、原生应用和 Terminal 复用这个组件。

修改几何时同步正式 SVG、安装图标和组件中的矢量模板。
wheel 保留运行资源，Debian 包保留可缩放安装图标。
验证几何一致性、双主题显示和包内文件；
不以旧版设计截图代替当前渲染检查。

[PROTOCOL]: Update this header on change, then check AGENTS.md
