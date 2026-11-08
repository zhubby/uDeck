// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import "../../qml" as Shared

FocusScope {
    id: root
    property string identifier
    property QtObject hostController: null
    property int fontSize: 20
    property string paletteName: "udeck"
    property string language: "en"
    TerminalFonts { id: terminalFonts; language: root.language; hostController: root.hostController; pixelSize: root.fontSize }
    Shared.ThemePalette { id: themeColors; theme: root.paletteName === "udeck-dark" ? "dark" : "classic"; profile: "terminal" }
    function tr(source) { return hostController ? hostController.translate(source, language) : "" }
    function start(spec) {}
    function focusInput() { forceActiveFocus() }
    Rectangle { objectName: "terminalBackground"; anchors.fill: parent; color: themeColors.background }
    Text {
        objectName: "terminalContent"
        anchors.fill: parent
        text: "uDeck Terminal  ·  " + root.tr("界面预览")
            + "\n\nzhubby@uconsole:~ $ uname -m\naarch64\nzhubby@uconsole:~ $ printf '你好，uDeck\\n'\n你好，uDeck\n\n"
            + "\uf07c ~/Projects   \uf120 shell   \ue0b0 Powerline   \udb80\udc01 Material\n\n"
            + root.tr("会话在返回桌面后继续运行。") + "\n\nzhubby@uconsole:~ $ ▏"
        color: themeColors.text
        font: terminalFonts.contentFont
        wrapMode: Text.Wrap
    }
}
