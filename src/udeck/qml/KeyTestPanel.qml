import QtQuick

Column {
    id: testPanel
    required property var colors
    required property string fontFamily
    required property var state
    required property var translate
    required property var msg
    property bool reducedMotion: false
    property bool compact: false
    property string notice: ""
    // Keep delegates alive across input edges so press/release animations run.
    property string layoutOwner: ""
    property var keyboardRows: []
    property var gamepadKeys: []
    property var pointerKeys: []
    property var internalKeys: []
    onStateChanged: {
        if (state.kind === "key-test" && state.key !== layoutOwner) {
            layoutOwner = state.key
            keyboardRows = state.keyboardRows || []
            gamepadKeys = state.gamepadKeys || []
            pointerKeys = state.pointerKeys || []
            internalKeys = state.internalKeys || []
        }
    }
    spacing: 8
    function down(action) { return (state.pressed || []).indexOf(action) >= 0 }
    function tested(action) { return (state.tested || []).indexOf(action) >= 0 }
    function rowWeight(row) { return row.reduce((total, key) => total + key.weight, 0) }
    readonly property int keyHeight: compact ? 30 : 36
    Row {
        width: parent.width; spacing: 16
        Column {
            id: keyboard
            width: parent.width - 270; spacing: 4
            Text {
                text: testPanel.translate(msg.KEYBOARD_FN_OUTPUTS); width: parent.width; height: 24
                font.family: testPanel.fontFamily; font.pixelSize: 18; color: testPanel.colors.muted
            }
            Repeater {
                model: testPanel.keyboardRows
                delegate: Row {
                    required property var modelData
                    readonly property real units: testPanel.rowWeight(modelData)
                    readonly property real unitWidth: (keyboard.width - (modelData.length - 1) * spacing) / units
                    width: keyboard.width; height: testPanel.keyHeight; spacing: 4
                    Repeater {
                        model: modelData
                        delegate: KeyTestCap {
                            required property var modelData
                            objectName: "testKey-" + modelData.id
                            width: parent.unitWidth * modelData.weight; height: testPanel.keyHeight
                            colors: testPanel.colors; fontFamily: testPanel.fontFamily
                            keyId: modelData.key; label: modelData.labelKey ? testPanel.translate(modelData.labelKey) : modelData.label
                            detectable: modelData.detectable
                            iconSize: testPanel.compact ? 28 : 34
                            fontSize: testPanel.compact ? 15 : 18
                            sideLabel: modelData.id === "shift-left" ? "L" : modelData.id === "shift-right" ? "R" : ""
                            stateLabel: testPanel.translate(!detectable ? msg.FIRMWARE_SYSTEM : pressed ? msg.PRESSED : msg.RELEASED)
                            pressed: testPanel.down(modelData.id); tested: testPanel.tested(modelData.id)
                            reducedMotion: testPanel.reducedMotion
                        }
                    }
                }
            }
        }
        Item {
            width: 254; height: Math.max(308, keyboard.height)
            Text {
                text: testPanel.translate(msg.CONTROLS_TRACKBALL); width: parent.width
                font.family: testPanel.fontFamily; font.pixelSize: 18; color: testPanel.colors.muted
            }
            Repeater {
                model: testPanel.gamepadKeys
                delegate: KeyTestCap {
                    required property var modelData
                    required property int index
                    readonly property var positions: [
                        [0, 28, 52], [56, 28, 64], [124, 28, 64], [192, 28, 52],
                        [36, 72, 34], [174, 72, 34], [0, 110, 34], [72, 110, 34],
                        [138, 110, 34], [210, 110, 34], [36, 148, 34], [174, 148, 34]
                    ]
                    objectName: "testKey-" + modelData.id
                    x: positions[index][0]; y: positions[index][1]; width: positions[index][2]; height: 34
                    colors: testPanel.colors; fontFamily: testPanel.fontFamily
                    keyId: modelData.key; label: modelData.labelKey ? testPanel.translate(modelData.labelKey) : modelData.label
                    iconRotation: modelData.rotation
                    stateLabel: testPanel.translate(pressed ? msg.PRESSED : msg.RELEASED)
                    pressed: testPanel.down(modelData.id); tested: testPanel.tested(modelData.id)
                    reducedMotion: testPanel.reducedMotion
                }
            }
            Text {
                y: 188; width: parent.width; text: testPanel.translate(msg.L_R_MOUSE_BUTTONS)
                font.family: testPanel.fontFamily; font.pixelSize: 15; color: testPanel.colors.muted
            }
            Repeater {
                model: testPanel.pointerKeys
                delegate: KeyTestCap {
                    required property var modelData
                    required property int index
                    objectName: "testKey-" + modelData.id
                    x: index < 5 ? index * 44 : (index - 5) * 40
                    y: index < 5 ? 210 : 246
                    width: 36; height: 30
                    colors: testPanel.colors; fontFamily: testPanel.fontFamily
                    keyId: modelData.key; label: modelData.labelKey ? testPanel.translate(modelData.labelKey) : modelData.label
                    iconRotation: modelData.rotation; iconSize: 28
                    stateLabel: testPanel.translate(pressed ? msg.PRESSED : msg.RELEASED)
                    pressed: testPanel.down(modelData.id); tested: testPanel.tested(modelData.id)
                    reducedMotion: testPanel.reducedMotion
                }
            }
            Text {
                x: 84; y: 249; width: parent.width - 84
                text: testPanel.translate(msg.SELECT_TRACKBALL_SCROLL)
                elide: Text.ElideRight; font.family: testPanel.fontFamily; font.pixelSize: 14
                color: testPanel.colors.muted
            }
            Row {
                y: 282; spacing: 4
                Repeater {
                    model: testPanel.internalKeys
                    delegate: KeyTestCap {
                        required property var modelData
                        objectName: "testKey-" + modelData.id
                        width: 82; height: 26; fontSize: 13
                        colors: testPanel.colors; fontFamily: testPanel.fontFamily
                        keyId: ""; label: modelData.labelKey ? testPanel.translate(modelData.labelKey) : modelData.label
                        detectable: false; stateLabel: testPanel.translate(msg.FIRMWARE_SYSTEM)
                    }
                }
            }
        }
    }
    Row {
        width: parent.width
        Text {
            objectName: "testLastKey"; width: parent.width * 0.62
            text: testPanel.translate(msg.LAST_INPUT) + ": " + (testPanel.state.lastKey || "")
                  + (testPanel.state.lastSource ? " · " + testPanel.state.lastSource : "")
            textFormat: Text.PlainText; elide: Text.ElideRight
            font.family: testPanel.fontFamily; font.pixelSize: 20; color: testPanel.colors.text
        }
        Text {
            width: parent.width * 0.38; horizontalAlignment: Text.AlignRight
            text: testPanel.translate(msg.CONTROLS_CHECKED) + ": " + (testPanel.state.tested || []).length + " / "
                  + (testPanel.state.totalKeys || 0) + "   ·   " + testPanel.translate(msg.KEY_PRESSES) + ": "
                  + (testPanel.state.pressCount || 0)
            font.family: testPanel.fontFamily; font.pixelSize: 18; color: testPanel.colors.muted
        }
    }
    Text {
        objectName: "testHeldKeys"; width: parent.width
        text: testPanel.state.exitHolding ? testPanel.translate(msg.KEEP_HOLDING_TO_EXIT)
              : testPanel.translate(msg.HELD_KEYS) + ": " + ((testPanel.state.activeLabels || []).join(" + ") || "—")
        textFormat: Text.PlainText; elide: Text.ElideRight
        font.family: testPanel.fontFamily; font.pixelSize: 18; color: testPanel.colors.accent
    }
    Text {
        width: parent.width; text: testPanel.state.deviceWarning || testPanel.notice || testPanel.translate(msg.FIRMWARE_KEY_TEST_INSTRUCTIONS)
        textFormat: Text.PlainText; elide: Text.ElideRight
        font.family: testPanel.fontFamily; font.pixelSize: 15
        color: testPanel.state.deviceWarning ? testPanel.colors.error : testPanel.notice ? testPanel.colors.accent : testPanel.colors.muted
    }
}
