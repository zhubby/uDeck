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
        settings: "gear-fill.svg"
    })
    source: Qt.resolvedUrl("../assets/home-icons/" + (files[kind] || files.settings))
    sourceSize.width: Math.ceil(width * 2)
    sourceSize.height: Math.ceil(height * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
}
