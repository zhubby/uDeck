/*
[INPUT]: 依赖 Agent 版本、主题和共享列表焦点。
[OUTPUT]: 提供四款 Agent 的选择列表、连接设置和操作面板。
[POS]: Agent 应用设置中的管理页。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Layouts
import "../../../qml" as Shared

RowLayout {
    id: manage
    required property var host
    required property var colors
    readonly property var msg: controller.messageKeys
    readonly property var state: host.state
    readonly property var providers: state.providers || []
    readonly property var current: providers[state.providerIndex] || ({})
    readonly property bool working: !!state.job
    readonly property bool selectedWorking: state.job === current.id
    readonly property int railWidth: Math.min(340, Math.round(width * 0.33))
    readonly property var tints: ({codex: "#243247", claude: "#463128",
                                   opencode: "#303537", pi: "#28382b"})

    spacing: 20

    ListView {
        id: providerList
        Layout.minimumWidth: manage.railWidth
        Layout.preferredWidth: manage.railWidth
        Layout.maximumWidth: manage.railWidth
        Layout.fillHeight: true
        spacing: 8
        clip: true
        model: manage.providers
        currentIndex: manage.state.providerIndex
        keyNavigationEnabled: false
        highlightFollowsCurrentItem: false
        boundsBehavior: Flickable.StopAtBounds

        Shared.SelectionViewport {
            view: providerList
            active: providerList.visible && host.active && !manage.state.menu.title
            reducedMotion: controller.reducedMotion
        }
        Shared.FocusFrame {
            parent: providerList.contentItem
            target: providerList.currentItem
            active: providerList.visible && host.active && !manage.state.menu.title
            accent: colors.accent
            reducedMotion: controller.reducedMotion
        }

        delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool selected: index === manage.state.providerIndex
            readonly property bool working: manage.state.job === modelData.id

            objectName: "agentProvider-" + modelData.id
            width: providerList.width
            height: 60
            radius: 10
            color: selected || hover.hovered ? colors.selected : colors.panel
            border.width: 1
            border.color: colors.border
            Accessible.role: Accessible.ListItem
            Accessible.name: modelData.name
            Accessible.selected: selected
            Accessible.onPressAction: controller.selectProvider(modelData.id)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 13
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 38
                    Layout.preferredHeight: 38
                    radius: 9
                    color: manage.tints[row.modelData.id]
                    AgentIcon {
                        anchors.centerIn: parent
                        name: row.modelData.id
                        size: 21
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: row.modelData.name
                    color: colors.text
                    font.family: host.fontFamily
                    font.pixelSize: 20
                    elide: Text.ElideRight
                }
                Text {
                    text: row.modelData.installed || ""
                    visible: !!text && manage.width >= 900
                    color: colors.muted
                    font.family: host.fontFamily
                    font.pixelSize: 15
                }
                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: 4
                    color: row.working || row.modelData.upgrade || row.modelData.needsLogin
                           ? colors.accent : row.modelData.installed ? "#a7cea4" : colors.signalInactive
                }
            }
            HoverHandler { id: hover }
            TapHandler {
                onTapped: controller.selectProvider(row.modelData.id)
                onDoubleTapped: controller.providerActions(row.modelData.id)
            }
        }
    }

    Rectangle {
        objectName: "agentManageDetails"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(390, manage.height)
        Layout.alignment: Qt.AlignTop
        radius: 10
        color: colors.panel
        border.width: 1
        border.color: colors.border

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 21
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Rectangle {
                    Layout.preferredWidth: 56
                    Layout.preferredHeight: 56
                    radius: 12
                    color: manage.tints[manage.current.id] || colors.panel
                    AgentIcon {
                        anchors.centerIn: parent
                        name: manage.current.id || ""
                        size: 31
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        text: manage.current.name || ""
                        color: colors.text
                        font.family: host.fontFamily
                        font.pixelSize: 27
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: manage.selectedWorking ? manage.state.stage
                              : manage.current.needsLogin ? host.tr(msg.AGENT_NEEDS_LOGIN)
                              : manage.current.verified ? host.tr(msg.AGENT_VERIFIED)
                              : manage.current.installed ? host.tr(msg.AGENT_INSTALLED)
                              : host.tr(msg.AGENT_MISSING)
                        color: manage.selectedWorking || manage.current.needsLogin ? colors.accent : colors.muted
                        font.family: host.fontFamily
                        font.pixelSize: 17
                        elide: Text.ElideRight
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: colors.divider }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: 9
                columnSpacing: 16

                Text {
                    text: host.tr(msg.AGENT_INSTALLED_VERSION)
                    color: colors.muted
                    font.family: host.fontFamily
                    font.pixelSize: 17
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignRight
                    text: manage.current.installed || "–"
                    color: colors.text
                    font.family: host.fontFamily
                    font.pixelSize: 17
                }
                Text {
                    text: host.tr(msg.AGENT_AVAILABLE_VERSION)
                    color: colors.muted
                    font.family: host.fontFamily
                    font.pixelSize: 17
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignRight
                    text: manage.current.available || "–"
                    color: manage.current.upgrade ? colors.accent : colors.text
                    font.family: host.fontFamily
                    font.pixelSize: 17
                }
            }
            Item { Layout.fillHeight: true }

            AgentButton {
                objectName: "agentConfigureProvider"
                text: host.tr(msg.AGENT_MODEL_CONNECTION)
                glyph: "plug"
                enabled: !manage.working
                compact: manage.width < 1000
                colors: manage.colors
                fontFamily: host.fontFamily
                onActivated: controller.configureProvider(manage.current.id)
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 9
                AgentButton {
                    objectName: "agentProviderPrimary"
                    visible: !!manage.state.providerPrimary && (!manage.working || manage.selectedWorking)
                    text: manage.state.providerPrimary || ""
                    glyph: manage.state.providerGlyph || ""
                    primary: !manage.working
                    destructive: manage.working
                    compact: manage.width < 1000
                    colors: manage.colors
                    fontFamily: host.fontFamily
                    onActivated: controller.activateProvider()
                }
                AgentButton {
                    visible: !manage.working && manage.state.providerGlyph !== "arrow-repeat"
                    text: host.tr(msg.AGENT_CHECK_UPDATES)
                    glyph: "arrow-repeat"
                    compact: manage.width < 1000
                    colors: manage.colors
                    fontFamily: host.fontFamily
                    onActivated: controller.checkProviderUpdates()
                }
                AgentButton {
                    objectName: "agentProviderActions"
                    text: host.tr(msg.ACTIONS)
                    glyph: "three-dots"
                    compact: manage.width < 1000
                    enabled: !manage.working || manage.selectedWorking
                    colors: manage.colors
                    fontFamily: host.fontFamily
                    onActivated: controller.providerActions(manage.current.id)
                }
                Item { Layout.fillWidth: true }
            }
        }
    }
}
