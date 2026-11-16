/*
[INPUT]: 依赖模态快照、主题、控制器和统一动效时长。
[OUTPUT]: 提供弹窗短过渡、关闭画面保留与点击隔离。
[POS]: Main 的模态视图；输入与操作仍由控制器决策。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    objectName: "modalShade"
    required property var viewState
    required property var colors
    required property string fontFamily
    property bool reducedMotion: false
    property var retainedDialog: ({})
    readonly property bool shown: !!viewState.modal.kind
    readonly property bool closing: !shown && visible
    readonly property var dialog: shown ? viewState.modal : retainedDialog
    readonly property var msg: controller.messageKeys
    readonly property color ink: colors.text
    readonly property color muted: colors.muted
    readonly property color accent: colors.accent
    property string lastDialog: ""
    signal restoreFocus()
    MotionTimings { id: motion; reducedMotion: root.reducedMotion }
    function tr(key) { return controller.translate(key, viewState.language) }
    function desktopIconSource(name) {
        const icon = name || "application-x-executable"
        const tint = icon.startsWith("udeck-setting:") ? "/" + colors.artText.toString() : ""
        return "image://desktop/" + encodeURIComponent(icon + tint)
    }
    function scrollPreview(amount) {
        previewContent.contentY = Math.max(0, Math.min(previewContent.contentY + amount,
            previewContent.contentHeight - previewContent.height))
    }
    function finishClose() {
        // 连续按键先于 QML 快照绑定刷新时，也立即结束旧画面。
        if (visible && !JSON.parse(controller.viewSnapshotJson).modal.kind) {
            transition.stop()
            opacity = 0; panelShift.y = 8
            retainedDialog = ({})
        }
    }
    function animateVisibility() {
        transition.stop()
        if (reducedMotion) {
            opacity = shown ? 1 : 0
            panelShift.y = shown ? 0 : 8
            if (!shown) retainedDialog = ({})
        } else {
            fade.to = shown ? 1 : 0; slide.to = shown ? 0 : 8
            fade.duration = shown ? motion.enter : motion.leave
            slide.duration = fade.duration
            transition.start()
        }
    }
    function syncView() {
        if (shown && dialog.kind === "menu")
            menuList.positionViewAtIndex(dialog.index, ListView.Contain)
        const key = viewState.modal.key || ""
        if (key === lastDialog) return
        lastDialog = key
        previewContent.contentY = 0
        if (shown && dialog.kind === "text") {
            editor.text = dialog.text || ""
            controller.editText(editor.text)
            editor.forceActiveFocus()
            editor.selectAll()
        } else {
            editor.focus = false
            restoreFocus()
        }
    }
    onViewStateChanged: if (viewState.modal.kind) retainedDialog = viewState.modal
    onShownChanged: animateVisibility()
    onReducedMotionChanged: if (reducedMotion) animateVisibility()
    Component.onCompleted: animateVisibility()
    visible: shown || opacity > 0
    opacity: 0
    ParallelAnimation {
        id: transition
        NumberAnimation {
            id: fade; target: root; property: "opacity"; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            id: slide; target: panelShift; property: "y"; easing.type: Easing.OutCubic
        }
        onFinished: if (!root.shown) root.retainedDialog = ({})
    }
    anchors.fill: parent
    color: root.colors.scrim

    MouseArea {
        anchors.fill: parent; acceptedButtons: Qt.AllButtons; cursorShape: Qt.BlankCursor
        onWheel: function(wheel) { wheel.accepted = true }
    }

    Rectangle {
        id: panel
        enabled: root.shown
        transform: Translate {
            id: panelShift; y: 8
        }
        objectName: "dialogPanel"
        anchors.centerIn: parent
        width: dialog.kind === "key-test" ? Math.min(1160, parent.width - 48) : Math.min(810, parent.width - 96)
        property real menuChromeHeight: dialog.kind === "menu" ? 96 + dialogTitle.implicitHeight + modalFooter.implicitHeight
            + (dialog.body ? dialogBody.implicitHeight + 20 : 0)
            + (viewState.toast ? modalToast.height + 20 : 0) : 0
        property real menuRowsHeight: Math.max(menuList.contentHeight, Math.max(0, (dialog.options || []).reduce(
            (height, option) => height + (option.singleLine ? 65 : 69), 0) - 5))
        property real previewChromeHeight: 96 + dialogTitle.implicitHeight + modalFooter.implicitHeight
            + (dialog.body ? (dialog.kind === "file-preview" ? previewDetails.height : dialogBody.height) + 20 : 0)
            + (dialog.truncated ? previewNotice.height + 20 : 0)
            + (viewState.toast ? modalToast.height + 20 : 0)
        property real previewHeight: Math.max(80, Math.min(240, parent.height - 64 - previewChromeHeight))
        height: Math.min(parent.height - (dialog.kind === "key-test" ? 32 : 64), dialog.kind === "menu"
            ? menuChromeHeight + menuRowsHeight : modalColumn.height + (dialog.kind === "key-test" ? 40 : 56))
        radius: 16; color: root.colors.dialog; border.width: 1; border.color: root.colors.dialogBorder

        Column {
            id: modalColumn
            objectName: "dialogContent"
            x: dialog.kind === "key-test" ? 20 : 28; y: dialog.kind === "key-test" ? 20 : 26
            width: parent.width - 2 * x; spacing: dialog.kind === "key-test" ? 8 : dialog.kind === "console-details" ? 16 : 20
            Text { textFormat: Text.PlainText; id: dialogTitle; width: parent.width; text: dialog.title || ""; font.family: root.fontFamily; font.pixelSize: dialog.kind === "key-test" ? 28 : 32; font.weight: Font.DemiBold; color: root.ink; wrapMode: Text.Wrap; maximumLineCount: dialog.kind === "console-details" ? 1 : 2; elide: Text.ElideRight }
            Text { textFormat: Text.PlainText; id: dialogBody; visible: !!dialog.body && dialog.kind !== "file-preview"; width: parent.width; text: dialog.body || ""; font.family: root.fontFamily; font.pixelSize: 24; color: root.muted; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight }

            ConsoleDetails {
                visible: dialog.kind === "console-details"; width: parent.width
                details: controller.runtimeConsole.details
                colors: root.colors; fontFamily: root.fontFamily
                reducedMotion: root.reducedMotion
                language: viewState.language; index: dialog.index || 0
            }

            Column {
                id: previewDetails
                objectName: "filePreviewDetails"
                visible: dialog.kind === "file-preview" && !!dialog.body
                width: parent.width; spacing: 2
                Repeater {
                    model: dialog.kind === "file-preview" ? (dialog.body || "").split("\n").slice(0, 4) : []
                    delegate: Text {
                        objectName: "filePreviewMetadata"
                        required property string modelData
                        width: modalColumn.width; textFormat: Text.PlainText; text: modelData
                        font.family: root.fontFamily; font.pixelSize: 21; color: root.muted
                        maximumLineCount: 1; elide: Text.ElideMiddle; clip: true
                    }
                }
            }

            Column {
                visible: !!dialog.metrics
                width: parent.width; spacing: 12
                Repeater {
                    model: dialog.metrics || []
                    delegate: Item {
                        required property var modelData
                        width: modalColumn.width; height: 34
                        Text { objectName: "batteryMetricLabel"; textFormat: Text.PlainText; width: parent.width - 190; anchors.verticalCenter: parent.verticalCenter; text: modelData.label; font.family: root.fontFamily; font.pixelSize: 24; color: root.muted; elide: Text.ElideRight }
                        Text { objectName: "batteryMetricValue"; textFormat: Text.PlainText; width: 178; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData.value; horizontalAlignment: Text.AlignRight; font.family: root.fontFamily; font.pixelSize: 26; font.weight: Font.Medium; color: root.ink; elide: Text.ElideRight }
                    }
                }
            }

            ListView {
                id: menuList
                objectName: "menuList"
                visible: dialog.kind === "menu"
                width: parent.width
                height: visible ? Math.max(0, Math.min(panel.menuRowsHeight, root.height - 64 - panel.menuChromeHeight)) : 0
                model: visible ? dialog.options : []
                clip: true; spacing: 5; currentIndex: dialog.index || 0; keyNavigationEnabled: false
                interactive: false
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { palette: root.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                FocusFrame {
                    objectName: "menuFocus"; parent: menuList.contentItem
                    target: menuList.currentItem; active: root.shown && menuList.visible
                    accent: root.colors.accent; reducedMotion: root.reducedMotion; radius: 8
                }
                delegate: Rectangle {
                    id: menuOption
                    objectName: "settingOptionRow"
                    required property var modelData
                    required property int index
                    property bool singleLine: !!modelData.singleLine
                    property bool toggle: typeof modelData.checked === "boolean"
                    property bool pending: !!modelData.pendingAction && (viewState.pending || []).indexOf(modelData.pendingAction) >= 0
                    width: menuList.width - 10
                    height: singleLine ? Math.max(60, systemOptionLabel.implicitHeight + 20) : Math.max(64, systemOptionText.implicitHeight + 16)
                    radius: 8
                    color: dialog.index === index ? root.colors.menuSelected : "transparent"
                    border.width: 0
                    border.color: root.accent
                    opacity: modelData.disabled || pending ? 0.45 : 1
                    Image {
                        id: systemOptionIcon
                        objectName: "settingOptionIcon"
                        visible: !!modelData.icon
                        x: 15; anchors.verticalCenter: parent.verticalCenter
                        height: menuOption.singleLine ? systemOptionLabel.implicitHeight : systemOptionText.implicitHeight; width: height
                        source: visible ? root.desktopIconSource(modelData.icon) : ""
                        sourceSize: Qt.size(Math.ceil(width * 2), Math.ceil(height * 2))
                    }
                    Column {
                        id: systemOptionText; anchors.verticalCenter: parent.verticalCenter
                        x: modelData.icon ? systemOptionIcon.x + systemOptionIcon.width + 14 : 15
                        width: parent.width - x - 15 - (systemOptionControls.visible ? systemOptionControls.width + 18 : 0); spacing: 4
                        Text { id: systemOptionLabel; objectName: "settingOptionLabel"; textFormat: Text.PlainText; width: parent.width; text: modelData.label; font.family: root.fontFamily; font.pixelSize: 25; color: root.ink; maximumLineCount: 1; elide: Text.ElideRight }
                        Text { textFormat: Text.PlainText; width: parent.width; visible: !menuOption.singleLine && !!modelData.subtitle; text: modelData.subtitle || ""; font.family: root.fontFamily; font.pixelSize: 24; color: root.muted; wrapMode: modelData.wrapSubtitle ? Text.WrapAnywhere : Text.NoWrap; maximumLineCount: modelData.wrapSubtitle ? 2 : 1; elide: Text.ElideRight }
                    }
                    Row {
                        id: systemOptionControls
                        objectName: "settingOptionControls"
                        visible: menuOption.singleLine && (!!systemOptionStatus.text || menuOption.toggle || !!modelData.navigate)
                        anchors.right: parent.right; anchors.rightMargin: 15
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 12
                        Text {
                            id: systemOptionStatus
                            objectName: "settingOptionStatus"
                            visible: !!text
                            width: Math.min(implicitWidth, Math.max(0, (menuOption.width - systemOptionText.x - 15) * 0.52
                                - (menuOption.toggle ? settingSwitch.width + 12 : modelData.navigate ? optionChevron.width + 12 : 0)))
                            anchors.verticalCenter: parent.verticalCenter
                            text: menuOption.pending ? root.tr(msg.APPLYING) : modelData.subtitle || (menuOption.toggle ? root.tr(modelData.checked ? msg.ON : msg.OFF) : "")
                            textFormat: Text.PlainText; horizontalAlignment: Text.AlignRight
                            font.family: root.fontFamily; font.pixelSize: 25; color: root.muted
                            maximumLineCount: 1; elide: Text.ElideRight
                        }
                        Rectangle {
                            id: settingSwitch
                            objectName: "settingOptionSwitch"
                            visible: menuOption.toggle
                            property bool checked: !!modelData.checked
                            width: 54; height: 30; radius: height / 2
                            anchors.verticalCenter: parent.verticalCenter
                            color: checked ? root.accent : root.colors.track
                            border.width: 1; border.color: checked ? root.accent : root.muted
                            Accessible.role: Accessible.CheckBox
                            Accessible.name: modelData.label
                            Accessible.checkable: true; Accessible.checked: checked
                            Rectangle {
                                width: 22; height: 22; radius: height / 2
                                anchors.verticalCenter: parent.verticalCenter
                                x: settingSwitch.checked ? settingSwitch.width - width - 4 : 4
                                color: settingSwitch.checked ? root.colors.dialog : root.ink
                                Behavior on x { NumberAnimation { duration: viewState.reducedMotion ? 0 : 100 } }
                            }
                        }
                        Text {
                            id: optionChevron
                            objectName: "settingOptionChevron"
                            visible: !!modelData.navigate && !menuOption.toggle
                            anchors.verticalCenter: parent.verticalCenter
                            text: "›"; textFormat: Text.PlainText
                            font.family: root.fontFamily; font.pixelSize: 25; color: root.muted
                        }
                    }
                }
            }

            Text { visible: !!dialog.error; width: parent.width; text: dialog.error || ""; textFormat: Text.PlainText; font.family: root.fontFamily; font.pixelSize: 22; color: root.colors.error; wrapMode: Text.Wrap; maximumLineCount: 2 }

            KeyTestPanel {
                visible: dialog.kind === "key-test"
                width: parent.width
                colors: root.colors; fontFamily: root.fontFamily; state: dialog
                translate: root.tr
                msg: root.msg
                reducedMotion: viewState.reducedMotion || false
                compact: root.height < 660
                notice: viewState.toast || ""
            }

            TextField { palette: root.colors.controls;
                id: editor
                property QtObject inputController: controller
                visible: dialog.kind === "text"
                width: parent.width; height: 66
                font.family: root.fontFamily; font.pixelSize: 28; color: root.ink
                selectByMouse: false
                maximumLength: 4096
                echoMode: dialog.secret && !dialog.reveal ? TextInput.Password : TextInput.Normal
                inputMethodHints: dialog.secret ? Qt.ImhSensitiveData | Qt.ImhNoPredictiveText : (dialog.numeric ? Qt.ImhDigitsOnly : Qt.ImhNone)
                background: Rectangle { radius: 8; color: root.colors.input; border.width: 2; border.color: root.accent }
                onTextEdited: controller.editText(text)
                Keys.priority: Keys.BeforeItem
                Keys.onPressed: function(event) {
                    if (inputMethodComposing) {
                        event.accepted = [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Up,
                                          Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp,
                                          Qt.Key_PageDown].indexOf(event.key) >= 0
                        return
                    }
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (!event.isAutoRepeat) controller.dispatch("accept")
                        event.accepted = true
                    } else if (event.key === Qt.Key_Escape) {
                        if (!event.isAutoRepeat) controller.dispatch("back")
                        event.accepted = true
                    }
                }
            }

            Column {
                visible: dialog.kind === "slider"
                width: parent.width; spacing: 18
                Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: Math.round((dialog.value || 0) * 100) + "%"; font.family: root.fontFamily; font.pixelSize: 50; color: root.accent }
                Rectangle { width: parent.width; height: 12; radius: 6; color: root.colors.track; Rectangle { width: parent.width * (dialog.value || 0); height: parent.height; radius: 6; color: root.accent } }
            }

            ProgressBar { visible: dialog.kind === "progress" && !dialog.fileTaskId; width: parent.width; palette: root.colors.controls; indeterminate: true }
            FileProgress { visible: dialog.kind === "progress" && !!dialog.fileTaskId; width: parent.width; colors: root.colors; reducedMotion: viewState.reducedMotion || false; indeterminate: !dialog.task || dialog.task.phase === "preparing"; from: 0; to: Math.max(1, dialog.task ? dialog.task.totalBytes || dialog.task.totalFiles || 1 : 1); value: dialog.task ? dialog.task.doneBytes || dialog.task.doneFiles || 0 : 0 }

            Column {
                objectName: "fileTaskDetails"
                visible: !!dialog.fileTaskId && !!dialog.task
                width: parent.width; spacing: 8
                Text { width: parent.width; textFormat: Text.PlainText; text: dialog.task ? dialog.task.sourceLabel : ""; elide: Text.ElideMiddle; font.family: root.fontFamily; font.pixelSize: 21; color: root.muted }
                Text { width: parent.width; textFormat: Text.PlainText; text: dialog.task ? dialog.task.destinationLabel : ""; elide: Text.ElideMiddle; font.family: root.fontFamily; font.pixelSize: 21; color: root.muted }
                Text { width: parent.width; textFormat: Text.PlainText; text: dialog.task ? dialog.task.fileCountLabel + (dialog.task.etaLabel ? "   ·   " + dialog.task.etaLabel : "") : ""; elide: Text.ElideRight; font.family: root.fontFamily; font.pixelSize: 21; color: root.muted }
            }

            Flickable {
                id: previewContent
                objectName: "filePreviewContent"
                visible: dialog.kind === "file-preview" && dialog.previewType === "text"
                width: parent.width; height: panel.previewHeight
                clip: true; interactive: false; contentWidth: width; contentHeight: previewText.height
                Text { id: previewText; width: parent.width; textFormat: Text.PlainText; text: dialog.previewText || ""; wrapMode: Text.WrapAnywhere; font.family: root.fontFamily; font.pixelSize: 21; color: root.ink }
                ScrollBar.vertical: ScrollBar { palette: root.colors.controls; interactive: false }
            }
            Image {
                objectName: "filePreviewImage"
                visible: dialog.kind === "file-preview" && dialog.previewType === "image"
                width: parent.width; height: panel.previewHeight
                source: dialog.previewImage || ""; fillMode: Image.PreserveAspectFit
            }
            Text { id: previewNotice; visible: !!dialog.truncated; width: parent.width; textFormat: Text.PlainText; text: root.tr(msg.TEXT_PREVIEW_LIMITED_TO_64_KIB); font.family: root.fontFamily; font.pixelSize: 20; color: root.muted }

            DialogActions {
                visible: dialog.kind === "confirm" || dialog.kind === "text"
                width: parent.width; colors: root.colors; fontFamily: root.fontFamily
                labels: [root.tr(msg.CANCEL), root.tr(msg.CONFIRM)]
                reducedMotion: root.reducedMotion
                index: dialog.kind === "confirm" ? (dialog.index || 0) : 1
                mouseEnabled: viewState.page === "windows" && dialog.kind === "confirm"
                onChosen: function(index) { controller.chooseModal(index) }
            }

            InputHints {
                id: modalFooter; width: parent.width
                objectName: "modalFooter"
                fontFamily: root.fontFamily; textColor: root.muted; fontSize: 22
                hints: dialog.fileTaskId && dialog.kind === "progress" ? [
                    {keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: root.tr(msg.RUN_IN_BACKGROUND)},
                    {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: root.tr(msg.CANCEL_TASK)}
                ] : dialog.kind === "file-preview" ? (dialog.previewType === "text" ? [
                    {keys: ["keyboard_arrows"], label: root.tr(msg.SCROLL)}
                ] : []).concat([
                    {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: root.tr(msg.BACK)}
                ]).concat(dialog.item && !dialog.item.directory && !dialog.item.trash ? [{keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: root.tr(msg.OPEN)}] : []) : dialog.kind === "key-test" ? [{keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: root.tr(msg.HOLD_1_2_S_TO_RETURN)}] : dialog.kind === "calibration" ? [{keys: ["keyboard_escape"], label: root.tr(msg.CANCEL)}] : [
                    {keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: root.tr(msg.CONFIRM)},
                    {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: root.tr(dialog.kind === "text" ? msg.CANCEL : msg.BACK)}].concat(dialog.kind === "text" && dialog.secret ? [
                    {keys: ["gamecube_button_x"], label: root.tr(dialog.reveal ? msg.HIDE_PASSWORD : msg.SHOW_PASSWORD)} ] : [])
            }
            Text { textFormat: Text.PlainText; id: modalToast; visible: !!viewState.toast && dialog.kind !== "key-test"; width: parent.width; text: viewState.toast; font.family: root.fontFamily; font.pixelSize: dialog.kind === "console-details" ? 20 : 24; color: root.accent; wrapMode: Text.Wrap; maximumLineCount: dialog.kind === "console-details" ? 1 : 3; elide: Text.ElideRight }
        }
    }
}
