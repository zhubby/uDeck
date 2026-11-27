/*
[INPUT]: 依赖共享应用按钮和 Agent 本地图标。
[OUTPUT]: 为共享按钮配置 Agent 图标、重点操作和停止样式。
[POS]: 会话与管理页的按钮适配。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import "../../common/qml" as Suite

Suite.SuiteButton {
    id: button
    property string glyph: ""
    property bool primary: false
    property bool destructive: false

    disabled: !enabled
    selected: primary
    color: destructive ? colors.errorSurface : selected ? colors.buttonSelected : colors.button
    border.color: destructive ? colors.error : selected ? colors.accent : colors.buttonBorder
    leadingIcon: glyph ? icon : null

    Component {
        id: icon
        AgentIcon { name: button.glyph; size: button.compact ? 17 : 20 }
    }
}
