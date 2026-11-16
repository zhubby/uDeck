/*
[INPUT]: 依赖桌面翻译接口和 Console 消息标识。
[OUTPUT]: 提供状态、CPU、内存和存活时间的统一显示格式。
[POS]: Console 列表与详情共用的无状态格式组件。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

QtObject {
    function percent(value) { return value === null || value === undefined ? "—" : Number(value).toFixed(1) + "%" }
    function memory(value, unit) {
        if (value === null || value === undefined || value < 0) return "—"
        return unit === "GiB" ? (value / 1073741824).toFixed(1) + " GiB" : Math.round(value / 1048576) + " MiB"
    }
    function uptime(value) {
        if (value === null || value === undefined) return "—"
        const total = Math.floor(value)
        function pad(n) { return String(n).padStart(2, "0") }
        const hours = Math.floor(total / 3600)
        if (hours >= 24) return Math.floor(hours / 24) + "d " + pad(hours % 24) + ":" + pad(Math.floor(total / 60) % 60)
        return pad(hours) + ":" + pad(Math.floor(total / 60) % 60) + ":" + pad(total % 60)
    }
    function state(value, language) {
        const msg = controller.messageKeys
        return controller.translate(value === "playing" ? msg.CONSOLE_PLAYING : value === "paused" ? msg.CONSOLE_PAUSED
            : value === "exiting" ? msg.CONSOLE_EXITING : value === "exited" ? msg.CONSOLE_CLOSED : msg.CONSOLE_RUNNING, language)
    }
}
