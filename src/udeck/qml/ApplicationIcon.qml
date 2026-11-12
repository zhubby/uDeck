import QtQuick

Image {
    id: icon
    required property string iconName
    required property var colors
    readonly property string nativeKind: /^io\.github\.zhubby\.uDeck\.(Terminal|Music|Video|Reader|Emulator|Browser)$/.test(iconName)
        ? iconName.split(".").pop().toLowerCase() : ""
    source: nativeKind ? "" : "image://desktop/" + encodeURIComponent(
        (iconName || "application-x-executable")
        + (iconName.startsWith("udeck-setting:") ? "/" + colors.artText.toString() : ""))
    fillMode: Image.PreserveAspectFit

    Rectangle {
        objectName: "applicationBackground"
        anchors.fill: parent
        visible: !!icon.nativeKind
        radius: width * 22 / 96
        color: icon.colors.artwork(icon.nativeKind)

        HomeIcon {
            objectName: "applicationGlyph"
            anchors.centerIn: parent
            width: parent.width * 0.76
            height: width
            kind: icon.nativeKind
        }
    }
}
