// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

FocusScope {
    id: root
    property string identifier
    property QtObject hostController: null
    property int fontSize: 20
    property string paletteName: "udeck"
    property string language: "en"
    function tr(source) { return hostController ? hostController.translate(source, language) : "" }
    function start(spec) {}
    function focusInput() { forceActiveFocus() }
    Rectangle { anchors.fill: parent; color: paletteName === "udeck" ? "#151719" : "#fdf6e3" }
    Text {
        anchors.fill: parent
        text: "uDeck Terminal  ·  " + root.tr("界面预览")
            + "\n\nzhubby@uconsole:~ $ uname -m\naarch64\nzhubby@uconsole:~ $ printf '你好，uDeck\\n'\n你好，uDeck\n\n"
            + root.tr("会话在返回桌面后继续运行。") + "\n\nzhubby@uconsole:~ $ ▏"
        color: paletteName === "udeck" ? "#f1eee7" : "#29363b"
        font.family: "monospace"
        font.pixelSize: fontSize
        wrapMode: Text.Wrap
    }
}
