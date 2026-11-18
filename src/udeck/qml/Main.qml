/*
[INPUT]: 依赖桌面控制器、ShellDialog 与页面组件。
[OUTPUT]: 提供局部选择更新、页面短过渡与启动反馈。
[POS]: ConsoleScreen 展示运行模型，其余页面沿用各自布局。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Window
import QtQuick.Controls

Window {
    id: window
    readonly property var msg: controller.messageKeys
    function tr(source) { return controller.translate(source, viewState.language) }
    function desktopIconSource(name) {
        const icon = name || "application-x-executable"
        const tint = icon.startsWith("udeck-setting:") ? "/" + window.colors.artText.toString() : ""
        return "image://desktop/" + encodeURIComponent(icon + tint)
    }
    width: 1280
    height: 720
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "uDeck"
    color: window.colors.background
    flags: windowedPreview ? Qt.Window : Qt.Window | Qt.FramelessWindowHint
    visibility: windowedPreview ? Window.Windowed : Window.FullScreen
    property var viewState: JSON.parse(controller.viewSnapshotJson)
    property var itemModel: []
    property var homeModel: []
    property var settingsModel: []
    property var modelStamps: ({})
    property string renderedPage: ""
    property string renderedTheme: ""
    property string renderedNavigation: ""
    property alias colors: themeColors
    ThemePalette { id: themeColors; theme: window.viewState.theme; profile: "shell" }
    property alias fontFamily: interfaceFonts.family
    InterfaceFonts { id: interfaceFonts; language: window.viewState.language }
    property var dialog: viewState.modal
    property color ink: window.colors.text
    property color muted: window.colors.muted
    property color accent: window.colors.accent
    property string clockText: controller.currentTime()
    property QtObject pointerCursor: null
    MotionTimings { id: motion; reducedMotion: window.viewState.reducedMotion }

    onActiveChanged: controller.windowActive(active)
    onClosing: function(event) {
        if (!windowedPreview) {
            event.accepted = false
            controller.activateSetting("logout")
        }
    }

    function syncView() {
        window.clockText = controller.currentTime()
        const keepScroll = renderedTheme !== "" && renderedTheme !== viewState.theme && renderedPage === viewState.page
        const gridY = applicationGrid.contentY
        const listY = itemList.contentY
        const pageChanged = renderedPage !== "" && renderedPage !== viewState.page
        const stamp = JSON.stringify(viewState.items)
        if (stamp !== modelStamps[viewState.page]) {
            modelStamps[viewState.page] = stamp
            if (viewState.page === "home")
                homeModel = viewState.items
            else if (viewState.page === "apps")
                itemModel = viewState.items
            else if (viewState.page === "settings")
                settingsModel = viewState.items
        }
        if (viewState.reducedMotion) content.finish()
        else if (pageChanged) content.replay()
        renderedPage = viewState.page
        renderedTheme = viewState.theme
        if (keepScroll) {
            applicationGrid.forceLayout()
            itemList.forceLayout()
            applicationGrid.contentY = gridY
            itemList.contentY = listY
        } else syncSelection(true)
        shellDialog.syncView()
    }

    function syncSelection(force) {
        const navigationStamp = [viewState.page, controller.navigationZone, controller.selectedIndex].join(":")
        if (!force && renderedNavigation === navigationStamp) return
        if (shellDialog.closing && renderedNavigation !== navigationStamp) shellDialog.finishClose()
        renderedNavigation = navigationStamp
        if (viewState.page === "home")
            homeScreen.positionSelection()
        else if (viewState.page === "apps")
            applicationGrid.positionViewAtIndex(controller.selectedIndex, GridView.Contain)
        else if (viewState.page === "files")
            filesScreen.positionSelection()
        else if (viewState.page === "windows")
            consoleScreen.positionSelection()
        else
            itemList.positionViewAtIndex(controller.selectedIndex, ListView.Contain)
    }

    Component.onCompleted: syncView()

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: window.clockText = controller.currentTime()
    }

    Connections {
        target: controller
        function onViewChanged() { Qt.callLater(window.syncView) }
        function onChanged() { Qt.callLater(window.syncSelection) }
        function onFilePreviewScroll(amount) { shellDialog.scrollPreview(amount) }
        function onPresent() {
            if (windowedPreview)
                window.show()
            else
                window.showFullScreen()
            if (!headlessPreview) {
                window.raise()
                window.requestActivate()
            }
        }
    }

    FocusScope {
        id: keyboardScope
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.AfterItem
        Keys.onPressed: function(event) {
            shellDialog.finishClose()
            let action = ""
            if (event.key === Qt.Key_Left) action = "left"
            else if (event.key === Qt.Key_Right) action = "right"
            else if (event.key === Qt.Key_Up) action = "up"
            else if (event.key === Qt.Key_Down) action = "down"
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) action = "accept"
            else if (event.key === Qt.Key_Escape) action = "back"
            else if (event.key === Qt.Key_F10) action = "context"
            else if (event.key === Qt.Key_F1) action = "quick-settings"
            else if (event.key === Qt.Key_PageUp) action = "previous-page"
            else if (event.key === Qt.Key_PageDown) action = "next-page"
            else if (event.key === Qt.Key_F && event.modifiers & Qt.ControlModifier) action = "search"
            if (viewState.page === "files" && !dialog.kind) {
                if (event.modifiers & Qt.ControlModifier) {
                    if (event.key === Qt.Key_C) action = "file-copy"
                    else if (event.key === Qt.Key_X) action = "file-cut"
                    else if (event.key === Qt.Key_V) action = "file-paste"
                    else if (event.key === Qt.Key_A) action = "file-select-all"
                    else if (event.key === Qt.Key_L) action = "file-go"
                } else {
                    if (event.key === Qt.Key_F2) action = "file-rename"
                    else if (event.key === Qt.Key_F5) action = "file-refresh"
                    else if (event.key === Qt.Key_Delete) action = "file-trash"
                    else if (event.key === Qt.Key_Space) action = "file-mark"
                }
            }
            if (action !== "" && (!event.isAutoRepeat || ["left", "right", "up", "down"].indexOf(action) >= 0)) {
                controller.dispatch(action)
                event.accepted = true
            }
        }

        Row {
            id: brandRow
            x: 28; y: 22; spacing: 13
            BrandLogo {
                colors: window.colors
                width: 34; height: 34
                anchors.verticalCenter: parent.verticalCenter
            }
            Text { textFormat: Text.PlainText; text: "uDeck"; font.family: window.fontFamily; font.pixelSize: 31; font.weight: Font.DemiBold; color: window.ink }
            Rectangle { width: 1; height: 24; color: window.colors.headerDivider; anchors.verticalCenter: parent.verticalCenter }
            Text { textFormat: Text.PlainText; text: viewState.mock ? window.tr(msg.SAFE_PREVIEW) : "uConsole"; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted; anchors.verticalCenter: parent.verticalCenter }
        }

        Row {
            id: statusBar
            objectName: "statusBar"
            anchors.right: parent.right; anchors.rightMargin: 28
            y: 24; height: 36; spacing: 24
            Text {
                visible: viewState.busy
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, 280, Math.max(0, window.width - brandRow.width - wirelessStatus.width - batteryStatus.width - statusClock.width - 56 - statusBar.spacing * 3 - 28))
                textFormat: Text.PlainText; elide: Text.ElideRight
                text: viewState.busyLabel
                font.family: window.fontFamily; font.pixelSize: 24; color: window.accent
            }
            Row {
                id: wirelessStatus
                anchors.verticalCenter: parent.verticalCenter
                spacing: 16
                Row {
                    spacing: 12
                    Repeater {
                        model: viewState.wifiIndicators
                        delegate: WirelessStatusIcon {
                            required property var modelData
                            width: 32; height: 32
                            colors: window.colors; fontFamily: window.fontFamily
                            hoverSurface: navigationPointer
                            kind: modelData.kind || "wifi"
                            deviceId: modelData.id
                            status: modelData.status
                            signalLevel: modelData.level
                            strengthKnown: modelData.strength !== null
                            description: modelData.label
                        }
                    }
                    WirelessStatusIcon {
                        visible: viewState.wifiIndicators.length === 0
                        width: 32; height: 32
                        colors: window.colors; fontFamily: window.fontFamily
                        hoverSurface: navigationPointer
                        status: "unavailable"
                        description: viewState.wifiSummary
                    }
                }
                WirelessStatusIcon {
                    visible: viewState.bluetooth.available && viewState.bluetooth.powered
                    width: 32; height: 32
                    colors: window.colors; fontFamily: window.fontFamily
                    hoverSurface: navigationPointer
                    kind: "bluetooth"
                    description: window.tr(msg.BLUETOOTH) + " · " + window.tr(msg.ENABLED)
                }
            }
            Row {
                id: batteryStatus
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Rectangle {
                    width: 31; height: 19; radius: 4; color: "transparent"; border.color: window.muted; border.width: 2
                    anchors.verticalCenter: parent.verticalCenter
                    Rectangle { x: 4; y: 4; height: 11; width: Math.max(1, 23 * viewState.battery.capacity / 100); radius: 1; color: viewState.battery.charging ? window.accent : window.muted }
                    Rectangle { x: 32; y: 6; width: 3; height: 7; radius: 1; color: window.muted }
                }
                Text { textFormat: Text.PlainText; text: viewState.battery.available ? viewState.battery.capacity + "%" : "—"; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted }
            }
            Text { id: statusClock; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: window.clockText; font.family: window.fontFamily; font.pixelSize: 24; font.weight: Font.Medium; color: window.ink }
        }

        Row {
            id: navigation
            objectName: "mainNavigation"
            x: 28; y: 85; width: parent.width - 56; height: 56
            spacing: 10
            Repeater {
                model: viewState.pages
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    objectName: "mainTab-" + modelData
                    property bool current: viewState.activeTab === modelData
                    width: (navigation.width - navigation.spacing * (viewState.pages.length - 1)) / viewState.pages.length; height: 56; radius: 10
                    color: current ? window.colors.selectedTab : "transparent"
                    border.width: current && controller.navigationZone === "tabs" && !dialog.kind ? 3 : 1
                    border.color: current && controller.navigationZone === "tabs" && !dialog.kind ? window.accent : (current ? window.colors.tabBorder : "transparent")
                    Row {
                        anchors.centerIn: parent; spacing: 12
                        Image { source: "image://desktop/" + ["go-home", "view-grid", "view-list-details", "folder"][index]; width: 27; height: 27; anchors.verticalCenter: parent.verticalCenter }
                        Text { textFormat: Text.PlainText; text: viewState.pageNames[index]; font.family: window.fontFamily; font.pixelSize: 24; font.weight: current ? Font.DemiBold : Font.Normal; color: current ? window.accent : window.muted }
                    }
                }
            }
        }

        Text { textFormat: Text.PlainText;
            visible: viewState.page !== "files"
            x: 30; y: 165; text: viewState.title
            font.family: window.fontFamily; font.pixelSize: 34; font.weight: Font.DemiBold; color: window.ink
        }
        Text { textFormat: Text.PlainText;
            visible: viewState.page !== "files" && viewState.page !== "windows"
            x: 30; y: 214; width: inputStatus.visible ? parent.width - 80 - inputStatus.width : parent.width - 60
            text: viewState.description; elide: Text.ElideMiddle
            font.family: window.fontFamily; font.pixelSize: 24; color: window.muted
        }
        Text { textFormat: Text.PlainText;
            id: inputStatus
            visible: viewState.page !== "files" && viewState.page !== "home" && viewState.page !== "windows"
            anchors.right: parent.right; anchors.rightMargin: 30; y: 216
            width: Math.min(implicitWidth, parent.width * 0.35); elide: Text.ElideRight
            text: viewState.mock ? window.tr(msg.NO_HARDWARE_CHANGES) : (viewState.input.verified ? window.tr(msg.ABXY_CALIBRATED) : (viewState.input.mapped ? window.tr(msg.ABXY_MAPPED) : window.tr(msg.ABXY_NEEDS_CALIBRATION)))
            font.family: window.fontFamily; font.pixelSize: 24; color: viewState.mock ? window.muted : window.accent
        }

        Text {
            visible: viewState.page === "windows"
            x: 30; y: 214; width: parent.width - 60
            textFormat: Text.PlainText
            text: consoleScreen.summaryText()
            font.family: window.fontFamily; font.pixelSize: 22; color: window.muted
            elide: Text.ElideRight
        }

        MotionItem {
            id: content
            objectName: "pageContent"
            enterX: 6; enterDuration: motion.page
            reducedMotion: viewState.reducedMotion
            x: 28; y: viewState.page === "files" ? 165 : viewState.page === "home" ? 250 : 265; width: parent.width - 56; height: parent.height - y - 85
            clip: true

            ConsoleScreen {
                id: consoleScreen
                objectName: "consoleScreen"
                anchors.fill: parent
                visible: viewState.page === "windows"
                appModel: controller.consoleModel
                summary: controller.runtimeConsole.summary
                colors: window.colors
                fontFamily: window.fontFamily
                index: controller.selectedIndex
                contentFocused: controller.navigationZone === "content" && !dialog.kind
                exitFocused: viewState.consoleExitFocused
                language: viewState.language
                hoverSurface: navigationPointer
                reducedMotion: viewState.reducedMotion
            }

            HomeScreen {
                id: homeScreen
                objectName: "homeScreen"
                anchors.fill: parent
                visible: viewState.page === "home"
                items: window.homeModel
                colors: window.colors
                fontFamily: window.fontFamily
                language: viewState.language
                index: controller.selectedIndex
                contentFocused: controller.navigationZone === "content" && !dialog.kind
                reducedMotion: viewState.reducedMotion
                launchState: viewState.appLaunch
            }

            FilesScreen {
                id: filesScreen
                objectName: "filesScreen"
                anchors.fill: parent
                visible: viewState.page === "files"
                state: viewState.fileState
                colors: window.colors
                fontFamily: window.fontFamily
                language: viewState.language
                fileModel: controller.fileModel
                reducedMotion: viewState.reducedMotion || false
                currentIndex: controller.selectedIndex
                contentFocused: controller.navigationZone === "content" && !dialog.kind
                busy: viewState.busy
            }

            GridView {
                id: applicationGrid
                objectName: "applicationGrid"
                anchors.fill: parent
                visible: viewState.page === "apps"
                model: window.itemModel
                cellWidth: width / 5; cellHeight: 174
                currentIndex: controller.selectedIndex
                keyNavigationEnabled: false
                interactive: false
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { palette: window.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                FocusFrame {
                    objectName: "appFocus"; parent: applicationGrid.contentItem
                    target: applicationGrid.currentItem; active: applicationGrid.visible && controller.navigationZone === "content" && !dialog.kind
                    accent: window.accent; reducedMotion: viewState.reducedMotion; radius: 12
                }
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    property bool selected: controller.selectedIndex === index && controller.navigationZone === "content"
                    readonly property bool launchPending: !!viewState.appLaunch.pending && modelData.id === viewState.appLaunch.applicationId
                    width: applicationGrid.cellWidth - 14; height: 158; radius: 12
                    scale: launchPending ? 0.98 : 1
                    Behavior on scale { NumberAnimation { duration: motion.press; easing.type: Easing.OutCubic } }
                    color: selected ? window.colors.selected : window.colors.panel
                    border.width: 1; border.color: window.colors.border
                    ApplicationIcon { objectName: "applicationIcon"; x: 18; y: 17; width: 56; height: 56; iconName: modelData.icon || "application-x-executable"; colors: window.colors; sourceSize.width: 80; sourceSize.height: 80 }
                    Text { textFormat: Text.PlainText; anchors.right: parent.right; anchors.rightMargin: 18; y: 21; text: viewState.favorites.indexOf(modelData.id) >= 0 ? "★" : ""; font.family: window.fontFamily; font.pixelSize: 24; color: window.accent }
                    Text { textFormat: Text.PlainText; x: 18; y: 84; width: parent.width - 36; text: modelData.name; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; font.weight: Font.Medium; color: window.ink }
                    Text { textFormat: Text.PlainText; x: 18; y: 120; width: parent.width - 36; text: launchPending ? window.tr(msg.OPENING_APPLICATION) : modelData.subtitle || viewState.categoryNames[modelData.category] || window.tr(msg.APPS); elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; color: launchPending ? window.accent : selected ? window.colors.selectedText : window.muted }
                }
            }

            ListView {
                id: itemList
                objectName: "itemList"
                anchors.fill: parent
                visible: viewState.page === "settings"
                model: window.settingsModel
                spacing: 10; currentIndex: controller.selectedIndex; keyNavigationEnabled: false
                interactive: false
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { palette: window.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                FocusFrame {
                    objectName: "settingsFocus"; parent: itemList.contentItem
                    target: itemList.currentItem; active: itemList.visible && controller.navigationZone === "content" && !dialog.kind
                    accent: window.accent; reducedMotion: viewState.reducedMotion
                }
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    property bool selected: controller.selectedIndex === index && controller.navigationZone === "content"
                    width: itemList.width - 12; height: Math.max(84, systemSettingText.implicitHeight + 20); radius: 10
                    color: selected ? window.colors.selected : window.colors.panel
                    border.width: 1; border.color: window.colors.rowBorder
                    ApplicationIcon {
                        id: systemSettingIcon; objectName: "systemSettingIcon"
                        x: 18; anchors.verticalCenter: parent.verticalCenter
                        height: systemSettingText.implicitHeight; width: height
                        iconName: modelData.icon || "application-x-executable"
                        colors: window.colors
                        sourceSize: Qt.size(Math.ceil(width * 2), Math.ceil(height * 2))
                    }
                    Column {
                        id: systemSettingText; anchors.verticalCenter: parent.verticalCenter
                        x: systemSettingIcon.x + systemSettingIcon.width + 18
                        width: parent.width - x - 28; spacing: 4
                        Text { textFormat: Text.PlainText; width: parent.width - (modelData.value !== undefined ? 190 : 30); text: modelData.name; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 25; color: modelData.disabled ? window.muted : window.ink }
                        Text { textFormat: Text.PlainText; width: parent.width; visible: !!modelData.subtitle; text: modelData.subtitle || ""; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted }
                    }
                    Rectangle {
                        visible: modelData.value !== undefined
                        anchors.right: parent.right; anchors.rightMargin: 26; y: 28; width: 170; height: 7; radius: 4; color: window.colors.rowTrack
                        Rectangle { width: parent.width * (modelData.value || 0); height: parent.height; radius: 4; color: window.accent }
                    }
                    Text { textFormat: Text.PlainText; visible: modelData.value === undefined; anchors.right: parent.right; anchors.rightMargin: 25; anchors.verticalCenter: parent.verticalCenter; text: "›"; font.family: window.fontFamily; font.pixelSize: 32; color: window.muted }
                }
            }

            Column {
                visible: viewState.page !== "files" && viewState.page !== "windows" && viewState.items.length === 0
                anchors.centerIn: parent; spacing: 14
                Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: viewState.busy ? window.tr(msg.PREPARING_CONTENT) : window.tr(msg.NO_ITEMS_HERE_YET); font.family: window.fontFamily; font.pixelSize: 30; color: window.ink }
                Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: viewState.page === "files" ? window.tr(msg.PRESS_X_TO_CREATE_A_FOLDER_OR_REFRESH) : (viewState.page === "windows" ? window.tr(msg.OPEN_AN_APP_TO_SEE_ITS_WINDOW_HERE) : window.tr(msg.PRESS_X_TO_CHANGE_CATEGORIES_OR_SEARCH)); font.family: window.fontFamily; font.pixelSize: 24; color: window.muted }
            }
        }

        Rectangle { x: 28; width: parent.width - 56; height: 1; y: parent.height - 74; color: window.colors.divider }
        Row {
            id: footerControls
            objectName: "footerControls"
            x: 30; y: parent.height - 37 - height / 2; spacing: 20
            Repeater {
                model: [{key: "gamecube_button_color_a", label: viewState.page === "windows" && !dialog.kind ? window.tr(viewState.consoleExitFocused ? msg.CONSOLE_EXIT : msg.CONSOLE_DETAILS) : window.tr(msg.CONFIRM)}, {key: "gamecube_button_color_b", label: window.tr(msg.BACK)}, {key: "gamecube_button_x", label: window.tr(msg.MORE)}, {key: "gamecube_button_y", label: window.tr(msg.QUICK_SETTINGS)}]
                delegate: InputPrompt {
                    required property var modelData
                    keys: [modelData.key]; label: modelData.label
                    fontFamily: window.fontFamily; textColor: window.muted
                    iconSize: 36; fontSize: 24
                }
            }
        }
        InputHints {
            objectName: "footerShortcuts"
            x: footerControls.x + footerControls.width + 20
            width: Math.max(0, parent.width - x - 30)
            y: parent.height - 37 - height / 2
            hints: [{keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"], label: window.tr(msg.PAGES)}]
                .concat(viewState.homeShortcutHints || [])
            fontFamily: window.fontFamily; fontSize: 20; iconSize: 32
            textColor: window.colors.pointer
        }

        ToastNotice {
            objectName: "shellToast"
            message: viewState.toast
            shown: !!message && !dialog.kind
            colors: window.colors; fontFamily: window.fontFamily
            reducedMotion: viewState.reducedMotion
            maximumWidth: parent.width - 120
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - height - 92
            fontSize: 24
        }

        ShellDialog {
            id: shellDialog
            anchors.fill: parent
            viewState: window.viewState; colors: window.colors; fontFamily: window.fontFamily
            reducedMotion: viewState.reducedMotion
            onRestoreFocus: keyboardScope.forceActiveFocus()
        }
        MouseArea {
            id: navigationPointer
            anchors.fill: parent
            z: 1000
            acceptedButtons: viewState.page === "windows" ? (shellDialog.visible ? Qt.NoButton : Qt.RightButton) : Qt.AllButtons
            hoverEnabled: true
            cursorShape: Qt.BlankCursor
            preventStealing: true
            onPressed: function(mouse) {
                if (shellDialog.visible) { mouse.accepted = true; return }
                if (mouse.button === Qt.LeftButton)
                    controller.dispatch("previous-page")
                else if (mouse.button === Qt.RightButton)
                    controller.dispatch("next-page")
                mouse.accepted = true
            }
            onDoubleClicked: function(mouse) { mouse.accepted = true }
            onWheel: function(wheel) { wheel.accepted = true }
        }
    }

    LoadingOverlay {
        objectName: "startupOverlay"
        anchors.fill: parent
        z: 30
        colors: window.colors
        fontFamily: window.fontFamily
        shown: window.viewState.startup.active
        brand: true
        applicationName: "uDeck"
        message: window.tr(msg.PREPARING_DESKTOP)
        reducedMotion: window.viewState.reducedMotion
    }

    LoadingOverlay {
        objectName: "appLaunchOverlay"
        anchors.fill: parent
        z: 20
        colors: window.colors
        fontFamily: window.fontFamily
        shown: window.viewState.appLaunch.visible
        applicationName: window.viewState.appLaunch.name || ""
        applicationIcon: window.viewState.appLaunch.icon || "application-x-executable"
        homeKind: window.viewState.appLaunch.homeKind || ""
        message: window.viewState.appLaunch.message || ""
        returnLabel: window.tr(msg.RETURN_TO_DESKTOP)
        reducedMotion: window.viewState.reducedMotion
        immediateHide: !window.active && !headlessPreview
    }

    PointerIndicator {
        objectName: "pointerLayer"
        anchors.fill: parent
        z: 10000
        cursor: window.pointerCursor
        colors: window.colors
    }
}
