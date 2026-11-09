// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../../qml" as Shared
import "../../common/qml"

Item {
    id: surface
    required property var colors
    required property var host
    property var appState: host ? host.state : ({current:{},media:{}})
    function tr(s){return host?host.tr(s):s}
    Rectangle { anchors.fill: parent; color: surface.colors.background }
    RowLayout {
        anchors.fill: parent; anchors.margins: host && host.width<1100?40:64; spacing: 48
        Artwork { fontFamily: surface.host.fontFamily; colors: surface.colors; Layout.preferredWidth: host && host.width<1100?280:350; Layout.preferredHeight: width; cover: appState.current.cover||""; kind: "music" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 20
            Text { font.family: surface.host.fontFamily; text: surface.tr("Now playing"); color: surface.colors.muted; font.pixelSize: 20 }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; text: appState.current.title||""; color: surface.colors.text; font.pixelSize: 36; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; text: appState.current.artist||appState.current.album||""; color: surface.colors.muted; font.pixelSize: 24; wrapMode: Text.Wrap }
            Text { font.family: surface.host.fontFamily; text: (appState.current.format||"")+"  ·  "+(appState.media.output||""); color: surface.colors.muted; font.pixelSize: 18 }
            Item { Layout.preferredHeight: 12 }
            Slider { palette: surface.colors.controls; Layout.fillWidth: true; from: 0; to: appState.media.duration||1; value: appState.media.position||0; onMoved: controller.seek(value) }
            Text { font.family: surface.host.fontFamily; text: host?host.time(appState.media.position)+" / "+host.time(appState.media.duration):""; color: surface.colors.muted; font.pixelSize: 20 }
            RowLayout {
                spacing: 14
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: "⏮"; selected: appState.control===0; onActivated: controller.command("previous") }
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: appState.media.playing?surface.tr("Pause"):surface.tr("Play"); selected: appState.control===1; onActivated: controller.command("play-pause") }
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: "⏭"; selected: appState.control===2; onActivated: controller.command("next") }
            }
            Text { font.family: surface.host.fontFamily; text: surface.tr("Shuffle")+": "+(appState.shuffle?surface.tr("On"):surface.tr("Off"))+"   ·   "+surface.tr("Repeat")+": "+(appState.repeatLabel||surface.tr("Off")); color: surface.colors.muted; font.pixelSize: 18 }
        }
    }
    Text { font.family: surface.host.fontFamily; anchors.centerIn: parent; visible: appState.media.loading||false; text: surface.tr("Loading…"); color: surface.colors.text; font.pixelSize: 28 }
}
