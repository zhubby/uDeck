// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../../qml" as Shared

Window {
    id: window
    width: 1280; height: 720
    minimumWidth: 800; minimumHeight: 500
    visible: true
    visibility: windowed ? Window.Windowed : Window.FullScreen
    color: window.colors.background
    title: "uDeck " + state.app.charAt(0).toUpperCase() + state.app.slice(1)
    property var state: JSON.parse(controller.snapshotJson)
    property alias colors: themeColors
    Shared.ThemePalette { id: themeColors; theme: window.state.theme; profile: "apps" }
    property alias fontFamily: interfaceFonts.family
    Shared.InterfaceFonts { id: interfaceFonts; language: window.state.language }
    property var cardModel: []
    property var tabModel: []
    property var menuModel: []
    property string cardsStamp: ""
    property string tabsStamp: ""
    property string menuStamp: ""
    property bool allowClose: false
    property bool videoFull: state.app === "video" && state.page === "player"
    property color ink: window.colors.text
    property color muted: window.colors.muted
    property color accent: window.colors.accent
    function tr(source) { return controller.translate(source, state.language) }
    function time(value) { const s=Math.max(0,Math.floor(value||0));return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0") }
    function syncModels() {
        const cards = JSON.stringify(state.cards)
        const tabs = JSON.stringify(state.tabs)
        const options = state.menu.options || []
        const menu = JSON.stringify(options)
        if (cards !== cardsStamp) { cardsStamp=cards; cardModel=state.cards }
        if (tabs !== tabsStamp) { tabsStamp=tabs; tabModel=state.tabs }
        if (menu !== menuStamp) { menuStamp=menu; menuModel=options }
    }
    function focusInput() {
        if (state.menu.input) {
            if (!draft.activeFocus) { draft.text = state.menu.draft; draft.forceActiveFocus(); draft.cursorPosition=draft.length }
        } else if (state.app === "browser" && state.webMode === "text" && !state.menu.title) {
            if (surface.item) surface.item.focusWeb()
        } else keys.forceActiveFocus()
    }
    Connections {
        target: controller
        function onChanged() {
            const previous=window.state.menu
            window.state=JSON.parse(controller.snapshotJson)
            window.syncModels()
            if (!window.state.menu.input || !previous.input || previous.title!==window.state.menu.title) Qt.callLater(window.focusInput)
        }
        function onClosed() { window.allowClose=true; window.close() }
    }
    onClosing: function(event) { event.accepted=allowClose; if(!allowClose) controller.requestClose() }
    onActiveChanged: if(active) Qt.callLater(focusInput)
    Shortcut { sequence: "Ctrl+L"; enabled: window.state.app === "browser"; onActivated: controller.command("address") }
    Shortcut { sequence: "Ctrl+T"; enabled: window.state.app === "browser"; onActivated: controller.command("new-tab") }
    Shortcut { sequence: "Escape"; enabled: window.state.app === "browser" && window.state.webMode === "text" && !window.state.menu.title; onActivated: controller.dispatch("back") }
    Shortcut { sequence: "Ctrl+Shift+M"; onActivated: controller.dispatch("context") }
    Shortcut { sequence: "Ctrl+,"; onActivated: controller.dispatch("quick-settings") }
    Shortcut { sequence: "Ctrl+Alt+M"; enabled: window.state.app === "games"; onActivated: controller.command("pause-game") }
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            visible: !window.videoFull
            Layout.fillWidth: true; Layout.preferredHeight: 66
            color: window.colors.header
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 18
                Text { font.family: window.fontFamily; text: "uD"; color: window.accent; font.pixelSize: 28; font.bold: true }
                Text { font.family: window.fontFamily; text: window.tr(window.state.app.charAt(0).toUpperCase()+window.state.app.slice(1)); color: window.ink; font.pixelSize: 28 }
                Item { Layout.fillWidth: true }
                Text { font.family: window.fontFamily; text: window.state.scanning ? window.tr("Scanning…") : window.state.app === "browser" ? window.tr(({navigation:"Link navigation",reading:"Reading",pointer:"Virtual pointer",text:"Text input"})[window.state.webMode]||"Link navigation") : window.state.count+" "+window.tr("items"); color: window.muted; font.pixelSize: 18 }
                SuiteButton { fontFamily: window.fontFamily; colors: window.colors; promptKeys: ["gamecube_button_y"]; text: window.tr("Settings"); implicitHeight: 42; onActivated: controller.dispatch("quick-settings") }
            }
        }
        Rectangle {
            visible: !window.videoFull && window.state.page !== "document" && window.state.page !== "game-running"
            Layout.fillWidth: true; Layout.preferredHeight: 54
            color: window.colors.footer
            ListView {
                id: tabbar
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28
                orientation: ListView.Horizontal; clip: true; spacing: 14
                model: window.tabModel; currentIndex: window.state.tab
                onCurrentIndexChanged: positionViewAtIndex(currentIndex,ListView.Contain)
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    width: Math.min(280, tabLabel.implicitWidth+36); height: 54
                    color: index===window.state.tab ? window.colors.selectedTab : "transparent"
                    Text { font.family: window.fontFamily; id: tabLabel; anchors.centerIn: parent; width: Math.min(244,implicitWidth); text: parent.modelData; color: index===window.state.tab ? window.ink : window.muted; font.pixelSize: 22; elide: Text.ElideRight }
                    Rectangle { anchors.bottom: parent.bottom; height: 3; width: parent.width; color: window.accent; visible: parent.index===window.state.tab }
                    MouseArea { anchors.fill: parent; onClicked: controller.setTab(parent.index) }
                }
            }
        }
        Item {
            id: content
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            RowLayout {
                anchors.fill: parent; anchors.margins: 28; spacing: 28
                visible: ["library","album"].indexOf(window.state.page)>=0 && window.state.app!=="browser"
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
                    Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.folder || window.state.filter || window.state.tabs[window.state.tab] || ""; color: window.ink; font.pixelSize: 30; elide: Text.ElideMiddle }
                    GridView {
                        id: cards
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        property bool listMode: window.state.page==="album" || (window.state.app==="music" && [1,2].indexOf(window.state.tab)>=0)
                        property int columns: listMode ? 1 : width<600 ? 2 : 3
                        cellWidth: Math.floor(width/columns)
                        cellHeight: listMode ? 78 : window.state.app==="reader" ? 190 : 238
                        model: window.cardModel
                        currentIndex: window.cardModel.findIndex(x=>x.id===window.state.selected)
                        onColumnsChanged: controller.setColumns(columns)
                        onCurrentIndexChanged: if(currentIndex>=0) Qt.callLater(function(){cards.positionViewAtIndex(cards.currentIndex,GridView.Contain)})
                        ScrollBar.vertical: ScrollBar { palette: window.colors.controls; }
                        delegate: Rectangle {
                            id: card
                            required property var modelData
                            required property int index
                            width: cards.cellWidth-12; height: cards.cellHeight-12
                            radius: 10
                            color: modelData.id===window.state.selected ? window.colors.selected : window.colors.panel
                            border.width: modelData.id===window.state.selected ? 3 : 1
                            border.color: modelData.id===window.state.selected ? window.accent : window.colors.border
                            Artwork { fontFamily: window.fontFamily; colors: window.colors; id: art; x: 10; y: 10; width: cards.listMode?54:parent.width-20; height: cards.listMode?54:parent.height-80; cover: card.modelData.cover||""; kind: card.modelData.kind==="folder"?"reader":window.state.app }
                            Column {
                                x: cards.listMode ? 80 : 12; y: cards.listMode ? 12 : art.y+art.height+8
                                width: parent.width-x-12; spacing: 4
                                Text { font.family: window.fontFamily; width: parent.width; text: (card.modelData.id===window.state.current.id ? "▶  " : "")+card.modelData.title; color: window.ink; font.pixelSize: cards.listMode?22:20; elide: Text.ElideRight }
                                Text { font.family: window.fontFamily; width: parent.width; text: card.modelData.subtitle||""; color: window.muted; font.pixelSize: 17; elide: Text.ElideRight }
                            }
                            MouseArea { anchors.fill: parent; onClicked: {controller.select(card.modelData.id);controller.dispatch("accept")} }
                        }
                        Item {
                            anchors.fill: parent; visible: window.cardModel.length===0
                            Column {
                                anchors.centerIn: parent; width: Math.min(parent.width-36,540); spacing: 18
                                Text { font.family: window.fontFamily; width: parent.width; text: window.state.scanning?window.tr("Scanning…"):window.tr("Nothing here yet"); color: window.ink; font.pixelSize: 30; horizontalAlignment: Text.AlignHCenter }
                                Text { font.family: window.fontFamily; width: parent.width; text: window.tr("Choose a folder in Sources, or switch to another collection."); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 21; horizontalAlignment: Text.AlignHCenter }
                                SuiteButton { fontFamily: window.fontFamily; colors: window.colors; anchors.horizontalCenter: parent.horizontalCenter; promptKeys: ["gamecube_button_color_a"]; text: window.tr("Sources"); selected: true; onActivated: controller.command("sources") }
                            }
                        }
                    }
                }
                ColumnLayout {
                    visible: window.state.app==="music" || window.state.app==="games"
                    Layout.preferredWidth: window.width<1100?230:290; Layout.maximumWidth: window.width<1100?230:290; Layout.fillWidth: false; Layout.fillHeight: true; spacing: 16
                    Rectangle { Layout.fillWidth: true; height: 1; color: window.colors.divider }
                    Text { font.family: window.fontFamily; text: window.state.app==="music"?window.tr("Now playing"):window.tr("Selected game"); color: window.muted; font.pixelSize: 18 }
                    Artwork { fontFamily: window.fontFamily; colors: window.colors; Layout.fillWidth: true; Layout.preferredHeight: 170; cover: window.state.app==="music"?(window.state.current.cover||""):((window.cardModel.find(x=>x.id===window.state.selected)||{}).cover||""); kind: window.state.app }
                    Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.app==="music"?(window.state.current.title||window.tr("Choose a track")):((window.cardModel.find(x=>x.id===window.state.selected)||{}).title||""); wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: window.ink; font.pixelSize: 25 }
                    Text { font.family: window.fontFamily; visible: window.state.app==="music"; text: window.time((window.state.media||{}).position)+" / "+window.time((window.state.media||{}).duration); color: window.muted; font.pixelSize: 19 }
                    SuiteButton { fontFamily: window.fontFamily; colors: window.colors; visible: window.state.app==="music" && !!window.state.current.id; text: window.tr("Now playing"); onActivated: controller.command("now-playing") }
                    Item { Layout.fillHeight: true }
                    Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.app==="music"?window.tr("Playback continues while browsing."):window.tr("Ctrl+Alt+M opens the game menu."); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 18 }
                }
            }
            Loader {
                id: surface; anchors.fill: parent
                objectName: "appSurface"
                Component.onCompleted: setSource(["music","video"].indexOf(window.state.app)>=0?"MediaSurface.qml":window.state.app==="browser"?"BrowserSurface.qml":window.state.app==="reader"?"ReaderSurface.qml":"GameSurface.qml", {host: window, colors: window.colors})
                visible: ["library","album"].indexOf(window.state.page)<0
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 62
            visible: !window.videoFull
            color: window.colors.footer
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 24
                Repeater {
                    model: [["gamecube_button_color_a",window.tr("Open")],["gamecube_button_color_b",window.tr("Back")],["gamecube_button_x",window.tr("Actions")],["gamecube_button_y",window.tr("Settings")]]
                    delegate: Shared.InputPrompt {
                        required property var modelData
                        keys: [modelData[0]]; label: modelData[1]
                        fontFamily: window.fontFamily; textColor: window.muted; fontSize: 19
                    }
                }
                Item { Layout.fillWidth: true }
                Shared.InputPrompt { keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"]; label: window.tr(window.state.page === "document" ? "Pages" : "Tabs"); fontFamily: window.fontFamily; textColor: window.muted; fontSize: 18 }
            }
        }
    }
    Rectangle {
        visible: !!(window.state.error||window.state.saveError||window.state.notice||(window.state.sourceErrors||[]).length)
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 76
        width: Math.min(parent.width-60,1000); height: toast.implicitHeight+24; radius: 8
        color: window.state.error?window.colors.errorSurface:window.colors.toast; border.color: window.colors.toastBorder; z: 5
        Text { font.family: window.fontFamily; id: toast; anchors.fill: parent; anchors.margins: 12; text: window.state.error||window.state.saveError||window.state.notice||(window.state.sourceErrors||[]).join("\n"); wrapMode: Text.Wrap; color: window.state.error && window.colors.dark ? window.colors.error : window.ink; font.pixelSize: 20; maximumLineCount: 4; elide: Text.ElideRight }
    }
    Item {
        id: keys; anchors.fill: parent; focus: true
        Keys.onPressed: function(event) {
            const map={};map[Qt.Key_Up]="up";map[Qt.Key_Down]="down";map[Qt.Key_Left]="left";map[Qt.Key_Right]="right";map[Qt.Key_Return]="accept";map[Qt.Key_Enter]="accept";map[Qt.Key_Escape]="back";map[Qt.Key_PageUp]="previous-tab";map[Qt.Key_PageDown]="next-tab";map[Qt.Key_F2]="context";map[Qt.Key_F3]="quick-settings"
            if(map[event.key]) {controller.dispatch(map[event.key]);event.accepted=true}
        }
    }
    Rectangle {
        anchors.fill: parent; visible: !!window.state.menu.title; color: window.colors.scrim; z: 10
        MouseArea { anchors.fill: parent }
        Rectangle {
            anchors.centerIn: parent; width: Math.min(parent.width-72,780)
            height: Math.min(parent.height-64,modalContents.implicitHeight+48)
            radius: 16; color: window.colors.dialog; border.color: window.colors.dialogBorder
            ColumnLayout {
                id: modalContents; anchors.fill: parent; anchors.margins: 24; spacing: 16
                Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.menu.title||""; font.pixelSize: 30; color: window.ink; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                Text { font.family: window.fontFamily; Layout.fillWidth: true; visible: !!window.state.menu.body; text: window.state.menu.body||""; font.pixelSize: 21; color: window.muted; wrapMode: Text.Wrap; maximumLineCount: 5; elide: Text.ElideRight }
                TextField { font.family: window.fontFamily; palette: window.colors.controls;
                    id: draft; visible: !!window.state.menu.input; Layout.fillWidth: true
                    font.pixelSize: 23; color: window.ink; selectByMouse: true
                    background: Rectangle { color: window.colors.input; radius: 8; border.width: 2; border.color: window.accent }
                    onTextEdited: controller.setDraft(text)
                    onAccepted: controller.submit(text)
                    Keys.onEscapePressed: controller.dispatch("back")
                }
                ListView {
                    id: options; objectName: "menuList"; Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.preferredHeight: contentHeight; Layout.minimumHeight: 0; clip: true; spacing: 5
                    model: window.menuModel; currentIndex: window.state.menu.index||0
                    onCurrentIndexChanged: Qt.callLater(function(){options.positionViewAtIndex(options.currentIndex,ListView.Contain)})
                    ScrollBar.vertical: ScrollBar { palette: window.colors.controls;}
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: options.width; height: Math.max(60,optionContents.implicitHeight+22); radius: 8
                        color: index===options.currentIndex?window.colors.selected:"transparent"
                        border.width: 3; border.color: index===options.currentIndex?window.accent:"transparent"
                        opacity: modelData.disabled?0.45:1
                        Column {
                            id: optionContents; anchors.verticalCenter: parent.verticalCenter; x: 14; width: parent.width-28; spacing: 4
                            Text { font.family: window.fontFamily; width: parent.width; text: modelData.title; color: window.ink; wrapMode: Text.Wrap; font.pixelSize: 22 }
                            Text { font.family: window.fontFamily; width: parent.width; visible: !!modelData.subtitle; text: modelData.subtitle; color: window.muted; wrapMode: Text.Wrap; font.pixelSize: 17 }
                        }
                        MouseArea { anchors.fill: parent; enabled: !parent.modelData.disabled; onClicked: controller.choose(parent.index) }
                    }
                }
                Shared.InputHints {
                    Layout.fillWidth: true
                    fontFamily: window.fontFamily; textColor: window.muted; fontSize: 18
                    hints: [{keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: window.tr("Confirm")},
                            {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: window.tr("Back")}]
                }
            }
        }
    }
    Component.onCompleted: { syncModels(); Qt.callLater(focusInput) }
}
