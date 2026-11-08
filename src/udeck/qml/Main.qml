import QtQuick
import QtQuick.Window
import QtQuick.Controls

Window {
    id: window
    function tr(source) { return controller.translate(source, viewState.language) }
    width: 1280
    height: 720
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "uDeck"
    color: window.colors.background
    flags: windowedPreview ? Qt.Window : Qt.Window | Qt.FramelessWindowHint
    visibility: windowedPreview ? Window.Windowed : Window.FullScreen
    property var viewState: JSON.parse(controller.snapshotJson)
    property var itemModel: []
    property var homeModel: []
    property string itemsStamp: ""
    property string renderedPage: ""
    property string renderedTheme: ""
    property alias colors: themeColors
    ThemePalette { id: themeColors; theme: window.viewState.theme; profile: "shell" }
    property alias fontFamily: interfaceFonts.family
    InterfaceFonts { id: interfaceFonts; language: window.viewState.language }
    property var dialog: viewState.modal
    property color ink: window.colors.text
    property color muted: window.colors.muted
    property color accent: window.colors.accent
    property string lastDialog: ""
    property string clockText: controller.currentTime()

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
        const stamp = JSON.stringify(viewState.items)
        if (stamp !== itemsStamp || renderedPage !== viewState.page) {
            itemsStamp = stamp
            if (viewState.page === "home")
                homeModel = viewState.items
            else
                itemModel = viewState.items
        }
        renderedPage = viewState.page
        renderedTheme = viewState.theme
        if (keepScroll) {
            applicationGrid.forceLayout()
            itemList.forceLayout()
            applicationGrid.contentY = gridY
            itemList.contentY = listY
        } else if (viewState.page === "home")
            homeScreen.positionSelection()
        else if (viewState.page === "apps")
            applicationGrid.positionViewAtIndex(viewState.index, GridView.Contain)
        else
            itemList.positionViewAtIndex(viewState.index, ListView.Contain)
        if (dialog.kind === "menu")
            menuList.positionViewAtIndex(dialog.index, ListView.Contain)
        let currentDialog = dialog.key || ""
        if (currentDialog !== lastDialog) {
            lastDialog = currentDialog
            if (dialog.kind === "text") {
                editor.text = dialog.text || ""
                controller.editText(editor.text)
                editor.forceActiveFocus()
                editor.selectAll()
            } else {
                keyboardScope.forceActiveFocus()
            }
        }
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
        function onChanged() { Qt.callLater(window.syncView) }
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
            if (action !== "" && (!event.isAutoRepeat || ["left", "right", "up", "down"].indexOf(action) >= 0)) {
                controller.dispatch(action)
                event.accepted = true
            }
        }

        Row {
            id: brandRow
            x: 28; y: 22; spacing: 13
            Rectangle {
                width: 34; height: 34; radius: 9; color: window.accent
                anchors.verticalCenter: parent.verticalCenter
                Rectangle { width: 15; height: 4; radius: 2; color: window.colors.brandInk; anchors.centerIn: parent }
                Rectangle { width: 4; height: 15; radius: 2; color: window.colors.brandInk; anchors.centerIn: parent }
            }
            Text { textFormat: Text.PlainText; text: "uDeck"; font.family: window.fontFamily; font.pixelSize: 31; font.weight: Font.DemiBold; color: window.ink }
            Rectangle { width: 1; height: 24; color: window.colors.headerDivider; anchors.verticalCenter: parent.verticalCenter }
            Text { textFormat: Text.PlainText; text: viewState.mock ? window.tr("安全预览") : "uConsole"; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted; anchors.verticalCenter: parent.verticalCenter }
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
                    description: window.tr("蓝牙") + " · " + window.tr("已开启")
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
                    border.width: current && viewState.zone === "tabs" && !dialog.kind ? 3 : 1
                    border.color: current && viewState.zone === "tabs" && !dialog.kind ? window.accent : (current ? window.colors.tabBorder : "transparent")
                    Row {
                        anchors.centerIn: parent; spacing: 12
                        Image { source: "image://desktop/" + ["go-home", "view-grid", "view-list-details", "folder"][index]; width: 27; height: 27; anchors.verticalCenter: parent.verticalCenter }
                        Text { textFormat: Text.PlainText; text: viewState.pageNames[index]; font.family: window.fontFamily; font.pixelSize: 24; font.weight: current ? Font.DemiBold : Font.Normal; color: current ? window.accent : window.muted }
                    }
                }
            }
        }

        Text { textFormat: Text.PlainText;
            x: 30; y: 165; text: viewState.title
            font.family: window.fontFamily; font.pixelSize: 34; font.weight: Font.DemiBold; color: window.ink
        }
        Text { textFormat: Text.PlainText;
            x: 30; y: 214; width: parent.width - 80 - inputStatus.width
            text: viewState.description; elide: Text.ElideMiddle
            font.family: window.fontFamily; font.pixelSize: 24; color: window.muted
        }
        Text { textFormat: Text.PlainText;
            id: inputStatus
            anchors.right: parent.right; anchors.rightMargin: 30; y: 216
            width: Math.min(implicitWidth, parent.width * 0.35); elide: Text.ElideRight
            text: viewState.mock ? window.tr("不操作真实设备") : (viewState.input.verified ? window.tr("ABXY 已校准") : (viewState.input.mapped ? window.tr("ABXY 已映射") : window.tr("ABXY 待校准")))
            font.family: window.fontFamily; font.pixelSize: 24; color: viewState.mock ? window.muted : window.accent
        }

        Item {
            id: content
            x: 28; y: viewState.page === "home" ? 250 : 265; width: parent.width - 56; height: parent.height - y - 85
            clip: true

            HomeScreen {
                id: homeScreen
                objectName: "homeScreen"
                anchors.fill: parent
                visible: viewState.page === "home"
                items: visible ? window.homeModel : []
                colors: window.colors
                fontFamily: window.fontFamily
                index: viewState.index
                contentFocused: viewState.zone === "content" && !dialog.kind
                reducedMotion: viewState.reducedMotion
            }

            GridView {
                id: applicationGrid
                objectName: "applicationGrid"
                anchors.fill: parent
                visible: viewState.page === "apps"
                model: visible ? window.itemModel : []
                cellWidth: width / 5; cellHeight: 174
                currentIndex: viewState.index
                keyNavigationEnabled: false
                interactive: false
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { palette: window.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    property bool selected: viewState.index === index && viewState.zone === "content"
                    width: applicationGrid.cellWidth - 14; height: 158; radius: 12
                    color: selected ? window.colors.selected : window.colors.panel
                    border.width: selected ? 3 : 1
                    border.color: selected ? window.accent : window.colors.border
                    Image { x: 18; y: 17; width: 56; height: 56; source: "image://desktop/" + encodeURIComponent(modelData.icon || "application-x-executable"); sourceSize.width: 80; sourceSize.height: 80 }
                    Text { textFormat: Text.PlainText; anchors.right: parent.right; anchors.rightMargin: 18; y: 21; text: viewState.favorites.indexOf(modelData.id) >= 0 ? "★" : ""; font.family: window.fontFamily; font.pixelSize: 24; color: window.accent }
                    Text { textFormat: Text.PlainText; x: 18; y: 84; width: parent.width - 36; text: modelData.name; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; font.weight: Font.Medium; color: window.ink }
                    Text { textFormat: Text.PlainText; x: 18; y: 120; width: parent.width - 36; text: modelData.subtitle || viewState.categoryNames[modelData.category] || window.tr("应用"); elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; color: selected ? window.colors.selectedText : window.muted }
                }
            }

            ListView {
                id: itemList
                objectName: "itemList"
                anchors.fill: parent
                visible: viewState.page !== "home" && viewState.page !== "apps"
                model: visible ? window.itemModel : []
                spacing: 10; currentIndex: viewState.index; keyNavigationEnabled: false
                interactive: false
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { palette: window.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    property bool selected: viewState.index === index && viewState.zone === "content"
                    width: itemList.width - 12; height: 84; radius: 10
                    color: selected ? window.colors.selected : window.colors.panel
                    border.width: selected ? 3 : 1
                    border.color: selected ? window.accent : window.colors.rowBorder
                    Image { x: 18; anchors.verticalCenter: parent.verticalCenter; width: 44; height: 44; source: "image://desktop/" + encodeURIComponent(modelData.icon || "application-x-executable") }
                    Text { textFormat: Text.PlainText; x: 83; y: 12; width: parent.width - 310; text: modelData.name; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 25; color: modelData.disabled ? window.muted : window.ink }
                    Text { textFormat: Text.PlainText; x: 83; y: 47; width: parent.width - 150; text: modelData.subtitle || ""; elide: Text.ElideRight; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted }
                    Rectangle {
                        visible: modelData.value !== undefined
                        anchors.right: parent.right; anchors.rightMargin: 26; y: 28; width: 170; height: 7; radius: 4; color: window.colors.rowTrack
                        Rectangle { width: parent.width * (modelData.value || 0); height: parent.height; radius: 4; color: window.accent }
                    }
                    Text { textFormat: Text.PlainText; visible: modelData.value === undefined; anchors.right: parent.right; anchors.rightMargin: 25; anchors.verticalCenter: parent.verticalCenter; text: "›"; font.family: window.fontFamily; font.pixelSize: 32; color: window.muted }
                }
            }

            Column {
                visible: viewState.items.length === 0
                anchors.centerIn: parent; spacing: 14
                Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: viewState.busy ? window.tr("正在准备内容") : window.tr("这里还没有项目"); font.family: window.fontFamily; font.pixelSize: 30; color: window.ink }
                Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: viewState.page === "files" ? window.tr("按 X 新建文件夹或刷新") : (viewState.page === "windows" ? window.tr("启动应用后，窗口会显示在这里") : window.tr("按 X 调整分类或搜索条件")); font.family: window.fontFamily; font.pixelSize: 24; color: window.muted }
            }
        }

        Rectangle { x: 28; width: parent.width - 56; height: 1; y: parent.height - 74; color: window.colors.divider }
        Row {
            id: footerControls
            objectName: "footerControls"
            x: 30; y: parent.height - 37 - height / 2; spacing: 20
            Repeater {
                model: [{key: "gamecube_button_color_a", label: window.tr("确认")}, {key: "gamecube_button_color_b", label: window.tr("返回")}, {key: "gamecube_button_x", label: window.tr("更多")}, {key: "gamecube_button_y", label: window.tr("快捷设置")}]
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
            hints: [{keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"], label: window.tr("Pages")},
                    {keys: ["keyboard_ctrl", "+", "keyboard_alt", "+", "keyboard_escape"], label: window.tr("主页")}]
            fontFamily: window.fontFamily; fontSize: 20; iconSize: 32
            textColor: window.colors.pointer
        }

        Rectangle {
            visible: !!viewState.toast && !dialog.kind
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - height - 92; width: Math.min(parent.width - 120, toastText.implicitWidth + 44); height: toastText.implicitHeight + 30
            radius: 10; color: window.colors.toast; border.color: window.colors.toastBorder
            Text { textFormat: Text.PlainText; id: toastText; anchors.centerIn: parent; width: Math.min(implicitWidth, keyboardScope.width - 180); text: viewState.toast; font.family: window.fontFamily; font.pixelSize: 24; color: window.ink; wrapMode: Text.Wrap }
        }

        Rectangle {
            id: modalShade
            visible: !!dialog.kind
            anchors.fill: parent
            color: window.colors.scrim

            Rectangle {
                id: panel
                objectName: "dialogPanel"
                anchors.centerIn: parent
                width: dialog.kind === "key-test" ? Math.min(1160, parent.width - 48) : Math.min(810, parent.width - 96)
                property real menuChromeHeight: dialog.kind === "menu" ? 96 + dialogTitle.implicitHeight + modalFooter.implicitHeight
                    + (dialog.body ? dialogBody.implicitHeight + 20 : 0)
                    + (viewState.toast ? modalToast.height + 20 : 0) : 0
                height: Math.min(parent.height - (dialog.kind === "key-test" ? 32 : 64), dialog.kind === "menu"
                    ? menuChromeHeight + (dialog.options || []).length * 80 : modalColumn.height + (dialog.kind === "key-test" ? 40 : 56))
                radius: 16; color: window.colors.dialog; border.width: 1; border.color: window.colors.dialogBorder

                Column {
                    id: modalColumn
                    objectName: "dialogContent"
                    x: dialog.kind === "key-test" ? 20 : 28; y: dialog.kind === "key-test" ? 20 : 26
                    width: parent.width - 2 * x; spacing: dialog.kind === "key-test" ? 8 : 20
                    Text { textFormat: Text.PlainText; id: dialogTitle; width: parent.width; text: dialog.title || ""; font.family: window.fontFamily; font.pixelSize: dialog.kind === "key-test" ? 28 : 32; font.weight: Font.DemiBold; color: window.ink; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                    Text { textFormat: Text.PlainText; id: dialogBody; visible: !!dialog.body; width: parent.width; text: dialog.body || ""; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight }

                    Column {
                        visible: !!dialog.metrics
                        width: parent.width; spacing: 12
                        Repeater {
                            model: dialog.metrics || []
                            delegate: Item {
                                required property var modelData
                                width: modalColumn.width; height: 34
                                Text { objectName: "batteryMetricLabel"; textFormat: Text.PlainText; width: parent.width - 190; anchors.verticalCenter: parent.verticalCenter; text: modelData.label; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted; elide: Text.ElideRight }
                                Text { objectName: "batteryMetricValue"; textFormat: Text.PlainText; width: 178; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData.value; horizontalAlignment: Text.AlignRight; font.family: window.fontFamily; font.pixelSize: 26; font.weight: Font.Medium; color: window.ink; elide: Text.ElideRight }
                            }
                        }
                    }

                    ListView {
                        id: menuList
                        visible: dialog.kind === "menu"
                        width: parent.width
                        height: visible ? Math.max(0, Math.min((dialog.options || []).length * 80, window.height - 64 - panel.menuChromeHeight)) : 0
                        model: visible ? dialog.options : []
                        clip: true; spacing: 5; currentIndex: dialog.index || 0; keyNavigationEnabled: false
                        interactive: false
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { palette: window.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: menuList.width - 10; height: modelData.wrapSubtitle ? 106 : modelData.subtitle ? 75 : 64; radius: 8
                            color: dialog.index === index ? window.colors.menuSelected : "transparent"
                            border.width: dialog.index === index ? 3 : 0
                            border.color: window.accent
                            opacity: modelData.disabled ? 0.45 : 1
                            Text { textFormat: Text.PlainText; x: 15; y: modelData.subtitle ? 8 : 14; width: parent.width - 30; text: modelData.label; font.family: window.fontFamily; font.pixelSize: 25; color: window.ink; elide: Text.ElideRight }
                            Text { textFormat: Text.PlainText; x: 15; y: 43; width: parent.width - 30; visible: !!modelData.subtitle; text: modelData.subtitle || ""; font.family: window.fontFamily; font.pixelSize: 24; color: window.muted; wrapMode: modelData.wrapSubtitle ? Text.WrapAnywhere : Text.NoWrap; maximumLineCount: modelData.wrapSubtitle ? 2 : 1; elide: Text.ElideRight }
                        }
                    }

                    Text { visible: !!dialog.error; width: parent.width; text: dialog.error || ""; textFormat: Text.PlainText; font.family: window.fontFamily; font.pixelSize: 22; color: window.colors.error; wrapMode: Text.Wrap; maximumLineCount: 2 }

                    KeyTestPanel {
                        visible: dialog.kind === "key-test"
                        width: parent.width
                        colors: window.colors; fontFamily: window.fontFamily; state: dialog
                        translate: window.tr
                        reducedMotion: viewState.reducedMotion || false
                        compact: window.height < 660
                        notice: viewState.toast || ""
                    }

                    TextField { palette: window.colors.controls;
                        id: editor
                        visible: dialog.kind === "text"
                        width: parent.width; height: 66
                        font.family: window.fontFamily; font.pixelSize: 28; color: window.ink
                        selectByMouse: false
                        maximumLength: 4096
                        echoMode: dialog.secret && !dialog.reveal ? TextInput.Password : TextInput.Normal
                        inputMethodHints: dialog.secret ? Qt.ImhSensitiveData | Qt.ImhNoPredictiveText : (dialog.numeric ? Qt.ImhDigitsOnly : Qt.ImhNone)
                        background: Rectangle { radius: 8; color: window.colors.input; border.width: 2; border.color: window.accent }
                        onTextEdited: controller.editText(text)
                        onAccepted: controller.dispatch("accept")
                        Keys.onEscapePressed: function(event) { if (!inputMethodComposing) { controller.dispatch("back"); event.accepted = true } }
                    }

                    Column {
                        visible: dialog.kind === "slider"
                        width: parent.width; spacing: 18
                        Text { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: Math.round((dialog.value || 0) * 100) + "%"; font.family: window.fontFamily; font.pixelSize: 50; color: window.accent }
                        Rectangle { width: parent.width; height: 12; radius: 6; color: window.colors.track; Rectangle { width: parent.width * (dialog.value || 0); height: parent.height; radius: 6; color: window.accent } }
                    }

                    ProgressBar { visible: dialog.kind === "progress"; width: parent.width; indeterminate: visible }

                    Row {
                        visible: dialog.kind === "confirm" || dialog.kind === "text"
                        width: parent.width; spacing: 14
                        Repeater {
                            model: [window.tr("取消"), window.tr("确认")]
                            delegate: Rectangle {
                                required property string modelData
                                required property int index
                                property bool selected: dialog.kind === "confirm" ? dialog.index === index : index === 1
                                width: (modalColumn.width - 14) / 2; height: 58; radius: 8
                                color: selected ? window.colors.buttonSelected : window.colors.button; border.width: selected ? 3 : 1; border.color: selected ? window.accent : window.colors.buttonBorder
                                Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: modelData; font.family: window.fontFamily; font.pixelSize: 25; color: window.ink }
                            }
                        }
                    }

                    InputHints {
                        id: modalFooter; width: parent.width
                        fontFamily: window.fontFamily; textColor: window.muted; fontSize: 22
                        hints: dialog.kind === "key-test" ? [{keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: window.tr("Hold 1.2 s to return")}] : dialog.kind === "calibration" ? [{keys: ["keyboard_escape"], label: window.tr("取消")}] : [
                            {keys: ["gamecube_button_color_a", "/", "keyboard_enter"], label: window.tr("确认")},
                            {keys: ["gamecube_button_color_b", "/", "keyboard_escape"], label: window.tr(dialog.kind === "text" ? "取消" : "返回")}].concat(dialog.kind === "text" && dialog.secret ? [
                            {keys: ["gamecube_button_x"], label: window.tr(dialog.reveal ? "Hide password" : "Show password")} ] : [])
                    }
                    Text { textFormat: Text.PlainText; id: modalToast; visible: !!viewState.toast && dialog.kind !== "key-test"; width: parent.width; text: viewState.toast; font.family: window.fontFamily; font.pixelSize: 24; color: window.accent; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                }
            }
        }
        MouseArea {
            id: navigationPointer
            anchors.fill: parent
            z: 1000
            acceptedButtons: Qt.AllButtons
            hoverEnabled: true
            cursorShape: Qt.BlankCursor
            preventStealing: true
            onPressed: function(mouse) {
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
}
