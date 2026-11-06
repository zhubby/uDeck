// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: window
    width: 1280; height: 720
    minimumWidth: 800; minimumHeight: 500
    visible: true
    visibility: windowed ? Window.Windowed : Window.FullScreen
    color: "#171b1d"
    title: "uDeck " + state.app.charAt(0).toUpperCase() + state.app.slice(1)
    property var state: JSON.parse(controller.snapshotJson)
    property var cardModel: state.cards
    property string cardsStamp: JSON.stringify(cardModel)
    property bool allowClose: false
    property bool videoFull: state.app === "video" && state.page === "player"
    property color ink: "#f1eee7"
    property color muted: "#a8acae"
    property color accent: "#edb866"
    function tr(source) { return controller.translate(source, state.language) }
    function time(value) { const s=Math.max(0,Math.floor(value||0));return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0") }
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
            const stamp=JSON.stringify(window.state.cards)
            if(stamp!==window.cardsStamp) {window.cardsStamp=stamp;window.cardModel=window.state.cards}
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
            color: "#202628"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 18
                Text { text: "uD"; color: window.accent; font.pixelSize: 28; font.bold: true }
                Text { text: window.tr(window.state.app.charAt(0).toUpperCase()+window.state.app.slice(1)); color: window.ink; font.pixelSize: 28 }
                Item { Layout.fillWidth: true }
                Text { text: window.state.scanning ? window.tr("Scanning…") : window.state.app === "browser" ? window.tr(({navigation:"Link navigation",reading:"Reading",pointer:"Virtual pointer",text:"Text input"})[window.state.webMode]||"Link navigation") : window.state.count+" "+window.tr("items"); color: window.muted; font.pixelSize: 18 }
                SuiteButton { text: "Y  "+window.tr("Settings"); implicitHeight: 42; onActivated: controller.dispatch("quick-settings") }
            }
        }
        Rectangle {
            visible: !window.videoFull && window.state.page !== "document" && window.state.page !== "game-running"
            Layout.fillWidth: true; Layout.preferredHeight: 54
            color: "#1d2224"
            ListView {
                id: tabbar
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28
                orientation: ListView.Horizontal; clip: true; spacing: 14
                model: window.state.tabs; currentIndex: window.state.tab
                onCurrentIndexChanged: positionViewAtIndex(currentIndex,ListView.Contain)
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    width: Math.min(280, tabLabel.implicitWidth+36); height: 54
                    color: index===window.state.tab ? "#383025" : "transparent"
                    Text { id: tabLabel; anchors.centerIn: parent; width: Math.min(244,implicitWidth); text: parent.modelData; color: index===window.state.tab ? window.ink : window.muted; font.pixelSize: 22; elide: Text.ElideRight }
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
                    Text { Layout.fillWidth: true; text: window.state.folder || window.state.filter || window.state.tabs[window.state.tab] || ""; color: window.ink; font.pixelSize: 30; elide: Text.ElideMiddle }
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
                        ScrollBar.vertical: ScrollBar { }
                        delegate: Rectangle {
                            id: card
                            required property var modelData
                            required property int index
                            width: cards.cellWidth-12; height: cards.cellHeight-12
                            radius: 10
                            color: modelData.id===window.state.selected ? "#393227" : "#252b2d"
                            border.width: modelData.id===window.state.selected ? 3 : 1
                            border.color: modelData.id===window.state.selected ? window.accent : "#42494a"
                            Artwork { id: art; x: 10; y: 10; width: cards.listMode?54:parent.width-20; height: cards.listMode?54:parent.height-80; cover: card.modelData.cover||""; kind: card.modelData.kind==="folder"?"reader":window.state.app }
                            Column {
                                x: cards.listMode ? 80 : 12; y: cards.listMode ? 12 : art.y+art.height+8
                                width: parent.width-x-12; spacing: 4
                                Text { width: parent.width; text: (card.modelData.id===window.state.current.id ? "▶  " : "")+card.modelData.title; color: window.ink; font.pixelSize: cards.listMode?22:20; elide: Text.ElideRight }
                                Text { width: parent.width; text: card.modelData.subtitle||""; color: window.muted; font.pixelSize: 17; elide: Text.ElideRight }
                            }
                            MouseArea { anchors.fill: parent; onClicked: {controller.select(card.modelData.id);controller.dispatch("accept")} }
                        }
                        Item {
                            anchors.fill: parent; visible: window.cardModel.length===0
                            Column {
                                anchors.centerIn: parent; width: Math.min(parent.width-36,540); spacing: 18
                                Text { width: parent.width; text: window.state.scanning?window.tr("Scanning…"):window.tr("Nothing here yet"); color: window.ink; font.pixelSize: 30; horizontalAlignment: Text.AlignHCenter }
                                Text { width: parent.width; text: window.tr("Choose a folder in Sources, or switch to another collection."); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 21; horizontalAlignment: Text.AlignHCenter }
                                SuiteButton { anchors.horizontalCenter: parent.horizontalCenter; text: "A  "+window.tr("Sources"); selected: true; onActivated: controller.command("sources") }
                            }
                        }
                    }
                }
                ColumnLayout {
                    visible: window.state.app==="music" || window.state.app==="games"
                    Layout.preferredWidth: window.width<1100?230:290; Layout.maximumWidth: window.width<1100?230:290; Layout.fillWidth: false; Layout.fillHeight: true; spacing: 16
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#464b49" }
                    Text { text: window.state.app==="music"?window.tr("Now playing"):window.tr("Selected game"); color: window.muted; font.pixelSize: 18 }
                    Artwork { Layout.fillWidth: true; Layout.preferredHeight: 170; cover: window.state.app==="music"?(window.state.current.cover||""):((window.cardModel.find(x=>x.id===window.state.selected)||{}).cover||""); kind: window.state.app }
                    Text { Layout.fillWidth: true; text: window.state.app==="music"?(window.state.current.title||window.tr("Choose a track")):((window.cardModel.find(x=>x.id===window.state.selected)||{}).title||""); wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: window.ink; font.pixelSize: 25 }
                    Text { visible: window.state.app==="music"; text: window.time((window.state.media||{}).position)+" / "+window.time((window.state.media||{}).duration); color: window.muted; font.pixelSize: 19 }
                    SuiteButton { visible: window.state.app==="music" && !!window.state.current.id; text: window.tr("Now playing"); onActivated: controller.command("now-playing") }
                    Item { Layout.fillHeight: true }
                    Text { Layout.fillWidth: true; text: window.state.app==="music"?window.tr("Playback continues while browsing."):window.tr("Ctrl+Alt+M opens the game menu."); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 18 }
                }
            }
            Loader {
                id: surface; anchors.fill: parent
                source: ["music","video"].indexOf(window.state.app)>=0?"MediaSurface.qml":window.state.app==="browser"?"BrowserSurface.qml":window.state.app==="reader"?"ReaderSurface.qml":"GameSurface.qml"
                onLoaded: item.host=window
                visible: ["library","album"].indexOf(window.state.page)<0
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 62
            visible: !window.videoFull
            color: "#1d2224"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 24
                Repeater {
                    model: [["A",window.tr("Open")],["B",window.tr("Back")],["X",window.tr("Actions")],["Y",window.tr("Settings")]]
                    delegate: Row {
                        required property var modelData
                        spacing: 7
                        Rectangle { width: 28; height: 28; radius: 14; color: parent.modelData[0]==="A"?window.accent:"transparent"; border.color: "#929694"; Text{anchors.centerIn:parent;text:parent.parent.modelData[0];font.pixelSize:18;color:parent.parent.modelData[0]==="A"?"#252019":window.ink} }
                        Text { text: parent.modelData[1]; color: window.muted; font.pixelSize: 19 }
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: window.state.page==="document"?window.tr("L / R  Page"):window.tr("L / R  Tabs"); color: window.muted; font.pixelSize: 18 }
            }
        }
    }
    Rectangle {
        visible: !!(window.state.error||window.state.saveError||window.state.notice||(window.state.sourceErrors||[]).length)
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 76
        width: Math.min(parent.width-60,1000); height: toast.implicitHeight+24; radius: 8
        color: window.state.error?"#542e2a":"#363027"; border.color: "#967c51"; z: 5
        Text { id: toast; anchors.fill: parent; anchors.margins: 12; text: window.state.error||window.state.saveError||window.state.notice||(window.state.sourceErrors||[]).join("\n"); wrapMode: Text.Wrap; color: window.ink; font.pixelSize: 20; maximumLineCount: 4; elide: Text.ElideRight }
    }
    Item {
        id: keys; anchors.fill: parent; focus: true
        Keys.onPressed: function(event) {
            const map={};map[Qt.Key_Up]="up";map[Qt.Key_Down]="down";map[Qt.Key_Left]="left";map[Qt.Key_Right]="right";map[Qt.Key_Return]="accept";map[Qt.Key_Enter]="accept";map[Qt.Key_Escape]="back";map[Qt.Key_PageUp]="previous-tab";map[Qt.Key_PageDown]="next-tab";map[Qt.Key_F2]="context";map[Qt.Key_F3]="quick-settings"
            if(map[event.key]) {controller.dispatch(map[event.key]);event.accepted=true}
        }
    }
    Rectangle {
        anchors.fill: parent; visible: !!window.state.menu.title; color: "#b5000000"; z: 10
        MouseArea { anchors.fill: parent }
        Rectangle {
            anchors.centerIn: parent; width: Math.min(parent.width-72,780)
            height: Math.min(parent.height-64,modalContents.implicitHeight+48)
            radius: 16; color: "#222729"; border.color: "#68675f"
            ColumnLayout {
                id: modalContents; anchors.fill: parent; anchors.margins: 24; spacing: 16
                Text { Layout.fillWidth: true; text: window.state.menu.title||""; font.pixelSize: 30; color: window.ink; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                Text { Layout.fillWidth: true; visible: !!window.state.menu.body; text: window.state.menu.body||""; font.pixelSize: 21; color: window.muted; wrapMode: Text.Wrap; maximumLineCount: 5; elide: Text.ElideRight }
                TextField {
                    id: draft; visible: !!window.state.menu.input; Layout.fillWidth: true
                    font.pixelSize: 23; color: window.ink; selectByMouse: true
                    background: Rectangle { color: "#161b1d"; radius: 8; border.width: 2; border.color: window.accent }
                    onTextEdited: controller.setDraft(text)
                    onAccepted: controller.submit(text)
                    Keys.onEscapePressed: controller.dispatch("back")
                }
                ListView {
                    id: options; Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.preferredHeight: contentHeight; Layout.minimumHeight: 0; clip: true; spacing: 5
                    model: window.state.menu.options||[]; currentIndex: window.state.menu.index||0
                    onCurrentIndexChanged: Qt.callLater(function(){options.positionViewAtIndex(options.currentIndex,ListView.Contain)})
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: options.width; height: Math.max(60,optionContents.implicitHeight+22); radius: 8
                        color: index===options.currentIndex?"#393227":"transparent"
                        border.width: 3; border.color: index===options.currentIndex?window.accent:"transparent"
                        opacity: modelData.disabled?0.45:1
                        Column {
                            id: optionContents; anchors.verticalCenter: parent.verticalCenter; x: 14; width: parent.width-28; spacing: 4
                            Text { width: parent.width; text: modelData.title; color: window.ink; wrapMode: Text.Wrap; font.pixelSize: 22 }
                            Text { width: parent.width; visible: !!modelData.subtitle; text: modelData.subtitle; color: window.muted; wrapMode: Text.Wrap; font.pixelSize: 17 }
                        }
                        MouseArea { anchors.fill: parent; enabled: !parent.modelData.disabled; onClicked: controller.choose(parent.index) }
                    }
                }
                Text { text: window.tr("A / Enter  Confirm    B / Esc  Back"); color: window.muted; font.pixelSize: 18 }
            }
        }
    }
    Component.onCompleted: Qt.callLater(focusInput)
}
