// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖视频控制器、共享主题、应用按钮和播放状态。
[OUTPUT]: 显示视频、字幕和居中的播放图标；报告窗口坐标中的指针活动。
[POS]: 视频应用的播放视图；页面过渡不计入指针活动。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
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

    component PlaybackButton: SuiteButton {
        id: playbackButton
        required property string symbolPath
        required property string command
        colors: surface.colors
        fontFamily: surface.host.fontFamily
        iconComponent: Shape {
            width: 24
            height: 24
            ShapePath {
                fillColor: surface.colors.text
                strokeColor: "transparent"
                PathSvg { path: playbackButton.symbolPath }
            }
        }
        onActivated: controller.command(command)
    }

    Rectangle { anchors.fill: parent; color: "black" }
    Loader {
        anchors.fill: parent; z: 1
        active: surface.visible
        onActiveChanged: if (!active) controller.pointerPressed(false)
        sourceComponent: Item {
            HoverHandler {
                property point previousScenePosition: Qt.point(-1, -1)
                onPointChanged: {
                    if (point.scenePosition.x !== previousScenePosition.x || point.scenePosition.y !== previousScenePosition.y) {
                        previousScenePosition = point.scenePosition
                        if (hovered) controller.pointerActivity()
                    }
                }
            }
            PointHandler {
                acceptedButtons: Qt.AllButtons
                onActiveChanged: controller.pointerPressed(active)
                onPointChanged: if (active) controller.pointerActivity()
            }
        }
    }
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
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(playbackControls.implicitHeight, playbackHints.implicitHeight)
                RowLayout {
                    id: playbackControls
                    anchors.centerIn: parent
                    spacing: 18
                    PlaybackButton {
                        text: surface.tr(msg.PREVIOUS_CHAPTER)
                        symbolPath: "M 4,4 H 7 V 20 H 4 Z M 20,4 L 8,12 L 20,20 Z"
                        selected: appState.control === 0
                        command: "previous"
                    }
                    PlaybackButton {
                        text: surface.tr(msg.SEEK_BACKWARD)
                        symbolPath: "M 12,5 L 2,12 L 12,19 Z M 22,5 L 12,12 L 22,19 Z"
                        selected: appState.control === 1
                        command: "seek-backward"
                    }
                    PlaybackButton {
                        text: surface.tr(appState.media.playing ? msg.PAUSE : msg.PLAY)
                        symbolPath: appState.media.playing
                            ? "M 6,4 H 10 V 20 H 6 Z M 14,4 H 18 V 20 H 14 Z"
                            : "M 7,4 L 20,12 L 7,20 Z"
                        selected: appState.control === 2
                        command: "play-pause"
                    }
                    PlaybackButton {
                        text: surface.tr(msg.SEEK_FORWARD)
                        symbolPath: "M 2,5 L 12,12 L 2,19 Z M 12,5 L 22,12 L 12,19 Z"
                        selected: appState.control === 3
                        command: "seek-forward"
                    }
                    PlaybackButton {
                        text: surface.tr(msg.NEXT_CHAPTER)
                        symbolPath: "M 4,4 L 16,12 L 4,20 Z M 17,4 H 20 V 20 H 17 Z"
                        selected: appState.control === 4
                        command: "next"
                    }
                }
                RowLayout {
                    id: playbackHints
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 18
                    Shared.InputPrompt { keys: ["gamecube_button_x"]; label: surface.tr(msg.OPTIONS); fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
                    Shared.InputPrompt { keys: ["gamecube_button_color_b"]; label: surface.tr(msg.BACK); fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
                }
            }
        }
    }
    Text { font.family: surface.host.fontFamily; anchors.centerIn: parent; visible: appState.media.loading||false; text: surface.tr(msg.LOADING); color: surface.colors.text; font.pixelSize: 28 }
}
