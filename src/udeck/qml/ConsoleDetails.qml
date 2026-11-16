/*
[INPUT]: 依赖应用实时详情、ConsoleFormat、主题与模态选择。
[OUTPUT]: 提供运行指标、进程信息和四个应用操作入口。
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
    readonly property var msg: controller.messageKeys
    readonly property bool available: !!details.available
    spacing: 14
    function tr(key) { return controller.translate(key, language) }
    ConsoleFormat { id: format }

    Grid {
        width: parent.width; columns: 2; columnSpacing: 20; rowSpacing: 8
        Repeater {
            model: [
                {label: root.tr(msg.CONSOLE_STATE), value: format.state(root.available ? root.details.runtimeState : "exited", root.language), name: "State"},
                {label: "CPU", value: format.percent(root.details.cpuPercent), name: "Cpu"},
                {label: root.tr(msg.CONSOLE_MEMORY), value: format.memory(root.details.memoryBytes, "MiB"), name: "Memory"},
                {label: root.tr(msg.CONSOLE_UPTIME), value: format.uptime(root.details.uptimeSeconds), name: "Uptime"},
                {label: root.tr(msg.CONSOLE_PID), value: root.details.mainPid || "—", name: "Pid"},
                {label: root.tr(msg.CONSOLE_PROCESSES), value: root.details.processCount ?? "—", name: "Processes"}
            ]
            delegate: Column {
                required property var modelData
                width: (root.width - 20) / 2; height: 52; spacing: 2
                Text {
                    width: parent.width; text: modelData.label; textFormat: Text.PlainText
                    font.family: root.fontFamily; font.pixelSize: 18; color: root.colors.muted
                    elide: Text.ElideRight
                }
                Text {
                    objectName: "consoleDetails" + modelData.name
                    width: parent.width; text: modelData.value; textFormat: Text.PlainText
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
    Grid {
        width: parent.width; columns: 2; spacing: 8
        Repeater {
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
                border.width: selected ? 3 : 1
                border.color: selected ? root.colors.accent : root.colors.buttonBorder
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
