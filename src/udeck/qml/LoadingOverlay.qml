/*
[INPUT]: 依赖请求身份、启动内容、主题与前台交接状态。
[OUTPUT]: 提供保留退出内容且可立即隐藏的启动遮罩。
[POS]: 桌面启动和应用打开的视觉边界，不延迟输入交接。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: overlay
    required property var colors
    required property string fontFamily
    property bool shown: false
    property bool brand: false
    property bool reducedMotion: false
    property bool immediateHide: false
    property string requestId: ""
    property string applicationName: ""
    property string applicationIcon: "application-x-executable"
    property string homeKind: ""
    property string message: ""
    property string returnLabel: ""
    property var presentation: ({})
    readonly property bool presenting: shown && !immediateHide
    readonly property bool animationRunning: indicator.animationRunning
    opacity: 0
    visible: opacity > 0
    enabled: presenting
    Accessible.role: Accessible.StaticText
    Accessible.name: (presentation.name || "") + ". " + (presentation.message || "")
    Accessible.ignored: !presenting

    function syncPresentation() {
        const showNow = shown && !immediateHide
        if (showNow) {
            presentation = {requestId: requestId, name: applicationName, icon: applicationIcon,
                            homeKind: homeKind, message: message, returnLabel: returnLabel}
        }
        fade.stop()
        if (reducedMotion || immediateHide) {
            opacity = showNow ? 1 : 0
            if (!showNow) presentation = ({})
        } else {
            fade.to = showNow ? 1 : 0
            fade.duration = showNow ? 140 : 120
            fade.start()
        }
    }
    onShownChanged: Qt.callLater(syncPresentation)
    onRequestIdChanged: Qt.callLater(syncPresentation)
    onApplicationNameChanged: Qt.callLater(syncPresentation)
    onApplicationIconChanged: Qt.callLater(syncPresentation)
    onHomeKindChanged: Qt.callLater(syncPresentation)
    onMessageChanged: Qt.callLater(syncPresentation)
    onReturnLabelChanged: Qt.callLater(syncPresentation)
    onReducedMotionChanged: if (reducedMotion) syncPresentation()
    onImmediateHideChanged: syncPresentation()
    Component.onCompleted: syncPresentation()
    NumberAnimation {
        id: fade; target: overlay; property: "opacity"; easing.type: Easing.OutCubic
        onFinished: if (!overlay.presenting) overlay.presentation = ({})
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
            color: overlay.brand ? "transparent" : overlay.presentation.homeKind ? overlay.colors.artwork(overlay.presentation.homeKind) : "transparent"

            BrandLogo {
                colors: overlay.colors
                visible: overlay.brand
                anchors.fill: parent
            }

            HomeIcon {
                visible: !overlay.brand && !!overlay.presentation.homeKind
                anchors.centerIn: parent
                width: 54
                height: 54
                kind: overlay.presentation.homeKind || ""
            }

            Image {
                visible: !overlay.brand && !overlay.presentation.homeKind
                anchors.fill: parent
                source: visible ? "image://desktop/" + encodeURIComponent(overlay.presentation.icon || "application-x-executable") : ""
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
            text: overlay.presentation.name || ""
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
            text: overlay.presentation.message || ""
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
            active: overlay.presenting && overlay.visible
            reducedMotion: overlay.reducedMotion
        }

        InputPrompt {
            objectName: "loadingReturnHint"
            visible: !overlay.brand
            anchors.horizontalCenter: parent.horizontalCenter
            y: 232
            keys: ["gamecube_button_color_b", "/", "keyboard_escape"]
            label: overlay.presentation.returnLabel || ""
            fontFamily: overlay.fontFamily
            textColor: overlay.colors.muted
            iconSize: 22
            fontSize: 18
        }
    }
}
