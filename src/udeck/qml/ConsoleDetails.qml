/*
[INPUT]: 依赖应用实时详情、ConsoleFormat、主题与模态选择。
[OUTPUT]: 复用八个指标控件，区分 PSS、RSS、独占内存与进程信息。
[POS]: Main 模态容器内的详情内容；退出确认由控制器编排。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Column {
    id: root
    objectName: "consoleDetails"
    required property var details
    required property var colors
    required property string fontFamily
    required property string language
    required property int index
    property bool reducedMotion: false
    readonly property var msg: controller.messageKeys
    readonly property bool available: !!details.available
    readonly property var metricNames: ["State", "Cpu", "Uptime", "Memory", "Rss", "Private", "Pid", "Processes"]
    readonly property var metricLabels: [tr(msg.CONSOLE_STATE), "CPU", tr(msg.CONSOLE_UPTIME),
        tr(msg.CONSOLE_MEMORY), tr(msg.CONSOLE_MEMORY_RSS), tr(msg.CONSOLE_MEMORY_PRIVATE),
        tr(msg.CONSOLE_PID), tr(msg.CONSOLE_PROCESSES)]
    readonly property var metricValues: [
        format.state(available ? details.runtimeState : "exited", language),
        format.percent(details.cpuPercent), format.uptime(details.uptimeSeconds),
        format.memory(details.memoryBytes, "MiB"),
        format.memory(details.memoryRssBytes, "MiB"), format.memory(details.memoryPrivateBytes, "MiB"),
        details.mainPid || "—", details.processCount ?? "—"
    ]
    spacing: 14
    function tr(key) { return controller.translate(key, language) }
    function syncActionFocus() { actionFocus.target = actions.itemAt(root.index) }
    onIndexChanged: Qt.callLater(syncActionFocus)
    ConsoleFormat { id: format }

    Grid {
        width: parent.width; columns: 3; columnSpacing: 20; rowSpacing: 8
        Repeater {
            model: root.metricNames.length
            delegate: Column {
                id: metric
                required property int index
                width: (root.width - 40) / 3; height: 52; spacing: 2
                Text {
                    width: parent.width; text: root.metricLabels[metric.index]; textFormat: Text.PlainText
                    font.family: root.fontFamily; font.pixelSize: 18; color: root.colors.muted
                    elide: Text.ElideRight
                }
                Text {
                    objectName: "consoleDetails" + root.metricNames[metric.index]
                    width: parent.width; text: root.metricValues[metric.index]; textFormat: Text.PlainText
                    font.family: root.fontFamily; font.pixelSize: 24; font.features: { "tnum": 1 }
                    color: root.colors.text; elide: Text.ElideRight
                }
            }
        }
    }
    Text {
        width: parent.width; text: root.details.applicationKey || ""; textFormat: Text.PlainText
        font.family: root.fontFamily; font.pixelSize: 18; color: root.colors.muted; elide: Text.ElideMiddle
    }
    Item {
        width: parent.width; height: actionGrid.implicitHeight
        FocusFrame {
            id: actionFocus; active: root.visible
            accent: root.colors.accent; reducedMotion: root.reducedMotion; radius: 7
        }
        Grid {
            id: actionGrid
            width: parent.width; columns: 2; spacing: 8
            Repeater {
                id: actions
                onItemAdded: function(index, item) { if (index === root.index) actionFocus.target = item }
                model: [
                    {label: root.tr(msg.OPEN_APP), enabled: root.available},
                    {label: root.tr(msg.CONSOLE_EXIT), enabled: root.available && root.details.canQuit},
                    {label: root.tr(msg.CONSOLE_FORCE_QUIT), enabled: root.available && root.details.canForce},
                    {label: root.tr(msg.CONSOLE_CLOSE), enabled: true}
                ]
                delegate: Rectangle {
                    id: button
                    required property var modelData
                    required property int index
                    readonly property bool selected: root.index === index
                    objectName: "consoleDetailsAction-" + index
                    width: (root.width - 8) / 2; height: 48; radius: 7
                    color: selected ? root.colors.buttonSelected : root.colors.button
                    border.width: 1; border.color: root.colors.buttonBorder
                    opacity: modelData.enabled ? 1 : 0.45
                    Text {
                        anchors.centerIn: parent; width: parent.width - 20
                        text: button.modelData.label; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter
                        font.family: root.fontFamily; font.pixelSize: 22; color: root.colors.text; elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent; enabled: button.modelData.enabled; cursorShape: Qt.BlankCursor
                        onClicked: controller.chooseModal(button.index)
                    }
                }
            }
        }
    }
}
