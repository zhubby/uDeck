// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖应用控制器、增量库模型、共享短过渡与圆点组件。
[OUTPUT]: 提供交接后的窗口、连续切页、封面和非交互指针层。
[POS]: 五类应用的窗口外壳，内容视图由各应用加载。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../../../qml" as Shared

Window {
    id: window
    readonly property var msg: controller.messageKeys
    width: 1280; height: 720
    minimumWidth: 800; minimumHeight: 500
    property bool presentationReady: true
    visibility: presentationReady ? (windowed ? Window.Windowed : Window.FullScreen) : Window.Hidden
    color: window.colors.background
    title: "uDeck " + appName
    readonly property string appName: window.tr(({music: msg.MUSIC, video: msg.VIDEO, browser: msg.BROWSER,
                                                 reader: msg.READER, emulator: msg.EMULATOR})[state.app])
    property var state: JSON.parse(controller.viewSnapshotJson)
    property alias colors: themeColors
    Shared.ThemePalette { id: themeColors; theme: window.state.theme; profile: "apps" }
    property alias fontFamily: interfaceFonts.family
    Shared.InterfaceFonts { id: interfaceFonts; language: window.state.language }
    property var tabModel: []
    property var menuModel: []
    property var gameInfoModel: []
    property string tabsStamp: ""
    property string menuStamp: ""
    property string gameInfoStamp: ""
    property string focusedInputId: ""
    property var retainedMenu: ({})
    property string renderedPage: ""
    property int renderedTab: -1
    property string renderedMenuId: ""
    property string renderedNavigation: ""
    Shared.MotionTimings { id: motion; reducedMotion: controller.reducedMotion }
    Shared.SelectionViewport {
        id: cardViewport; objectName: "appCardViewport"
        view: cards; active: cards.visible && window.active && !window.state.menu.title
        reducedMotion: controller.reducedMotion
    }
    Shared.SelectionViewport {
        id: tabViewport; objectName: "appTabViewport"
        view: tabbar; active: tabbar.visible && window.active && !window.state.menu.title
        reducedMotion: controller.reducedMotion
    }
    Shared.SelectionViewport {
        id: menuViewport; objectName: "appMenuViewport"
        view: options; active: modal.shown && window.active
        reducedMotion: controller.reducedMotion
    }
    property bool allowClose: false
    property QtObject pointerCursor: null
    property bool videoFull: state.app === "video" && state.page === "player"
    property color ink: window.colors.text
    property color muted: window.colors.muted
    property color accent: window.colors.accent
    function tr(source) { return controller.translate(source, state.language) }
    function time(value) { const s=Math.max(0,Math.floor(value||0));return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0") }
    function syncModels() {
        if (state.menu.title) retainedMenu = state.menu
        const navigation = [state.page, state.tab, state.selected].join(":")
        if (modal.closing && renderedNavigation !== navigation) modal.finish()
        renderedNavigation = navigation
        if (renderedPage && (renderedPage !== state.page || renderedTab !== state.tab)) {
            const order = {library: 0, album: 1, "game-details": 1, document: 2, player: 2, "game-running": 2}
            const direction = renderedPage === state.page ? Math.sign(state.tab - renderedTab)
                : Math.sign((order[state.page] || 0) - (order[renderedPage] || 0))
            content.replay(direction || 1)
        }
        renderedPage = state.page; renderedTab = state.tab
        const menuId = state.menu.id || ""
        if (menuId && renderedMenuId && menuId !== renderedMenuId && modal.opacity > 0.99)
            menuContent.replay(Number(menuId) >= Number(renderedMenuId) ? 1 : -1)
        renderedMenuId = menuId
        const tabs = JSON.stringify(state.tabs)
        const options = (state.menu.title ? state.menu : retainedMenu).options || []
        const menu = JSON.stringify(options)
        const gameInfo = JSON.stringify(state.selectedGameInfo || [])
        if (tabs !== tabsStamp) { tabsStamp=tabs; tabModel=state.tabs }
        if (menu !== menuStamp) { menuStamp=menu; menuModel=options }
        if (gameInfo !== gameInfoStamp) { gameInfoStamp=gameInfo; gameInfoModel=state.selectedGameInfo || [] }
        ensureSurface()
    }
    function ensureSurface() {
        // Bind the video sink before playback can start.
        if (surface.source.toString() === "" && (state.app === "browser" || state.app === "video" || ["library", "album"].indexOf(state.page) < 0))
            surface.setSource("../../" + state.app + "/qml/" + ({music:"Music", video:"Video", browser:"Browser", reader:"Reader", emulator:"Emulator"})[state.app] + "Surface.qml", {host: window, colors: window.colors})
    }
    function focusInput() {
        if (state.menu.input) {
            if (focusedInputId !== state.menu.id) {
                focusedInputId = state.menu.id
                draft.text = state.menu.draft
                draft.cursorPosition = draft.length
            }
            draft.forceActiveFocus()
        } else {
            focusedInputId = ""
            if (state.app === "browser" && state.webMode === "text" && !state.menu.title) {
                if (surface.item) surface.item.focusWeb()
            } else keys.forceActiveFocus()
        }
    }
    Connections {
        target: controller
        function onChanged() {
            const previous=window.state.menu
            window.state=JSON.parse(controller.viewSnapshotJson)
            window.syncModels()
            if (!window.state.menu.input || !previous.input || previous.id!==window.state.menu.id) Qt.callLater(window.focusInput)
        }
        function onClosed() { window.allowClose=true; window.close() }
    }
    onClosing: function(event) { event.accepted=allowClose; if(!allowClose) controller.requestClose() }
    onActiveChanged: if(active) Qt.callLater(focusInput)
    Shortcut { sequence: "Ctrl+L"; autoRepeat: false; enabled: window.state.app === "browser"; onActivated: { controller.command("address"); Qt.callLater(window.focusInput) } }
    Shortcut { sequence: "Ctrl+T"; autoRepeat: false; enabled: window.state.app === "browser"; onActivated: controller.command("new-tab") }
    Shortcut { sequence: "Escape"; autoRepeat: false; enabled: window.state.app === "browser" && window.state.webMode === "text" && !window.state.menu.title; onActivated: controller.dispatch("back") }
    Shortcut { sequence: "Ctrl+Shift+M"; autoRepeat: false; onActivated: controller.dispatch("context") }
    Shortcut { sequence: "Ctrl+,"; autoRepeat: false; onActivated: controller.dispatch("quick-settings") }
    Shortcut { sequence: "Ctrl+Alt+M"; autoRepeat: false; enabled: window.state.app === "emulator"; onActivated: controller.command("pause-game") }
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            visible: !window.videoFull
            Layout.fillWidth: true; Layout.preferredHeight: 66
            color: window.colors.header
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 18
                Shared.BrandLogo { colors: window.colors; Layout.preferredWidth: 34; Layout.preferredHeight: 34 }
                Text { font.family: window.fontFamily; text: window.appName; color: window.ink; font.pixelSize: 28 }
                Item { Layout.fillWidth: true }
                Text { font.family: window.fontFamily; text: window.state.scanning ? window.tr(msg.SCANNING) : window.state.app === "browser" ? window.tr(({navigation:msg.LINK_NAVIGATION,reading:msg.READING,pointer:msg.VIRTUAL_POINTER,text:msg.TEXT_INPUT})[window.state.webMode]||msg.LINK_NAVIGATION) : window.state.app === "emulator" ? window.state.countLabel : window.state.count+" "+window.tr(msg.ITEMS); color: window.muted; font.pixelSize: 18 }
                SuiteButton { fontFamily: window.fontFamily; colors: window.colors; promptKeys: ["gamecube_button_y"]; text: window.tr(msg.SETTINGS); implicitHeight: 42; onActivated: controller.dispatch("quick-settings") }
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
                highlightFollowsCurrentItem: false
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
        Shared.MotionItem {
            id: content
            objectName: "appPageContent"
            reducedMotion: controller.reducedMotion
            fadeEnabled: false
            enterX: 6; enterDuration: motion.page
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            RowLayout {
                anchors.fill: parent; anchors.margins: 28; spacing: 28
                visible: ["library","album"].indexOf(window.state.page)>=0 && window.state.app!=="browser"
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
                    Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.app === "emulator" ? (window.state.platformTitle || window.state.tabs[window.state.tab]) + (window.state.filter ? " · " + window.state.filter : "") : window.state.folder || window.state.filter || window.state.tabs[window.state.tab] || ""; color: window.ink; font.pixelSize: 30; elide: Text.ElideMiddle }
                    GridView {
                        id: cards
                        objectName: "appCards"
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        property bool listMode: window.state.page==="album" || (window.state.app==="music" && [1,2].indexOf(window.state.tab)>=0)
                        property int columns: listMode ? 1 : window.state.platformsView ? 5 : width<600 ? 2 : 3
                        // Reserve one font line per label, independent of title length.
                        FontMetrics { id: cardTitleMetrics; font.family: window.fontFamily; font.pixelSize: cards.listMode ? 22 : 20 }
                        FontMetrics { id: cardSubtitleMetrics; font.family: window.fontFamily; font.pixelSize: 17 }
                        cellWidth: Math.floor(width/columns)
                        cellHeight: listMode ? 78 : window.state.platformsView ? 208 : window.state.app==="reader" ? 190 : 238
                        model: controller.cardModel
                        currentIndex: controller.selectedIndex
                        highlightFollowsCurrentItem: false
                        onColumnsChanged: controller.setColumns(columns)
                        ScrollBar.vertical: ScrollBar { palette: window.colors.controls; }
                        Shared.FocusFrame {
                            objectName: "appCardFocus"; parent: cards.contentItem
                            target: cards.currentItem
                            active: cards.visible && !window.state.menu.title
                            accent: window.accent; reducedMotion: controller.reducedMotion
                        }
                        delegate: Rectangle {
                            id: card
                            required property var entry
                            readonly property var modelData: entry
                            required property int index
                            width: cards.cellWidth-12; height: cards.cellHeight-12
                            radius: 10
                            color: modelData.id===window.state.selected ? window.colors.selected : window.colors.panel
                            border.width: 1; border.color: window.colors.border
                            Artwork { objectName: "cardArtwork"; fontFamily: window.fontFamily; colors: window.colors; id: art; x: 10; y: 10; width: cards.listMode?54:parent.width-20; height: cards.listMode?54:parent.height-(window.state.app==="emulator"?cardTitleMetrics.height+cardSubtitleMetrics.height+32:80); identity: card.modelData.gameId || card.modelData.id; cover: card.modelData.cover||""; fallbackIcon: window.state.app === "emulator" ? controller.platformIcon(card.modelData.platform || "") : ""; kind: card.modelData.kind==="folder"?"reader":window.state.app; iconOnly: card.modelData.kind === "platform" || card.modelData.kind === "playlist" }
                            Column {
                                x: cards.listMode ? 80 : 12; y: cards.listMode ? 12 : art.y+art.height+8
                                width: parent.width-x-12; spacing: 4
                                ScrollingTitle {
                                    objectName: "cardTitleViewport"
                                    width: parent.width; height: cardTitleMetrics.height
                                    fontFamily: window.fontFamily; pixelSize: cards.listMode ? 22 : 20
                                    text: ((card.modelData.gameId||card.modelData.id)===window.state.current.id ? "▶  " : "")+card.modelData.title
                                    textColor: window.ink
                                    resetKey: card.modelData.id
                                    reducedMotion: controller.reducedMotion
                                    selected: card.modelData.id === window.state.selected
                                    active: cards.visible && window.active && !window.state.menu.title
                                }
                                Text { font.family: window.fontFamily; width: parent.width; height: cardSubtitleMetrics.height; text: card.modelData.subtitle||""; color: window.muted; font.pixelSize: 17; elide: Text.ElideRight }
                            }
                            MouseArea { anchors.fill: parent; onClicked: {controller.select(card.modelData.id);controller.dispatch("accept")} }
                        }
                        Item {
                            anchors.fill: parent; visible: window.state.count===0
                            Column {
                                anchors.centerIn: parent; width: Math.min(parent.width-36,540); spacing: 18
                                Text { font.family: window.fontFamily; width: parent.width; text: window.state.scanning?window.tr(msg.SCANNING):window.tr(msg.NOTHING_HERE_YET); color: window.ink; font.pixelSize: 30; horizontalAlignment: Text.AlignHCenter }
                                Text { font.family: window.fontFamily; width: parent.width; text: window.state.app === "emulator" ? window.state.emptyHint : window.tr(msg.CHOOSE_A_FOLDER_IN_SOURCES_OR_SWITCH_TO_ANOTHER_COLLECTION); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 21; horizontalAlignment: Text.AlignHCenter }
                                SuiteButton { fontFamily: window.fontFamily; colors: window.colors; anchors.horizontalCenter: parent.horizontalCenter; promptKeys: ["gamecube_button_color_a"]; text: window.tr(window.state.app === "emulator" ? (window.state.filter ? msg.CLEAR_SEARCH : msg.SETTINGS) : msg.SOURCES); selected: true; onActivated: window.state.app === "emulator" ? controller.dispatch("accept") : controller.command("sources") }
                            }
                        }
                    }
                }
                ColumnLayout {
                    id: selectedGamePanel
                    objectName: "selectedGamePanel"
                    visible: window.state.app==="music" || (window.state.app==="emulator" && !window.state.platformsView)
                    Layout.preferredWidth: window.width<1100?230:290; Layout.maximumWidth: window.width<1100?230:290; Layout.fillWidth: false; Layout.fillHeight: true; spacing: 16
                    Rectangle { Layout.fillWidth: true; height: 1; color: window.colors.divider }
                    Text { font.family: window.fontFamily; text: window.state.app==="music"?window.tr(msg.NOW_PLAYING):window.tr(msg.SELECTED_GAME); color: window.muted; font.pixelSize: 18 }
                    Flickable {
                        id: selectedGameBody
                        objectName: "selectedGameBody"
                        visible: window.state.app === "emulator"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentHeight: selectedGameContent.implicitHeight
                        interactive: contentHeight > height
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        ScrollBar.vertical: ScrollBar { id: gameInfoScroll; policy: ScrollBar.AsNeeded }
                        WheelHandler {
                            enabled: selectedGameBody.interactive
                            target: null
                            onWheel: function(event) {
                                const delta = event.pixelDelta.y || event.angleDelta.y / 120 * 48
                                if (!delta) { event.accepted = false; return }
                                selectedGameBody.cancelFlick()
                                const end = Math.max(0, selectedGameBody.contentHeight - selectedGameBody.height)
                                selectedGameBody.contentY = Math.max(0, Math.min(end, selectedGameBody.contentY - delta))
                                event.accepted = true
                            }
                        }
                        Connections {
                            target: controller
                            function onSelectionChanged() { selectedGameBody.contentY = 0 }
                        }
                        ColumnLayout {
                            id: selectedGameContent
                            width: selectedGameBody.width - (selectedGameBody.interactive ? gameInfoScroll.width + 8 : 0)
                            spacing: 12
                            Artwork {
                                fontFamily: window.fontFamily; colors: window.colors
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(80, Math.min(170, selectedGameBody.height - 180))
                                identity: controller.selectedItem.gameId || controller.selectedItem.id || ""
                                cover: controller.selectedItem.cover || ""
                                fallbackIcon: window.state.app === "emulator" ? controller.platformIcon(controller.selectedItem.platform || "") : ""
                                kind: "emulator"
                            }
                            ScrollingTitle {
                                objectName: "selectedGameTitle"
                                Layout.fillWidth: true
                                fontFamily: window.fontFamily; pixelSize: 25; textColor: window.ink
                                text: controller.selectedItem.title || ""
                                resetKey: controller.selectedItem.id || ""
                                reducedMotion: controller.reducedMotion
                                active: false
                            }
                            ColumnLayout {
                                objectName: "selectedGameInfo"
                                Layout.fillWidth: true
                                spacing: 8
                                Repeater {
                                    model: window.gameInfoModel
                                    RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        spacing: 12
                                        Text {
                                            objectName: "gameInfoLabel_" + modelData.key
                                            Layout.preferredWidth: 88
                                            font.family: window.fontFamily; font.pixelSize: 17
                                            text: modelData.label; color: window.muted
                                            textFormat: Text.PlainText
                                        }
                                        ScrollingTitle {
                                            objectName: "gameInfoValue_" + modelData.key
                                            Layout.fillWidth: true
                                            fontFamily: window.fontFamily; pixelSize: 17; textColor: window.ink
                                            text: modelData.value
                                            resetKey: controller.selectedItem.id || ""
                                            reducedMotion: controller.reducedMotion
                                            active: false
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Artwork { visible: window.state.app === "music"; fontFamily: window.fontFamily; colors: window.colors; Layout.fillWidth: true; Layout.preferredHeight: 170; identity: window.state.current.id || ""; cover: window.state.current.cover || ""; kind: window.state.app }
                    Text { font.family: window.fontFamily; visible: window.state.app==="music"; Layout.fillWidth: true; text: window.state.current.title||window.tr(msg.CHOOSE_A_TRACK); wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: window.ink; font.pixelSize: 25 }
                    Text { font.family: window.fontFamily; visible: window.state.app==="music"; text: window.time((window.state.media||{}).position)+" / "+window.time((window.state.media||{}).duration); color: window.muted; font.pixelSize: 19 }
                    SuiteButton { fontFamily: window.fontFamily; colors: window.colors; visible: window.state.app==="music" && !!window.state.current.id; text: window.tr(msg.NOW_PLAYING); onActivated: controller.command("now-playing") }
                    Item { visible: window.state.app === "music"; Layout.fillHeight: true }
                    Text { font.family: window.fontFamily; Layout.fillWidth: true; text: window.state.app==="music"?window.tr(msg.PLAYBACK_CONTINUES_WHILE_BROWSING):window.tr(msg.CTRL_ALT_M_OPENS_THE_GAME_MENU); wrapMode: Text.Wrap; color: window.muted; font.pixelSize: 18 }
                }
            }
            Loader {
                id: surface; anchors.fill: parent
                objectName: "appSurface"
                asynchronous: window.state.app !== "browser" && window.state.app !== "video"
                onLoaded: Qt.callLater(window.focusInput)
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
                    model: [["gamecube_button_color_a",window.tr(msg.OPEN)],["gamecube_button_color_b",window.tr(msg.BACK)],["gamecube_button_x",window.tr(msg.ACTIONS)],["gamecube_button_y",window.tr(msg.SETTINGS)]]
                    delegate: Shared.InputPrompt {
                        required property var modelData
                        keys: [modelData[0]]; label: modelData[1]
                        fontFamily: window.fontFamily; textColor: window.muted; fontSize: 19
                    }
                }
                Item { Layout.fillWidth: true }
                Shared.InputPrompt { keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"]; label: window.tr(window.state.page === "document" ? msg.PAGES : msg.TABS); fontFamily: window.fontFamily; textColor: window.muted; fontSize: 18 }
            }
        }
    }
    Shared.ToastNotice {
        objectName: "appToast"
        colors: window.colors; fontFamily: window.fontFamily
        reducedMotion: controller.reducedMotion
        message: window.state.error||window.state.saveError||window.state.notice||(window.state.sourceErrors||[]).join("\n")
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 76
        maximumWidth: Math.min(parent.width-60,1000); fontSize: 20; z: 5
        surfaceColor: window.state.error?window.colors.errorSurface:window.colors.toast
        textColor: window.state.error && window.colors.dark ? window.colors.error : window.ink
    }
    Item {
        id: keys; objectName: "appKeys"; anchors.fill: parent; focus: true
        Keys.onPressed: function(event) {
            if (modal.closing) modal.finish()
            const map={};map[Qt.Key_Up]="up";map[Qt.Key_Down]="down";map[Qt.Key_Left]="left";map[Qt.Key_Right]="right";map[Qt.Key_Return]="accept";map[Qt.Key_Enter]="accept";map[Qt.Key_Escape]="back";map[Qt.Key_PageUp]="previous-tab";map[Qt.Key_PageDown]="next-tab";map[Qt.Key_F2]="context";map[Qt.Key_F3]="quick-settings"
            if(map[event.key]) {
                if (!event.isAutoRepeat || ["up", "down", "left", "right"].indexOf(map[event.key]) >= 0)
                    controller.dispatch(map[event.key])
                event.accepted=true
            }
        }
    }
    Shared.MotionItem {
        id: modal; objectName: "applicationModal"
        property var menu: window.state.menu.title ? window.state.menu : window.retainedMenu
        anchors.fill: parent; shown: !!window.state.menu.title; z: 10
        reducedMotion: controller.reducedMotion
        enterDuration: motion.enter; leaveDuration: motion.leave
        onHidden: if (!window.state.menu.title) window.retainedMenu = ({})
        Rectangle { anchors.fill: parent; color: window.colors.scrim }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(wheel) { wheel.accepted = true } }
        Rectangle {
            id: menuPanel; objectName: "appMenuPanel"
            enabled: modal.shown
            transform: Translate { y: 8 * (1 - modal.opacity) }
            anchors.centerIn: parent; width: Math.min(parent.width-72,780)
            height: Math.min(parent.height-64,modalContents.implicitHeight+48)
            radius: 16; color: window.colors.dialog; border.color: window.colors.dialogBorder
            Behavior on height {
                enabled: !controller.reducedMotion && modal.shown && modal.opacity > 0.99
                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
            }
            Shared.MotionItem {
                id: menuContent; objectName: "appMenuContent"
                anchors.fill: parent; reducedMotion: controller.reducedMotion
                fadeEnabled: false; enterX: 4; enterDuration: 120
            ColumnLayout {
                id: modalContents; anchors.fill: parent; anchors.margins: 24; spacing: 16
                Text { objectName: "appMenuTitle"; font.family: window.fontFamily; Layout.fillWidth: true; text: modal.menu.title||""; font.pixelSize: 30; color: window.ink; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                Text { font.family: window.fontFamily; objectName: "menuBody"; Layout.fillWidth: true; visible: !!modal.menu.body; text: modal.menu.body||""; textFormat: Text.PlainText; font.pixelSize: 21; color: window.muted; wrapMode: Text.Wrap; maximumLineCount: modal.menu.bodyLines || 5; elide: Text.ElideRight }
                TextField { font.family: window.fontFamily; palette: window.colors.controls;
                    id: draft; objectName: "menuDraft"; visible: !!modal.menu.input; Layout.fillWidth: true
                    property QtObject inputController: controller
                    font.pixelSize: 23; color: window.ink; selectByMouse: true
                    background: Rectangle { color: window.colors.input; radius: 8; border.width: 2; border.color: window.accent }
                    onTextEdited: controller.setDraft(text)
                    Keys.priority: Keys.BeforeItem
                    Keys.onPressed: function(event) {
                        if (inputMethodComposing) {
                            event.accepted = [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape,
                                              Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right].indexOf(event.key) >= 0
                            return
                        }
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            if (!event.isAutoRepeat) controller.submit(text)
                            event.accepted = true
                        } else if (event.key === Qt.Key_Escape) {
                            if (!event.isAutoRepeat) controller.dispatch("back")
                            event.accepted = true
                        }
                    }
                }
                ListView {
                    id: options; objectName: "menuList"; Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.preferredHeight: contentHeight; Layout.minimumHeight: 0; clip: true; spacing: 5
                    model: window.menuModel; currentIndex: modal.menu.index||0
                    highlightFollowsCurrentItem: false
                    ScrollBar.vertical: ScrollBar { palette: window.colors.controls;}
                    Shared.FocusFrame {
                        objectName: "appMenuFocus"; parent: options.contentItem
                        target: options.currentItem; active: modal.shown
                        accent: window.accent; reducedMotion: controller.reducedMotion; radius: 8
                    }
                    delegate: Rectangle {
                        id: menuOption
                        required property var modelData
                        required property int index
                        property bool singleLine: !!modal.menu.settings
                        width: options.width; height: singleLine ? settingsRow.implicitHeight : Math.max(60,optionContents.implicitHeight+22); radius: 8
                        color: index===options.currentIndex?window.colors.selected:"transparent"
                        border.width: 0
                        opacity: !singleLine && modelData.disabled?0.45:1
                        Shared.SettingsRow {
                            id: settingsRow
                            anchors.fill: parent; visible: menuOption.singleLine
                            option: menuOption.modelData
                            colors: window.colors; fontFamily: window.fontFamily
                            selected: menuOption.index === options.currentIndex
                            border.width: 0
                            onLabel: window.tr(msg.ON); offLabel: window.tr(msg.OFF)
                            onActivated: controller.choose(menuOption.index)
                        }
                        Image {
                            id: appSettingIcon
                            objectName: "settingOptionIcon"
                            visible: !menuOption.singleLine && !!modelData.icon
                            x: 14; anchors.verticalCenter: parent.verticalCenter
                            height: optionContents.implicitHeight; width: height
                            source: visible ? "image://desktop/" + encodeURIComponent(modelData.icon) : ""
                            sourceSize: Qt.size(Math.ceil(width * 2), Math.ceil(height * 2))
                        }
                        Column {
                            id: optionContents; anchors.verticalCenter: parent.verticalCenter
                            visible: !menuOption.singleLine
                            x: modelData.icon ? appSettingIcon.x + appSettingIcon.width + 14 : 14
                            width: parent.width-x-14; spacing: 4
                            Text { font.family: window.fontFamily; width: parent.width; text: modelData.title; color: window.ink; wrapMode: Text.Wrap; font.pixelSize: 22 }
                            Text { font.family: window.fontFamily; width: parent.width; visible: !!modelData.subtitle; text: modelData.subtitle; color: window.muted; wrapMode: Text.Wrap; font.pixelSize: 17 }
                        }
                        MouseArea { anchors.fill: parent; enabled: !parent.singleLine && !parent.modelData.disabled; onClicked: controller.choose(parent.index) }
                    }
                }
                Shared.InputHints {
                    Layout.fillWidth: true
                    fontFamily: window.fontFamily; textColor: window.muted; fontSize: 18
                    hints: [{keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: window.tr(msg.CONFIRM)},
                            {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: window.tr(msg.BACK)}]
                }
            }
            }
        }
    }
    Shared.PointerIndicator {
        objectName: "pointerLayer"; anchors.fill: parent; z: 10000
        cursor: window.pointerCursor; colors: window.colors
        reducedMotion: controller.reducedMotion
    }
    Component.onCompleted: { syncModels(); Qt.callLater(focusInput) }
}
