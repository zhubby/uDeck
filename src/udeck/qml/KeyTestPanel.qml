import QtQuick

Column {
    id: testPanel
    required property var colors
    required property string fontFamily
    required property var state
    required property var translate
    property bool reducedMotion: false
    spacing: 12
    function down(action) { return (state.pressed || []).indexOf(action) >= 0 }
    function tested(action) { return (state.tested || []).indexOf(action) >= 0 }
    Rectangle {
        width: parent.width; height: 220; radius: 12
        color: testPanel.colors.panel
        border.color: testPanel.colors.rowBorder
        Repeater {
            model: [
                {action: "previous-page", key: "gamecube_trigger_l", label: "L", x: 20, y: 12},
                {action: "next-page", key: "gamecube_trigger_r", label: "R", x: testPanel.width - 94, y: 12},
                {action: "up", key: "keyboard_arrow_up", label: testPanel.translate("Up"), x: 76, y: 62},
                {action: "left", key: "keyboard_arrow_up", rotation: 270, label: testPanel.translate("Left"), x: 20, y: 114},
                {action: "right", key: "keyboard_arrow_up", rotation: 90, label: testPanel.translate("Right"), x: 132, y: 114},
                {action: "down", key: "keyboard_arrow_up", rotation: 180, label: testPanel.translate("Down"), x: 76, y: 166},
                {action: "context", key: "gamecube_button_x", label: "X", x: testPanel.width - 140, y: 62},
                {action: "quick-settings", key: "gamecube_button_y", label: "Y", x: testPanel.width - 196, y: 114},
                {action: "accept", key: "gamecube_button_color_a", label: "A", x: testPanel.width - 84, y: 114},
                {action: "back", key: "gamecube_button_color_b", label: "B", x: testPanel.width - 140, y: 166}
            ]
            delegate: KeyTestCap {
                required property var modelData
                objectName: "testKey-" + modelData.action
                x: modelData.x; y: modelData.y
                width: modelData.action === "previous-page" || modelData.action === "next-page" ? 74 : 54
                height: 46
                colors: testPanel.colors; fontFamily: testPanel.fontFamily
                keyId: modelData.key; label: modelData.label; iconRotation: modelData.rotation || 0
                stateLabel: testPanel.translate(pressed ? "Pressed" : "Released")
                pressed: testPanel.down(modelData.action); tested: testPanel.tested(modelData.action)
                reducedMotion: testPanel.reducedMotion
            }
        }
        Column {
            x: 204; y: 36; width: parent.width - 418; spacing: 8
            Text { width: parent.width; text: testPanel.translate("Last input"); horizontalAlignment: Text.AlignHCenter; font.family: testPanel.fontFamily; font.pixelSize: 20; color: testPanel.colors.muted }
            Text {
                objectName: "testLastKey"; width: parent.width
                text: testPanel.state.lastKey || ""; textFormat: Text.PlainText
                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                font.family: testPanel.fontFamily; font.pixelSize: 32; color: testPanel.colors.text
            }
            Text { width: parent.width; text: testPanel.state.lastSource || ""; horizontalAlignment: Text.AlignHCenter; font.family: testPanel.fontFamily; font.pixelSize: 20; color: testPanel.colors.muted }
            Text {
                width: parent.width; text: testPanel.state.exitHolding ? testPanel.translate("Keep holding to exit…") : ((testPanel.state.activeLabels || []).length ? testPanel.translate("Pressed") : testPanel.translate("Released"))
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                font.family: testPanel.fontFamily; font.pixelSize: 22; color: testPanel.colors.accent
            }
        }
    }
    Text {
        objectName: "testHeldKeys"; width: parent.width
        text: testPanel.translate("Held keys") + ": " + ((testPanel.state.activeLabels || []).join(" + ") || "—")
        textFormat: Text.PlainText; elide: Text.ElideRight
        font.family: testPanel.fontFamily; font.pixelSize: 22; color: testPanel.colors.text
    }
    Row {
        width: parent.width
        Text {
            width: parent.width / 2
            text: testPanel.translate("Controls checked") + ": " + (testPanel.state.tested || []).length + " / 10"
            font.family: testPanel.fontFamily; font.pixelSize: 20; color: testPanel.colors.muted
        }
        Text {
            width: parent.width / 2; horizontalAlignment: Text.AlignRight
            text: testPanel.translate("Key presses") + ": " + (testPanel.state.pressCount || 0)
            font.family: testPanel.fontFamily; font.pixelSize: 20; color: testPanel.colors.muted
        }
    }
}
