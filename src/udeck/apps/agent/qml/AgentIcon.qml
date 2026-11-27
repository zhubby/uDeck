/*
[INPUT]: 依赖随包提供的操作图标和 Agent 标志。
[OUTPUT]: 按名称提供清晰的本地图标。
[POS]: 会话、管理和消息视图共用。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: icon
    required property string name
    property int size: 22
    implicitWidth: size
    implicitHeight: size

    Image {
        anchors.fill: parent
        source: icon.name ? Qt.resolvedUrl("icons/" + icon.name + ".svg") : ""
        sourceSize: Qt.size(icon.size * 2, icon.size * 2)
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
}
