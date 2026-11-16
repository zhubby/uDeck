/*
[INPUT]: 依赖桌面的减少动画开关。
[OUTPUT]: 提供焦点、弹窗、切页、提示和补位的统一时长。
[POS]: 视图共用的动效令牌，不参与输入或启动调度。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

QtObject {
    property bool reducedMotion: false
    readonly property int focus: reducedMotion ? 0 : 90
    readonly property int enter: reducedMotion ? 0 : 150
    readonly property int leave: reducedMotion ? 0 : 110
    readonly property int page: reducedMotion ? 0 : 140
    readonly property int press: reducedMotion ? 0 : 80
    readonly property int notice: reducedMotion ? 0 : 120
    readonly property int artwork: reducedMotion ? 0 : 120
    readonly property int reflow: reducedMotion ? 0 : 140
}
