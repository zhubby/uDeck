/*
[INPUT]: 依赖回复文本、流式状态和共享主题。
[OUTPUT]: 提供按文字边界吐字、文本选择和带代码样式的安全 Markdown 排版。
[POS]: 会话正文渲染层。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

TextEdit {
    id: reply
    required property string sourceText
    property bool markdown: false
    property bool animate: false
    property bool streaming: false
    property color codeSurface: "transparent"
    property color codeInk: color
    property int displayedLength: 0
    property bool ready: false
    readonly property bool revealing: animate && (streaming || displayedLength < sourceText.length)
    readonly property bool showingRaw: !markdown || revealing

    objectName: "agentReplyText"
    readOnly: true
    selectByMouse: true
    activeFocusOnPress: false
    wrapMode: TextEdit.Wrap
    textFormat: showingRaw ? TextEdit.PlainText : TextEdit.RichText
    text: showingRaw ? sourceText.slice(0, displayedLength) : formatted(sourceText)

    function updateReveal() {
        if (!ready)
            return
        if (!animate || (!streaming && displayedLength === 0) || displayedLength > sourceText.length)
            displayedLength = sourceText.length
        else if (sourceText.length - displayedLength > 180)
            advance(sourceText.length - displayedLength - 100)
    }

    function advance(amount) {
        let end = Math.min(sourceText.length, displayedLength + amount)
        // 将代理对、变体选择符、肤色修饰符和连接符留在同一帧。
        while (end < sourceText.length) {
            const next = sourceText.codePointAt(end)
            const previous = sourceText.charCodeAt(end - 1)
            const combined = (next >= 0xdc00 && next <= 0xdfff) ||
                (next >= 0x0300 && next <= 0x036f) || (next >= 0x1f3fb && next <= 0x1f3ff) ||
                next === 0xfe0f || next === 0x200d || previous === 0x200d ||
                (previous === 0x000d && next === 0x000a)
            if (!combined)
                break
            end += next > 0xffff ? 2 : 1
        }
        displayedLength = end
    }

    function escapeHtml(value) {
        return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    function inlineMarkup(value) {
        return escapeHtml(value).replace(/`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)/g,
            function(match, code, strong, label, url) {
                if (code !== undefined)
                    return "<code style='color:" + codeInk + "; background-color:" + codeSurface + "'>"
                        + code + "</code>"
                if (strong !== undefined)
                    return "<strong>" + strong + "</strong>"
                return label + " (" + url + ")"
            })
    }

    function codeBlock(lines) {
        return "<pre style='font-family:monospace; margin-top:6px; margin-bottom:6px; color:" + codeInk
            + "; background-color:" + codeSurface + "'>" + escapeHtml(lines.join("\n")) + "</pre>"
    }

    function formatted(value) {
        // 只生成此组件定义的标记。回复中的 HTML 和图片链接以文字显示。
        const lines = value.split(/\r?\n/)
        const output = []
        let fence = ""
        let content = []
        let paragraph = []
        for (const line of lines) {
            const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/)
            const heading = line.match(/^(#{1,6})\s+(.+)$/)
            if (fence && marker && marker[1][0] === fence[0] && marker[1].length >= fence.length
                && !marker[2].trim()) {
                output.push(codeBlock(content))
                content = []
                fence = ""
            } else if (fence) {
                content.push(line)
            } else if (marker) {
                if (paragraph.length)
                    output.push("<p>" + paragraph.splice(0).join("<br/>") + "</p>")
                fence = marker[1]
            } else if (heading) {
                if (paragraph.length)
                    output.push("<p>" + paragraph.splice(0).join("<br/>") + "</p>")
                output.push("<p style='margin-top:8px; margin-bottom:4px; font-size:"
                    + (font.pixelSize + (heading[1].length < 3 ? 3 : 1)) + "px'><strong>"
                    + inlineMarkup(heading[2]) + "</strong></p>")
            } else if (!line.trim()) {
                if (paragraph.length)
                    output.push("<p>" + paragraph.splice(0).join("<br/>") + "</p>")
            } else if (/^\s*[-*+]\s+/.test(line)) {
                paragraph.push("• " + inlineMarkup(line.replace(/^\s*[-*+]\s+/, "")))
            } else {
                paragraph.push(inlineMarkup(line))
            }
        }
        if (fence)
            output.push(codeBlock(content))
        if (paragraph.length)
            output.push("<p>" + paragraph.join("<br/>") + "</p>")
        return output.join("")
    }

    onSourceTextChanged: updateReveal()
    onStreamingChanged: updateReveal()
    onAnimateChanged: updateReveal()
    Component.onCompleted: {
        ready = true
        updateReveal()
    }

    Timer {
        interval: 24
        running: reply.ready && reply.revealing
                 && reply.displayedLength < reply.sourceText.length
        repeat: true
        onTriggered: {
            const remaining = reply.sourceText.length - reply.displayedLength
            reply.advance(Math.max(1, Math.ceil(remaining / (reply.streaming ? 10 : 4))))
        }
    }
}
