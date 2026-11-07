import QtQuick

Rectangle {
    id: cap
    required property var colors
    required property string fontFamily
    required property string keyId
    required property string label
    required property string stateLabel
    property bool pressed: false
    property bool tested: false
    property int iconRotation: 0
    property bool reducedMotion: false
    property bool detectable: true
    property int iconSize: 32
    property int fontSize: 16
    property string sideLabel: ""
    width: 54; height: 50; radius: 8
    color: pressed ? colors.menuSelected : colors.panel
    border.width: pressed ? 3 : 1
    border.color: pressed || tested ? colors.accent : colors.rowBorder
    opacity: detectable ? 1 : 0.55
    scale: pressed ? 0.91 : 1
    Behavior on scale { NumberAnimation { duration: cap.reducedMotion ? 0 : 80; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.StaticText
    Accessible.name: label + " · " + stateLabel
    InputIcon {
        anchors.centerIn: parent; visible: !!cap.keyId
        keyId: cap.keyId; iconSize: Math.min(cap.iconSize, (cap.width - 4) / artworkScale)
        rotation: cap.iconRotation
    }
    Text {
        visible: !cap.keyId; anchors.centerIn: parent; width: parent.width - 4
        text: cap.label; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter
        font.family: cap.fontFamily; font.pixelSize: cap.fontSize
        color: cap.pressed ? cap.colors.accent : cap.colors.text
        elide: Text.ElideRight
        Accessible.ignored: true
    }
    Text {
        visible: !!cap.sideLabel; text: cap.sideLabel
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 1
        font.family: cap.fontFamily; font.pixelSize: 10; color: cap.colors.text
        Accessible.ignored: true
    }
    Text {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 2
        visible: cap.tested && !cap.pressed
        text: "✓"; font.family: cap.fontFamily; font.pixelSize: 14; color: cap.colors.accent
        Accessible.ignored: true
    }
}
