// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Layouts

Item {
    property var host
    property var appState:host?host.state:({current:{},gameChecks:{}})
    RowLayout {
        anchors.fill: parent; anchors.margins: 48; spacing: 40
        Artwork { Layout.preferredWidth: 300; Layout.preferredHeight: 330; cover: appState.current.cover||""; kind: "games" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 18
            Text { Layout.fillWidth:true;text:appState.current.title||"";color:"#f1eee7";font.pixelSize:36;wrapMode:Text.Wrap;maximumLineCount:3;elide:Text.ElideRight }
            Text { text:(appState.current.platform||"")+"  ·  "+(appState.gameChecks.core||"").split("/").pop();color:"#edb866";font.pixelSize:21 }
            Text { Layout.fillWidth:true;text:appState.current.path||"";color:"#a8acae";font.pixelSize:18;wrapMode:Text.WrapAnywhere;maximumLineCount:3;elide:Text.ElideMiddle }
            Text { Layout.fillWidth:true;text:(appState.gameChecks.errors||[]).join("\n");color:"#e3ac91";font.pixelSize:21;wrapMode:Text.Wrap }
            SuiteButton { text:host?host.tr("A  Start / Continue"):"";selected:true;disabled:appState.page==="game-running";onActivated:controller.dispatch("accept") }
            Text { Layout.fillWidth:true;text:appState.page==="game-running"?(host?host.tr("The emulator owns gameplay input. Ctrl+Alt+M opens the pause menu."):""):host?host.tr("Manual saves and the automatic resume point are kept separately."):"";color:"#a8acae";font.pixelSize:20;wrapMode:Text.Wrap }
        }
    }
}
