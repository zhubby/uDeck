/*
[INPUT]: 依赖 ACP 回复块、协议操作和共享应用主题。
[OUTPUT]: 显示计划状态、差异面板、媒体引用和协议操作。
[POS]: 会话消息的结构化内容。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: block
    required property var value
    required property var host
    required property var colors
    required property string clip
    property bool actionEnabled: false
    signal activated()
    readonly property var msg: controller.messageKeys
    readonly property string kind: value.type || ""
    readonly property string path: value.path || ""
    readonly property string reference: value.uri || (path && value.line ? path + ":" + value.line : path)
        || value.terminalId || value.sessionId || ""
    readonly property string mime: value.mimeType || (value.resource ? value.resource.mimeType : "") || ""
    readonly property string imageData: mime.match(/^image\/(png|jpeg|gif|webp)$/) &&
        typeof value.data === "string" && value.data.length <= 2800000 &&
        /^[A-Za-z0-9+/]+={0,2}$/.test(value.data) ? value.data : ""
    readonly property bool hasAudio: mime.startsWith("audio/") && !!value.data
    readonly property bool audioActive: controller.replyAudioClip === clip
    readonly property string audioActionLabel: audioActive ? msg.AGENT_AUDIO_STOP : msg.PLAY
    readonly property string title: (value.labelKey ? host.tr(value.labelKey) : value.title || value.name) || ({
        image: host.tr(msg.AGENT_IMAGE),
        audio: host.tr(msg.AGENT_AUDIO),
        resource: host.tr(msg.AGENT_RESOURCE),
        resource_link: host.tr(msg.AGENT_RESOURCE),
        terminal: host.tr(msg.AGENT_TERMINAL_OUTPUT),
        session: host.tr(msg.AGENT_SESSIONS),
        diff: host.tr(msg.AGENT_DIFF),
        location: "",
        usage: "",
        action: "",
        plan: value.text || "",
        text: "",
        content: ""
    })[kind] || ""
    readonly property string detailText: value.text || value.description ||
        (value.resource ? (value.resource.text || "") : "")
    readonly property string actionLabel: title || value.label || value.text || ""
    readonly property bool planStep: kind === "plan"
    readonly property string status: value.status || ""
    readonly property color statusInk: status === "completed" ? "#a7cea4"
        : status === "failed" ? colors.error
        : status === "in_progress" ? colors.accent : colors.muted
    spacing: 6

    function toggleAudio() {
        controller.toggleReplyAudio(clip, mime, value.data)
    }

    RowLayout {
        visible: block.kind !== "action" && !!block.title
        Layout.fillWidth: true
        spacing: 8
        Rectangle {
            visible: block.planStep
            Layout.preferredWidth: 17
            Layout.preferredHeight: 17
            radius: 5
            color: block.status === "in_progress" ? block.colors.selected : block.colors.input
            border.color: block.status === "pending" ? block.colors.track : block.statusInk

            Text {
                anchors.centerIn: parent
                visible: block.status === "completed"
                text: "✓"
                color: block.statusInk
                font.pixelSize: 13
            }
            Rectangle {
                anchors.centerIn: parent
                visible: block.status === "in_progress"
                width: 5
                height: 5
                radius: 2
                color: block.statusInk
            }
        }
        AgentIcon {
            visible: !block.planStep
            name: ({terminal: "terminal", diff: "folder2",
                    session: "chat-square-text",
                    image: "folder2", audio: "plug"})[block.kind] || "folder2"
            size: 16
        }
        Text {
            Layout.fillWidth: true
            text: block.title
            color: block.colors.text
            font.family: host.fontFamily
            font.pixelSize: 17
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }
        Rectangle {
            visible: !!statusLabel.text
            Layout.preferredWidth: statusLabel.implicitWidth + 16
            Layout.preferredHeight: 22
            radius: 5
            color: block.status === "in_progress" ? block.colors.selected : block.colors.input
            Text {
                id: statusLabel
                anchors.centerIn: parent
                text: ({
                    pending: host.tr(msg.AGENT_TOOL_PENDING),
                    in_progress: host.tr(msg.RUNNING),
                    completed: host.tr(msg.DONE),
                    failed: host.tr(msg.AGENT_TOOL_FAILED)
                })[block.status] || block.status
                color: block.statusInk
                font.family: host.fontFamily
                font.pixelSize: 13
                textFormat: Text.PlainText
            }
        }
        AgentButton {
            visible: block.hasAudio
            compact: true
            Layout.preferredHeight: 28
            text: host.tr(block.audioActionLabel)
            glyph: block.audioActive ? "stop-fill" : ""
            colors: block.colors
            fontFamily: host.fontFamily
            onActivated: block.toggleAudio()
        }
    }

    RowLayout {
        visible: block.kind === "action"
        Layout.fillWidth: true
        spacing: 8

        TextMetrics {
            id: actionMetrics
            text: block.actionLabel
            font.family: host.fontFamily
            font.pixelSize: 16
            elide: Qt.ElideRight
            elideWidth: Math.max(0, (actionDetail.text ? block.width * 0.54 : block.width) - 28)
        }
        AgentButton {
            visible: block.actionEnabled
            compact: true
            text: actionMetrics.elidedText
            Accessible.name: block.actionLabel
            primary: block.value.status === "selected"
            colors: block.colors
            fontFamily: host.fontFamily
            onActivated: block.activated()
        }
        Text {
            id: actionDetail
            Layout.fillWidth: true
            visible: !!text
            text: [block.actionEnabled ? "" : block.actionLabel,
                   block.value.detail || block.value.description].filter(Boolean).join("  ·  ")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            font.family: host.fontFamily
            font.pixelSize: 15
            color: block.colors.muted
        }
        Item {
            Layout.fillWidth: true
            visible: !actionDetail.visible
        }
    }

    Rectangle {
        visible: block.kind === "usage" && block.value.size > 0
        Layout.fillWidth: true
        Layout.maximumWidth: 420
        Layout.preferredHeight: 5
        radius: 2
        color: block.colors.divider

        Rectangle {
            width: parent.width * Math.max(0, Math.min(1, block.value.used / block.value.size))
            height: parent.height
            radius: parent.radius
            color: block.colors.accent
        }
    }

    TextEdit {
        visible: !!text
        Layout.fillWidth: true
        text: [block.reference, block.mime, block.value.byteSize ? block.value.byteSize + " B" : ""]
              .filter(Boolean).join("  ·  ")
        color: block.colors.muted
        font.family: host.fontFamily
        font.pixelSize: 15
        textFormat: TextEdit.PlainText
        readOnly: true
        selectByMouse: true
        activeFocusOnPress: false
        wrapMode: TextEdit.Wrap
    }

    Image {
        id: blockImage
        objectName: "agentReplyImage"
        readonly property bool decoded: status === Image.Ready
        visible: !!block.imageData && status !== Image.Error
        Layout.preferredWidth: Math.min(block.width, 500)
        Layout.preferredHeight: Math.min(240, implicitHeight)
        source: block.imageData ? "data:" + block.mime + ";base64," + block.imageData : ""
        sourceSize: Qt.size(500, 240)
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        cache: false
    }

    Text {
        visible: block.kind === "image" && (!block.imageData || blockImage.status === Image.Error)
        Layout.fillWidth: true
        text: host.tr(msg.AGENT_PREVIEW_UNAVAILABLE)
        color: block.colors.muted
        font.family: host.fontFamily
        font.pixelSize: 15
        wrapMode: Text.Wrap
    }

    Text {
        visible: (block.kind === "audio" && !block.hasAudio) || controller.replyAudioFailure === block.clip
        Layout.fillWidth: true
        text: host.tr(msg.AGENT_PREVIEW_UNAVAILABLE)
        color: block.colors.muted
        font.family: host.fontFamily
        font.pixelSize: 15
        wrapMode: Text.Wrap
    }

    Repeater {
        model: block.kind === "diff" ? [
            { label: msg.AGENT_DIFF_BEFORE, text: block.value.oldText, color: block.colors.error, sign: "−" },
            { label: msg.AGENT_DIFF_AFTER, text: block.value.newText, color: "#a7cea4", sign: "+" }
        ].filter(function(side) { return side.text !== undefined && side.text !== null }) : []
        delegate: Rectangle {
            id: side
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: diffBody.implicitHeight + 16
            radius: 7
            color: block.colors.input
            border.color: block.colors.divider
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 2
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: 6
                width: 2
                radius: 1
                color: side.modelData.color
            }
            ColumnLayout {
                id: diffBody
                x: 15
                y: 8
                width: parent.width - 27
                spacing: 4
                Text {
                    text: side.modelData.sign + "  " + host.tr(side.modelData.label)
                    color: side.modelData.color
                    font.family: host.fontFamily
                    font.weight: Font.DemiBold
                    font.pixelSize: 13
                    textFormat: Text.PlainText
                }
                AgentReplyText {
                    Layout.fillWidth: true
                    sourceText: side.modelData.text
                    color: block.colors.text
                    font.family: "monospace"
                    font.pixelSize: 15
                }
            }
        }
    }

    AgentReplyText {
        visible: !!sourceText
        Layout.fillWidth: true
        sourceText: ["plan", "diff", "action"].indexOf(block.kind) >= 0 ? "" : block.detailText
        color: block.colors.text
        font.family: host.fontFamily
        font.pixelSize: 17
    }
}
