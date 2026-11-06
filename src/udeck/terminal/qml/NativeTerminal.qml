// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QMLTermWidget 2.0

FocusScope {
    id: root
    property string identifier
    property QtObject hostController: null
    property int fontSize: 20
    property string paletteName: "udeck"
    function start(spec) {
        hostController.attachSession(identifier, ptySession)
        ptySession.initialWorkingDirectory = spec.cwd
        ptySession.shellProgram = spec.program
        ptySession.shellProgramArgs = spec.arguments
        ptySession.configureEnvironment(spec.environment)
        Qt.callLater(function() { ptySession.startShellProgram() })
    }
    function focusInput() { term.forceActiveFocus() }
    QMLTermSession {
        id: ptySession
        historySize: 10000
        onFinished: Qt.callLater(function() { if (root.hostController) root.hostController.sessionFinished(root.identifier) })
        onTitleChanged: if (root.hostController) root.hostController.updateTitle(root.identifier, title)
        onError: function(message) { root.hostController.showError(message) }
    }
    QMLTermWidget {
        id: term
        objectName: "nativeTerminal"
        anchors.fill: parent
        session: ptySession
        font.family: "monospace"
        font.pixelSize: root.fontSize
        colorScheme: root.paletteName
        blinkingCursor: false
        useFBORendering: false
        // All pointer operations stay inside the terminal. No mouse reports
        // reach a shell/TUI when running in the button-first uDeck interface.
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(wheel) { wheel.accepted = true } }
    }
    Connections {
        target: root.hostController
        function onOperate(id, action, text) {
            if (id !== root.identifier) return
            const historyMode = JSON.parse(root.hostController.snapshotJson).mode === "history"
            const directions = {left:[-1,0],right:[1,0],up:[0,-1],down:[0,1],"page-up":[0,-20],"page-down":[0,20]}
            if (directions[action]) {
                if (historyMode) term.moveHistory(directions[action][0], directions[action][1])
                else term.simulateKeyPress(({left:Qt.Key_Left,right:Qt.Key_Right,up:Qt.Key_Up,down:Qt.Key_Down})[action], 0, true, 0, "")
            } else if (action === "return") term.simulateKeyPress(Qt.Key_Return, 0, true, 0, "\r")
            else if (action === "escape") term.simulateKeyPress(Qt.Key_Escape, 0, true, 0, "\x1b")
            else if (action === "close") ptySession.close()
            else if (action === "history") term.beginHistory()
            else if (action === "anchor") term.anchorHistory()
            else if (action === "copy-history") { term.copyClipboard(); term.leaveHistory() }
            else if (action === "copy") term.copyClipboard()
            else if (action === "paste") term.pasteText(text)
            else if (action === "leave-history") term.leaveHistory()
            else if (action === "search-next" || action === "search-previous") term.searchText(text, action === "search-next")
        }
    }
}
