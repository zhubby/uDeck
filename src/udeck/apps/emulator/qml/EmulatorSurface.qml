// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Layouts
import "../../../qml" as Shared
import "../../common/qml"

Item {
    id: surface
    readonly property var msg: host ? host.msg : ({})
    required property var colors
    required property var host
    property var appState:host?host.state:({current:{},gameChecks:{}})
    RowLayout {
        anchors.fill: parent; anchors.margins: 48; spacing: 40
        Artwork { fontFamily: surface.host.fontFamily; colors: surface.colors; Layout.preferredWidth: 300; Layout.preferredHeight: 330; cover: appState.current.cover||""; kind: "emulator" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 18
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.current.title||"";color:surface.colors.text;font.pixelSize:36;wrapMode:Text.Wrap;maximumLineCount:3;elide:Text.ElideRight }
            Text { font.family: surface.host.fontFamily; text:(appState.current.platform||"")+"  ·  "+(appState.gameChecks.core||"").split("/").pop();color:surface.colors.accent;font.pixelSize:21 }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.current.path||"";color:surface.colors.muted;font.pixelSize:18;wrapMode:Text.WrapAnywhere;maximumLineCount:3;elide:Text.ElideMiddle }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:(appState.gameChecks.errors||[]).join("\n");color:surface.colors.error;font.pixelSize:21;wrapMode:Text.Wrap }
            SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; promptKeys: ["gamecube_button_color_a"]; text:host?host.tr(appState.gameBusy ? msg.PREPARING_GAME : msg.START_CONTINUE):"";selected:true;disabled:appState.page==="game-running" || appState.gameBusy;onActivated:controller.dispatch("accept") }
            Shared.InputPrompt { visible: appState.page === "game-running"; keys: ["keyboard_ctrl", "+", "keyboard_alt", "+", "keyboard_m"]; label: host ? host.tr(msg.GAME_MENU) : ""; fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.page==="game-running"?(host?host.tr(msg.THE_EMULATOR_OWNS_GAMEPLAY_INPUT_CTRL_ALT_M_OPENS_THE_PAUSE_MENU):""):host?host.tr(appState.gameChecks.savestate ? msg.MANUAL_SAVES_AND_THE_AUTOMATIC_RESUME_POINT_ARE_KEPT_SEPARATELY : msg.THIS_CORE_DOES_NOT_SUPPORT_SAVE_STATES):"";color:surface.colors.muted;font.pixelSize:20;wrapMode:Text.Wrap }
        }
    }
}
