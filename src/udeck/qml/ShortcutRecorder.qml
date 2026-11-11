import QtQuick
import QtQuick.Window
import QtQuick.Controls

Window {
    id: window
    title: "uDeck Shortcut Recorder"
    visible: false
    flags: Qt.Dialog | Qt.FramelessWindowHint
    modality: Qt.WindowModal
    color: colors.dialog
    property var viewState: JSON.parse(controller.viewSnapshotJson)
    property var state: JSON.parse(recorder.snapshotJson)
    function tr(source) { return controller.translate(source, viewState.language) }
    ThemePalette { id: colors; theme: window.viewState.theme; profile: "shell" }
    InterfaceFonts { id: fonts; language: window.viewState.language }
    onActiveChanged: recorder.activeChanged(active)
    onClosing: recorder.cancel()

    component RecorderButton: Button {
        id: button
        property var promptKeys: []
        implicitWidth: Math.max(220, contentItem.implicitWidth + 24)
        implicitHeight: 50
        opacity: enabled ? 1 : 0.45
        background: Rectangle {
            radius: 8; color: button.down ? colors.buttonSelected : colors.button
            border.width: 1; border.color: colors.buttonBorder
        }
        contentItem: InputPrompt {
            keys: button.promptKeys; label: button.text
            fontFamily: fonts.family; fontSize: 22; iconSize: 30; textColor: colors.text
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"; border.width: 2; border.color: colors.accent; radius: 12
    }
    Column {
        x: 28; y: 24; width: parent.width - 56; spacing: 16
        Text {
            objectName: "shortcutRecordingTitle"
            width: parent.width; text: window.state.label; textFormat: Text.PlainText
            font.family: fonts.family; font.pixelSize: 27; font.weight: Font.DemiBold
            color: colors.text; elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: !window.state.ready ? window.tr("Preparing shortcut recording…") : window.state.sequence
                ? window.tr("Release all keys, then confirm") : window.tr("Press a new key combination")
            textFormat: Text.PlainText; font.family: fonts.family; font.pixelSize: 23
            color: colors.muted; wrapMode: Text.Wrap
        }
        Rectangle {
            width: parent.width; height: 76; radius: 8
            color: colors.menuSelected; border.width: 1; border.color: colors.dialogBorder
            Text {
                objectName: "recordedShortcut"
                anchors.fill: parent; anchors.margins: 12
                text: window.state.sequence || "…"; textFormat: Text.PlainText
                font.family: fonts.family; font.pixelSize: 34; font.weight: Font.Medium
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                color: colors.text; elide: Text.ElideRight
            }
        }
        Text {
            width: parent.width; height: 48
            text: window.state.error || window.tr("Esc cancels · recording ends after 15 seconds")
            textFormat: Text.PlainText; font.family: fonts.family; font.pixelSize: 21
            color: window.state.error ? colors.error : colors.muted
            wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
        }
        Row {
            spacing: 20
            RecorderButton {
                text: window.tr("Cancel"); promptKeys: ["gamecube_button_color_b", "/", "keyboard_escape"]
                onClicked: recorder.cancel()
            }
            RecorderButton {
                text: window.tr("Confirm"); promptKeys: ["gamecube_button_color_a", "/", "keyboard_enter"]
                enabled: window.state.canConfirm; onClicked: recorder.confirm()
            }
        }
    }
}
