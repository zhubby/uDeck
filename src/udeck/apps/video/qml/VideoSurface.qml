// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "../../../qml" as Shared
import "../../common/qml"

Item {
    id: surface
    readonly property var msg: host ? host.msg : ({})
    required property var colors
    required property var host
    property var appState: host ? host.state : ({current:{},media:{}})
    function tr(s){return host?host.tr(s):s}
    Rectangle { anchors.fill: parent; color: "black" }
    VideoOutput {
        anchors.fill: parent
        visible: !controller.softwareRendering
        fillMode: VideoOutput.PreserveAspectFit
        Component.onCompleted: controller.setVideoSink(videoSink)
    }
    Image {
        anchors.fill:parent;visible:controller.softwareRendering
        source:visible&&appState.videoFrameRevision>0?"image://video/"+appState.videoFrameRevision:""
        fillMode:Image.PreserveAspectFit;cache:false
    }
    Rectangle {
        anchors.top: parent.top; width: parent.width; height: 100
        visible: appState.controlsVisible
        gradient: Gradient { GradientStop{position:0;color:"#c9000000"} GradientStop{position:1;color:"transparent"} }
        Text { font.family: surface.host.fontFamily; anchors.fill: parent; anchors.margins: 28; text: appState.current.title||""; color: surface.colors.text; font.pixelSize: 28; elide: Text.ElideRight }
    }
    Text { font.family: surface.host.fontFamily;
        anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom
        anchors.bottomMargin:appState.controlsVisible?170:46
        width:parent.width-100;text:appState.subtitleText||"";textFormat:Text.PlainText
        color:"white";style:Text.Outline;styleColor:"black";font.pixelSize:28
        horizontalAlignment:Text.AlignHCenter;wrapMode:Text.Wrap
    }
    Rectangle {
        anchors.bottom: parent.bottom; width: parent.width; height: 150
        visible: appState.controlsVisible
        color: surface.colors.videoControls
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 10
            RowLayout {
                Slider { palette: surface.colors.controls; Layout.fillWidth: true; from:0;to:appState.media.duration||1;value:appState.media.position||0;onMoved:controller.seek(value) }
                Text { font.family: surface.host.fontFamily; text:host?host.time(appState.media.position)+" / "+host.time(appState.media.duration):"";color:surface.colors.text;font.pixelSize:20 }
            }
            RowLayout {
                spacing: 18
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: surface.tr(msg.PREVIOUS_CHAPTER); selected: appState.control===0; onActivated: controller.command("previous") }
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: appState.media.playing?surface.tr(msg.PAUSE):surface.tr(msg.PLAY); selected: appState.control===1; onActivated: controller.command("play-pause") }
                SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: surface.tr(msg.NEXT_CHAPTER); selected: appState.control===2; onActivated: controller.command("next") }
                Item { Layout.fillWidth: true }
                Shared.InputPrompt { keys: ["gamecube_button_x"]; label: surface.tr(msg.OPTIONS); fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
                Shared.InputPrompt { keys: ["gamecube_button_color_b"]; label: surface.tr(msg.BACK); fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
            }
        }
    }
    Text { font.family: surface.host.fontFamily; anchors.centerIn: parent; visible: appState.media.loading||false; text: surface.tr(msg.LOADING); color: surface.colors.text; font.pixelSize: 28 }
}
