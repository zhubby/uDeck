// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Layouts
import "../../qml" as Shared

Item {
    id: surface
    required property var colors
    required property var host
    property var appState:host?host.state:({current:{},gameChecks:{}})
    RowLayout {
        anchors.fill: parent; anchors.margins: 48; spacing: 40
        Artwork { fontFamily: surface.host.fontFamily; colors: surface.colors; Layout.preferredWidth: 300; Layout.preferredHeight: 330; cover: appState.current.cover||""; kind: "games" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 18
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.current.title||"";color:surface.colors.text;font.pixelSize:36;wrapMode:Text.Wrap;maximumLineCount:3;elide:Text.ElideRight }
            Text { font.family: surface.host.fontFamily; text:(appState.current.platform||"")+"  ·  "+(appState.gameChecks.core||"").split("/").pop();color:surface.colors.accent;font.pixelSize:21 }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.current.path||"";color:surface.colors.muted;font.pixelSize:18;wrapMode:Text.WrapAnywhere;maximumLineCount:3;elide:Text.ElideMiddle }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:(appState.gameChecks.errors||[]).join("\n");color:surface.colors.error;font.pixelSize:21;wrapMode:Text.Wrap }
            SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; promptKeys: ["gamecube_button_color_a"]; text:host?host.tr(appState.gameBusy ? "Preparing game…" : "Start / Continue"):"";selected:true;disabled:appState.page==="game-running" || appState.gameBusy;onActivated:controller.dispatch("accept") }
            Shared.InputPrompt { visible: appState.page === "game-running"; keys: ["keyboard_ctrl", "+", "keyboard_alt", "+", "keyboard_m"]; label: host ? host.tr("Game menu") : ""; fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 18 }
            Text { font.family: surface.host.fontFamily; Layout.fillWidth:true;text:appState.page==="game-running"?(host?host.tr("The emulator owns gameplay input. Ctrl+Alt+M opens the pause menu."):""):host?host.tr(appState.gameChecks.savestate ? "Manual saves and the automatic resume point are kept separately." : "This core does not support save states"):"";color:surface.colors.muted;font.pixelSize:20;wrapMode:Text.Wrap }
        }
    }
}
