/*
[INPUT]: 依赖首页卡片类别和内置图标。
[OUTPUT]: 提供随尺寸缩放的首页图标。
[POS]: 首页和应用启动反馈共用。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Image {
    id: icon
    required property string kind
    readonly property var files: ({
        terminal: "terminal-fill.svg",
        music: "music-note-beamed.svg",
        video: "play-btn-fill.svg",
        reader: "book-fill.svg",
        emulator: "controller.svg",
        browser: "globe2.svg",
        settings: "gear-fill.svg",
        agent: "agent.svg"
    })
    source: Qt.resolvedUrl("../assets/home-icons/" + (files[kind] || files.settings))
    sourceSize.width: Math.ceil(width * 2)
    sourceSize.height: Math.ceil(height * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
}
