// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../../qml" as Shared

Window {
    id: window
    function tr(source) { return controller.translate(source, state.language) }
    width: 1280
    height: 720
    minimumWidth: 640
    minimumHeight: 360
    visible: true
    visibility: windowed ? Window.Windowed : Window.FullScreen
    color: window.colors.background
    title: (state.tabs.find(function(tab) { return tab.id === state.current }) || {}).title || "uDeck Terminal"
    property var state: JSON.parse(controller.snapshotJson)
    property var optionModel: []
    property string optionsStamp: ""
    property alias colors: themeColors
    Shared.ThemePalette { id: themeColors; theme: window.state.theme; profile: "terminal" }
    property alias fontFamily: interfaceFonts.family
    Shared.InterfaceFonts { id: interfaceFonts; language: window.state.language }
    property bool allowClose: false
    property color ink: window.colors.text
    property color muted: window.colors.muted
    property color accent: window.colors.accent
    onClosing: function(event) {
        event.accepted = allowClose
        if (!allowClose) controller.requestCloseWindow()
    }
    function focusInput() {
        if (state.mode === "input") {
            for (let i = 0; i < panes.count; ++i) {
                const pane = panes.itemAt(i)
                if (pane && pane.identifier === state.current && pane.item) pane.item.focusInput()
            }
        } else if (state.mode === "history") historyKeys.forceActiveFocus()
        else if (state.mode === "search") searchBox.forceActiveFocus()
        else modalKeys.forceActiveFocus()
    }
    function syncOptions() {
        const stamp = JSON.stringify(state.options)
        if (stamp !== optionsStamp) { optionsStamp=stamp; optionModel=state.options }
    }
    Component.onCompleted: syncOptions()
    Connections {
        target: controller
        function onChanged() {
            window.state = JSON.parse(controller.snapshotJson)
            window.syncOptions()
            Qt.callLater(window.focusInput)
        }
        function onClosed() { window.allowClose = true; window.close() }
    }
    onActiveChanged: if (active) Qt.callLater(focusInput)
    Shortcut { sequence: "Ctrl+Shift+T"; onActivated: controller.command("new-tab") }
    Shortcut { sequence: "Ctrl+Shift+W"; onActivated: controller.command("close-tab") }
    Shortcut { sequence: "Ctrl+Shift+C"; onActivated: controller.command("copy") }
    Shortcut { sequence: "Ctrl+Shift+V"; onActivated: controller.command("paste") }
    Shortcut { sequence: "Ctrl+Shift+F"; onActivated: controller.command("search") }
    Shortcut { sequence: "Ctrl+Shift+M"; onActivated: controller.command("menu") }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            color: window.colors.header
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 12
                spacing: 12
                Text { font.family: window.fontFamily; text: ">_"; color: window.accent; font.pixelSize: 22; font.bold: true }
                ListView {
                    id: tabbar
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    orientation: ListView.Horizontal
                    spacing: 4
                    clip: true
                    model: controller.sessions
                    currentIndex: window.state.tabs.findIndex(function(tab) { return tab.id === window.state.current })
                    onCurrentIndexChanged: Qt.callLater(function() { tabbar.positionViewAtIndex(tabbar.currentIndex, ListView.Contain) })
                    delegate: Rectangle {
                        required property string identifier
                        required property string label
                        required property int index
                        width: Math.max(100, Math.min(240, titleText.implicitWidth + 42))
                        height: tabbar.height
                        color: identifier === window.state.current ? window.colors.selectedTab : "transparent"
                        Text { font.family: window.fontFamily;
                            id: titleText
                            anchors.centerIn: parent
                            width: Math.min(198, implicitWidth)
                            text: (index + 1) + "  " + label
                            elide: Text.ElideRight
                            color: identifier === window.state.current ? window.ink : window.muted
                            font.pixelSize: 16
                        }
                        Rectangle { height: 2; anchors.bottom: parent.bottom; width: parent.width; color: window.accent; visible: identifier === window.state.current }
                        MouseArea { anchors.fill: parent; onClicked: controller.selectTab(parent.identifier) }
                    }
                }
                Shared.InputPrompt { keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"]; label: window.tr("会话"); fontFamily: window.fontFamily; textColor: window.muted; iconSize: 24; fontSize: 14 }
            }
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            Repeater {
                id: panes
                model: controller.sessions
                delegate: Loader {
                    required property string identifier
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: identifier === window.state.current
                    source: useMock ? "MockTerminal.qml" : "NativeTerminal.qml"
                    onLoaded: {
                        item.identifier = identifier
                        item.hostController = controller
                        item.fontSize = Qt.binding(function() { return window.state.fontSize })
                        item.paletteName = Qt.binding(function() { return window.state.colorScheme })
                        item.language = Qt.binding(function() { return window.state.language })
                        item.start(JSON.parse(controller.sessionSpec(identifier)))
                        Qt.callLater(window.focusInput)
                    }
                    onStatusChanged: if (status === Loader.Error) controller.componentFailed()
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(44, statusHints.implicitHeight + 12)
            color: window.colors.header
            Shared.InputHints {
                id: statusHints
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                width: parent.width - 104
                fontFamily: window.fontFamily; textColor: window.muted; fontSize: 15; iconSize: 28
                hints: window.state.mode === "history" ? [
                    {keys: ["keyboard_arrows"], label: window.tr(window.state.anchored ? "Extend selection" : "Select")},
                    {keys: ["gamecube_button_color_a"], label: window.tr(window.state.anchored ? "Copy" : "Set start")},
                    {keys: ["gamecube_button_color_b"], label: window.tr(window.state.anchored ? "取消" : "返回")}
                ] : [
                    {keys: ["gamecube_button_color_a"], label: window.tr("Send Enter")},
                    {keys: ["gamecube_button_color_b"], label: window.tr("Send Escape")},
                    {keys: ["gamecube_button_x"], label: window.tr("Actions")},
                    {keys: ["gamecube_button_y"], label: window.tr("Settings")},
                    {keys: ["keyboard_ctrl", "+", "keyboard_shift", "+", "keyboard_t"], label: window.tr("New tab")}
                ]
            }
            Text { font.family: window.fontFamily; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; text: window.state.fontSize + " px"; color: window.muted; font.pixelSize: 14 }
        }
    }
    FocusScope {
        id: modalKeys
        anchors.fill: parent
        visible: window.state.mode !== "input" && window.state.mode !== "history"
        Keys.onPressed: function(event) {
            const actions = {}
            actions[Qt.Key_Up] = "up"; actions[Qt.Key_Down] = "down"
            actions[Qt.Key_Left] = "left"; actions[Qt.Key_Right] = "right"
            actions[Qt.Key_Return] = "accept"; actions[Qt.Key_Enter] = "accept"
            actions[Qt.Key_Escape] = "back"
            if (actions[event.key]) { controller.dispatch(actions[event.key]); event.accepted = true }
            else event.accepted = window.state.mode !== "search"
        }
        Rectangle { anchors.fill: parent; color: window.colors.scrim }
        Rectangle {
            width: Math.min(parent.width - 48, 680)
            height: Math.min(parent.height - 60, contents.implicitHeight + 48)
            anchors.centerIn: parent
            radius: 14
            color: window.colors.dialog
            border.color: window.colors.dialogBorder
            ColumnLayout {
                id: contents
                anchors.fill: parent
                anchors.margins: 24
                spacing: 14
                Text { font.family: window.fontFamily; text: ({menu:window.tr("终端操作"),settings:window.tr("终端设置"),close:window.tr("结束会话？"),paste:window.tr("确认粘贴"),search:window.tr("搜索文字"),error:window.tr("无法完成操作")})[window.state.mode] || ""; color: window.ink; font.pixelSize: 24; font.bold: true }
                Text {
                    objectName: "terminalThemeHint"
                    visible: window.state.mode === "settings"
                    Layout.fillWidth: true
                    font.family: window.fontFamily
                    font.pixelSize: 16
                    color: window.muted
                    wrapMode: Text.Wrap
                    text: window.state.themeLabel
                }
                Text { font.family: window.fontFamily; visible: window.state.mode === "close" || window.state.mode === "error" || window.state.mode === "paste"; text: window.state.message; color: window.muted; font.pixelSize: 17; wrapMode: Text.Wrap; Layout.fillWidth: true }
                ScrollView { palette: window.colors.controls;
                    visible: window.state.mode === "paste"
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(160, preview.implicitHeight + 16)
                    TextArea { font.family: window.fontFamily; palette: window.colors.controls; id: preview; text: window.state.pastePreview; readOnly: true; wrapMode: TextEdit.Wrap; font.pixelSize: 16; color: window.ink; background: Rectangle { color: window.colors.background } }
                }
                TextField { font.family: window.fontFamily; palette: window.colors.controls;
                    id: searchBox
                    visible: window.state.mode === "search"
                    Layout.fillWidth: true
                    text: window.state.query
                    placeholderText: window.tr("普通文字匹配 · Enter 下一处 · ↑ 上一处")
                    font.pixelSize: 20
                    onTextEdited: controller.setQuery(text)
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Escape) { controller.dispatch("back"); event.accepted = true }
                        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { controller.search(true); event.accepted = true }
                        else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) { controller.search(event.key === Qt.Key_Down); event.accepted = true }
                    }
                }
                ListView {
                    id: optionsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: contentHeight
                    Layout.minimumHeight: 0
                    visible: window.state.options.length > 0
                    clip: true
                    interactive: false
                    spacing: 4
                    model: window.optionModel
                    currentIndex: window.state.index
                    onCurrentIndexChanged: Qt.callLater(function() { optionsList.positionViewAtIndex(optionsList.currentIndex, ListView.Contain) })
                    delegate: Rectangle {
                        required property int index
                        required property string modelData
                        width: optionsList.width
                        height: 42
                        radius: 6
                        color: index === window.state.index ? window.colors.menuSelected : "transparent"
                        border.color: index === window.state.index ? window.accent : "transparent"
                        Text { font.family: window.fontFamily; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 12; text: parent.modelData; color: window.ink; font.pixelSize: 18 }
                        MouseArea { anchors.fill: parent; onClicked: { while (window.state.index < index) controller.dispatch("down"); while (window.state.index > index) controller.dispatch("up"); controller.dispatch("accept") } }
                    }
                }
                Shared.InputHints {
                    Layout.fillWidth: true
                    fontFamily: window.fontFamily; textColor: window.muted; fontSize: 14; iconSize: 28
                    hints: [{keys: ["keyboard_arrows"], label: window.tr("Select")},
                            {keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: window.tr("确认")},
                            {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: window.tr("返回")}]
                }
            }
        }
    }
    Item {
        id: historyKeys
        visible: window.state.mode === "history"
        focus: visible
        Keys.onPressed: function(event) {
            const mapping = {}
            mapping[Qt.Key_Up] = "up"; mapping[Qt.Key_Down] = "down"; mapping[Qt.Key_Left] = "left"; mapping[Qt.Key_Right] = "right"
            mapping[Qt.Key_PageUp] = "page-up"; mapping[Qt.Key_PageDown] = "page-down"
            mapping[Qt.Key_Return] = "accept"; mapping[Qt.Key_Enter] = "accept"; mapping[Qt.Key_Escape] = "back"
            if (mapping[event.key]) controller.dispatch(mapping[event.key])
            event.accepted = true
        }
        onVisibleChanged: if (visible) forceActiveFocus()
    }
}
