// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Window
import QtQuick.Controls

Item {
    id: root
    objectName: "wirelessStatusIcon"
    implicitWidth: 32
    implicitHeight: 32
    required property var colors
    required property string fontFamily
    property string kind: "wifi"
    property string deviceId: ""
    property string status: "disconnected"
    property int signalLevel: 0
    property bool strengthKnown: false
    property string description: ""
    property Item hoverSurface: null
    // The launcher's pointer shield owns mouse input. Observe its position
    // without adding a second mouse target or changing button navigation.
    readonly property point hoverPosition: hoverSurface && hoverSurface.containsMouse
        ? mapFromItem(hoverSurface, hoverSurface.mouseX, hoverSurface.mouseY) : Qt.point(-1, -1)
    readonly property real pixelRatio: Screen.devicePixelRatio
    readonly property color activeColor: status === "connecting" || kind === "hotspot" ? colors.accent : colors.text
    readonly property color inactiveColor: colors.signalInactive
    readonly property color markerColor: status === "unavailable" || status === "failed" ? colors.error : colors.muted
    readonly property color baseColor: colors.background
    readonly property string marker: status === "unavailable" || status === "failed" ? "!" : status === "unmanaged" ? "−"
                                    : status === "connected" && !strengthKnown ? "?" : ""

    Accessible.role: Accessible.StaticText
    Accessible.name: description
    onKindChanged: artwork.requestPaint()
    onStatusChanged: artwork.requestPaint()
    onSignalLevelChanged: artwork.requestPaint()
    onStrengthKnownChanged: artwork.requestPaint()
    onActiveColorChanged: artwork.requestPaint()
    onInactiveColorChanged: artwork.requestPaint()
    onMarkerColorChanged: artwork.requestPaint()
    onBaseColorChanged: artwork.requestPaint()

    // Rasterize vector paths at the screen's physical resolution. No bitmap
    // enlargement or extra Qt modules are needed on the handheld.
    Canvas {
        id: artwork
        width: Math.round(root.width * root.pixelRatio)
        height: Math.round(root.height * root.pixelRatio)
        transformOrigin: Item.TopLeft
        scale: 1 / root.pixelRatio
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            ctx.scale(width / 32, height / 32)
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.lineWidth = 2.5
            if (root.kind === "bluetooth") {
                ctx.strokeStyle = root.colors.muted
                ctx.beginPath()
                ctx.moveTo(10, 9)
                ctx.lineTo(23, 22)
                ctx.lineTo(16, 29)
                ctx.lineTo(16, 3)
                ctx.lineTo(23, 10)
                ctx.lineTo(10, 23)
                ctx.stroke()
                return
            }
            if (root.kind === "hotspot") {
                const busy = ["starting", "stopping", "restoring"].indexOf(root.status) >= 0
                ctx.strokeStyle = root.status === "failed" ? root.markerColor
                    : root.status === "active" || busy ? root.activeColor : root.inactiveColor
                for (let radius of [7, 13]) {
                    ctx.beginPath()
                    ctx.arc(16, 14, radius, -Math.PI / 3, Math.PI / 3)
                    ctx.stroke()
                    ctx.beginPath()
                    ctx.arc(16, 14, radius, 2 * Math.PI / 3, 4 * Math.PI / 3)
                    ctx.stroke()
                }
                ctx.beginPath()
                ctx.arc(16, 14, 2, 0, 2 * Math.PI)
                ctx.fillStyle = ctx.strokeStyle
                ctx.fill()
                ctx.beginPath()
                ctx.moveTo(16, 18)
                ctx.lineTo(16, 25)
                ctx.stroke()
                if (busy) {
                    for (let x of [11, 16, 21]) {
                        ctx.beginPath()
                        ctx.arc(x, 29, 1, 0, 2 * Math.PI)
                        ctx.fill()
                    }
                } else if (root.status !== "failed") {
                    ctx.beginPath()
                    ctx.moveTo(12, 28)
                    ctx.lineTo(20, 28)
                    ctx.stroke()
                }
                return
            }
            const connected = root.status === "connected"
            for (let i = 0; i < 3; i++) {
                ctx.strokeStyle = connected && root.signalLevel >= 4 - i ? root.activeColor : root.inactiveColor
                ctx.beginPath()
                ctx.arc(16, 26, 20 - i * 6, -3 * Math.PI / 4, -Math.PI / 4)
                ctx.stroke()
            }
            if (root.status === "connecting") {
                ctx.fillStyle = root.activeColor
                for (let i = 0; i < 3; i++) {
                    ctx.beginPath()
                    ctx.arc(11 + i * 5, 26, 1.5, 0, 2 * Math.PI)
                    ctx.fill()
                }
            } else if (root.status === "disconnected") {
                ctx.strokeStyle = root.markerColor
                ctx.lineWidth = 2
                ctx.beginPath()
                ctx.moveTo(14, 24)
                ctx.lineTo(18, 28)
                ctx.moveTo(18, 24)
                ctx.lineTo(14, 28)
                ctx.stroke()
            } else if (!root.marker) {
                ctx.fillStyle = connected && root.signalLevel > 0 ? root.activeColor : root.inactiveColor
                ctx.beginPath()
                ctx.arc(16, 26, 1.8, 0, 2 * Math.PI)
                ctx.fill()
            }
            if (root.status === "off") {
                ctx.beginPath()
                ctx.moveTo(5, 29)
                ctx.lineTo(28, 6)
                ctx.strokeStyle = root.baseColor
                ctx.lineWidth = 6
                ctx.stroke()
                ctx.strokeStyle = root.markerColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            }
        }
    }

    Text {
        visible: root.kind !== "bluetooth" && root.marker !== ""
        x: 8; y: 18; width: 16; height: 15
        text: root.marker
        textFormat: Text.PlainText
        font.family: root.fontFamily
        font.pixelSize: 15
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: root.markerColor
    }

    ToolTip {
        id: tooltip
        visible: root.visible && root.hoverPosition.x >= 0 && root.hoverPosition.x < root.width
                 && root.hoverPosition.y >= 0 && root.hoverPosition.y < root.height
        delay: 500
        width: Math.min(implicitWidth, root.Window.window ? root.Window.window.width - 56 : 600)
        text: root.description
        font.family: root.fontFamily
        font.pixelSize: 18
        palette: root.colors.controls
        contentItem: Text {
            objectName: "wirelessStatusTooltipText"
            text: tooltip.text
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            font: tooltip.font
            color: root.colors.text
        }
    }
}
