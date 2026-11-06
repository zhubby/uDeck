// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

Item {
    id: surface
    property var host
    property var appState: host ? host.state : ({current:{},media:{}})
    function tr(s){return host?host.tr(s):s}
    Rectangle { anchors.fill: parent; color: appState.app==="video"?"black":"#171b1d" }
    VideoOutput {
        anchors.fill: parent
        visible: appState.app==="video"&&!controller.softwareRendering
        fillMode: VideoOutput.PreserveAspectFit
        Component.onCompleted: controller.setVideoSink(videoSink)
    }
    Image {
        anchors.fill:parent;visible:appState.app==="video"&&controller.softwareRendering
        source:visible&&appState.videoFrameRevision>0?"image://video/"+appState.videoFrameRevision:""
        fillMode:Image.PreserveAspectFit;cache:false
    }
    RowLayout {
        anchors.fill: parent; anchors.margins: host && host.width<1100?40:64; spacing: 48
        visible: appState.app==="music"
        Artwork { Layout.preferredWidth: host && host.width<1100?280:350; Layout.preferredHeight: width; cover: appState.current.cover||""; kind: "music" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 20
            Text { text: surface.tr("Now playing"); color: "#a8acae"; font.pixelSize: 20 }
            Text { Layout.fillWidth: true; text: appState.current.title||""; color: "#f1eee7"; font.pixelSize: 36; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
            Text { Layout.fillWidth: true; text: appState.current.artist||appState.current.album||""; color: "#a8acae"; font.pixelSize: 24; wrapMode: Text.Wrap }
            Text { text: (appState.current.format||"")+"  ·  "+(appState.media.output||""); color: "#a8acae"; font.pixelSize: 18 }
            Item { Layout.preferredHeight: 12 }
            Slider { Layout.fillWidth: true; from: 0; to: appState.media.duration||1; value: appState.media.position||0; onMoved: controller.seek(value) }
            Text { text: host?host.time(appState.media.position)+" / "+host.time(appState.media.duration):""; color: "#a8acae"; font.pixelSize: 20 }
            RowLayout {
                spacing: 14
                SuiteButton { text: "⏮"; selected: appState.control===0; onActivated: controller.command("previous") }
                SuiteButton { text: appState.media.playing?surface.tr("Pause"):surface.tr("Play"); selected: appState.control===1; onActivated: controller.command("play-pause") }
                SuiteButton { text: "⏭"; selected: appState.control===2; onActivated: controller.command("next") }
            }
            Text { text: surface.tr("Shuffle")+": "+(appState.shuffle?surface.tr("On"):surface.tr("Off"))+"   ·   "+surface.tr("Repeat")+": "+(appState.repeatLabel||surface.tr("Off")); color: "#a8acae"; font.pixelSize: 18 }
        }
    }
    Rectangle {
        anchors.top: parent.top; width: parent.width; height: 100
        visible: appState.app==="video" && appState.controlsVisible
        gradient: Gradient { GradientStop{position:0;color:"#c9000000"} GradientStop{position:1;color:"transparent"} }
        Text { anchors.fill: parent; anchors.margins: 28; text: appState.current.title||""; color: "#f1eee7"; font.pixelSize: 28; elide: Text.ElideRight }
    }
    Text {
        anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom
        anchors.bottomMargin:appState.controlsVisible?170:46
        width:parent.width-100;text:appState.subtitleText||"";textFormat:Text.PlainText
        color:"white";style:Text.Outline;styleColor:"black";font.pixelSize:28
        horizontalAlignment:Text.AlignHCenter;wrapMode:Text.Wrap;visible:appState.app==="video"
    }
    Rectangle {
        anchors.bottom: parent.bottom; width: parent.width; height: 150
        visible: appState.app==="video" && appState.controlsVisible
        color: "#d1171b1d"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 10
            RowLayout {
                Slider { Layout.fillWidth: true; from:0;to:appState.media.duration||1;value:appState.media.position||0;onMoved:controller.seek(value) }
                Text { text:host?host.time(appState.media.position)+" / "+host.time(appState.media.duration):"";color:"#f1eee7";font.pixelSize:20 }
            }
            RowLayout {
                spacing: 18
                SuiteButton { text: surface.tr("Previous chapter"); selected: appState.control===0; onActivated: controller.command("previous") }
                SuiteButton { text: appState.media.playing?surface.tr("Pause"):surface.tr("Play"); selected: appState.control===1; onActivated: controller.command("play-pause") }
                SuiteButton { text: surface.tr("Next chapter"); selected: appState.control===2; onActivated: controller.command("next") }
                Item { Layout.fillWidth: true }
                Text { text: "X  "+surface.tr("Options")+"    B  "+surface.tr("Back"); color:"#a8acae";font.pixelSize:18 }
            }
        }
    }
    Text { anchors.centerIn: parent; visible: appState.media.loading||false; text: surface.tr("Loading…"); color: "#f1eee7"; font.pixelSize: 28 }
}
