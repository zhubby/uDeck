import QtQuick

Item {
    id: overlay
    required property var colors
    required property string fontFamily
    property bool shown: false
    property bool brand: false
    property bool reducedMotion: false
    property bool immediateHide: false
    property string applicationName: ""
    property string applicationIcon: "application-x-executable"
    property string homeKind: ""
    property string message: ""
    property string returnLabel: ""
    readonly property bool animationRunning: indicator.animationRunning
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown
    Accessible.role: Accessible.StaticText
    Accessible.name: applicationName + ". " + message
    Accessible.ignored: !shown

    Behavior on opacity {
        enabled: !overlay.reducedMotion && !overlay.immediateHide
        NumberAnimation { duration: overlay.shown ? 140 : 120 }
    }

    Rectangle {
        anchors.fill: parent
        color: overlay.brand ? overlay.colors.background : "#66000000"
    }

    Rectangle {
        id: panel
        objectName: "loadingPanel"
        anchors.centerIn: parent
        width: Math.min(392, parent.width - 64)
        height: 280
        radius: 20
        color: overlay.brand ? "transparent" : overlay.colors.panel
        border.width: overlay.brand ? 0 : 1
        border.color: overlay.colors.border

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 28
            width: 72
            height: 72
            radius: 18
            color: overlay.brand ? "transparent" : overlay.homeKind ? overlay.colors.artwork(overlay.homeKind) : "transparent"

            BrandLogo {
                colors: overlay.colors
                visible: overlay.brand
                anchors.fill: parent
            }

            HomeIcon {
                visible: !overlay.brand && !!overlay.homeKind
                anchors.centerIn: parent
                width: 54
                height: 54
                kind: overlay.homeKind
            }

            Image {
                visible: !overlay.brand && !overlay.homeKind
                anchors.fill: parent
                source: visible ? "image://desktop/" + encodeURIComponent(overlay.applicationIcon || "application-x-executable") : ""
                sourceSize: Qt.size(72, 72)
                fillMode: Image.PreserveAspectFit
            }
        }

        Text {
            objectName: "loadingTitle"
            x: 24
            y: 112
            width: parent.width - 48
            height: 36
            textFormat: Text.PlainText
            text: overlay.applicationName
            color: overlay.colors.text
            font.family: overlay.fontFamily
            font.pixelSize: overlay.brand ? 31 : 24
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        Text {
            objectName: "loadingMessage"
            x: 24
            y: 153
            width: parent.width - 48
            height: 42
            textFormat: Text.PlainText
            text: overlay.message
            color: overlay.colors.muted
            font.family: overlay.fontFamily
            font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignTop
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        LoadingIndicator {
            id: indicator
            anchors.horizontalCenter: parent.horizontalCenter
            y: 203
            colors: overlay.colors
            active: overlay.shown && overlay.visible
            reducedMotion: overlay.reducedMotion
        }

        InputPrompt {
            objectName: "loadingReturnHint"
            visible: !overlay.brand
            anchors.horizontalCenter: parent.horizontalCenter
            y: 232
            keys: ["gamecube_button_color_b", "/", "keyboard_escape"]
            label: overlay.returnLabel
            fontFamily: overlay.fontFamily
            textColor: overlay.colors.muted
            iconSize: 22
            fontSize: 18
        }
    }
}
