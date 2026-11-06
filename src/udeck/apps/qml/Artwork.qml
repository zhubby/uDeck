// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
Rectangle {
    id: art
    property string cover: ""
    property string label: ""
    property string kind: "music"
    radius: 7
    color: ({music:"#344749",video:"#42495a",reader:"#4e4535",games:"#384738"})[kind] || "#334346"
    clip: true
    Rectangle { x: parent.width*0.58; y: -parent.height*0.1; width: parent.width*0.65; height: parent.height*1.2; rotation: 26; color: "#18edb866" }
    Text { anchors.centerIn: parent; text: ({music:"♫",video:"▷",reader:"≡",games:"✚"})[art.kind] || "⌁"; color: "#e8cc9f"; font.pixelSize: Math.min(parent.width,parent.height)*0.4 }
    Image { anchors.fill: parent; source: art.cover; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 500; visible: status === Image.Ready }
}
