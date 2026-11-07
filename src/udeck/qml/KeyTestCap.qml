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
    width: 54; height: 50; radius: 8
    color: pressed ? colors.menuSelected : colors.panel
    border.width: pressed ? 3 : 1
    border.color: pressed || tested ? colors.accent : colors.rowBorder
    scale: pressed ? 0.91 : 1
    Behavior on scale { NumberAnimation { duration: cap.reducedMotion ? 0 : 80; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.StaticText
    Accessible.name: label + " · " + stateLabel
    InputIcon { anchors.centerIn: parent; keyId: cap.keyId; iconSize: 40; rotation: cap.iconRotation }
    Text {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 2
        visible: cap.tested && !cap.pressed
        text: "✓"; font.family: cap.fontFamily; font.pixelSize: 14; color: cap.colors.accent
        Accessible.ignored: true
    }
}
