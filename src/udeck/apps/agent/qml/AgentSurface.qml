/*
[INPUT]: 依赖共享窗口、主题、Agent 控制器与 ACP 消息模型。
[OUTPUT]: 提供占满内容区的会话、设置中的 Agent 管理与对应按键提示。
[POS]: Agent 的内容视图。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../../qml" as Shared

Item {
    id: surface
    required property var host
    required property var colors
    readonly property var msg: controller.messageKeys
    readonly property bool editing: composer.activeFocus
    readonly property var state: host.state
    readonly property bool inSettings: state.page === "agent-settings"
    readonly property var attachments: state.attachments || []
    readonly property bool onboarding: !state.session && !state.workspace
    readonly property string startLabel: host.tr(state.hasInstalledAgent ? msg.AGENT_NEW : msg.AGENT_INSTALL_FIRST)
    readonly property string startIcon: state.hasInstalledAgent ? "plus-lg" : "download"
    readonly property int gutter: width <= 1000 ? 24 : 32
    readonly property bool promptReady: state.canSend && !composer.inputMethodComposing
        && (composer.text.trim().length > 0 || attachments.length > 0)
    readonly property var footerHints: inSettings ? [
        [["gamecube_button_color_a"], msg.ACTIONS, "accept"],
        [["gamecube_button_color_b"], msg.BACK, "back"]
    ] : editing ? [
        [["gamecube_button_color_a"], msg.AGENT_SEND, "accept", promptReady],
        [["gamecube_button_color_b"], msg.AGENT_LEAVE_PROMPT, "back"],
        [["keyboard_enter"], msg.AGENT_SEND, "accept", promptReady]
    ] : [
        [["gamecube_button_color_a"], transcript.canExpand ? transcript.readItem.actionLabel
            : state.turn ? msg.AGENT_STOP : state.canSend ? msg.AGENT_EDIT_PROMPT
            : state.session ? msg.AGENT_CONTINUE
            : state.hasInstalledAgent ? msg.AGENT_NEW : msg.AGENT_INSTALL_FIRST, "accept"],
        [["gamecube_button_color_b"], msg.BACK, "back"],
        [["gamecube_button_x"], msg.AGENT_HISTORY, "context", !state.busy],
        [["gamecube_button_y"], state.turn ? msg.AGENT_STOP : msg.ACTIONS, "quick-settings"]
    ].concat(transcript.count ? [[["gamecube_dpad"], msg.AGENT_READ_MESSAGES]] : [])
    property string draftSession: ""
    property var drafts: ({})

    onStateChanged: syncDraft()
    Component.onCompleted: syncDraft()

    function syncDraft() {
        if (!composer || draftSession === (state.session || ""))
            return
        if (draftSession)
            drafts[draftSession] = composer.text
        draftSession = state.session || ""
        composer.text = drafts[draftSession] || ""
        transcript.latest()
    }

    function send() {
        if (promptReady && controller.sendPrompt(composer.text)) {
            composer.text = ""
            composer.focus = false
            host.focusInput()
            transcript.latest()
        }
    }

    function insertPrompt(text) {
        if (!state.canSend || state.menu.title)
            return
        composer.text = text
        composer.forceActiveFocus()
        composer.cursorPosition = composer.text.length
    }

    Connections {
        target: controller
        function onEditPrompt() {
            if (surface.state.canSend && !surface.state.menu.title)
                composer.forceActiveFocus()
        }
        function onSubmitPrompt() { surface.send() }
        function onLeavePrompt() { composer.focus = false; host.focusInput() }
        function onInsertPrompt(text) { surface.insertPrompt(text) }
        function onAcceptTranscript() {
            if (transcript.canExpand)
                transcript.readItem.activate()
            else
                controller.primarySessionAction()
        }
        function onScrollTranscript(delta) { transcript.read(delta) }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: surface.gutter
        anchors.topMargin: 10
        anchors.bottomMargin: 8
        spacing: 8
        visible: !surface.inSettings

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                visible: !surface.onboarding
                Layout.preferredWidth: 38
                Layout.preferredHeight: 38
                radius: 9
                color: colors.panel
                border.color: colors.divider
                AgentIcon {
                    anchors.centerIn: parent
                    name: surface.state.agentId || "chat-square-text"
                    size: 19
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: !surface.onboarding
                spacing: 2
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Text {
                        text: surface.state.agentName || ""
                        font.family: host.fontFamily
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        color: colors.text
                        textFormat: Text.PlainText
                    }
                    Rectangle {
                        Layout.preferredWidth: connection.implicitWidth + 16
                        Layout.preferredHeight: 22
                        radius: 5
                        color: surface.state.turn ? colors.selected : colors.panel
                        Row {
                            id: connection
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 5
                                height: 5
                                radius: width / 2
                                color: connectionLabel.color
                            }
                            Text {
                                id: connectionLabel
                                text: surface.state.connection || ""
                                font.family: host.fontFamily
                                font.pixelSize: 13
                                color: surface.state.connectionState === "ready" ? "#a7cea4"
                                    : surface.state.connectionState === "idle" ? colors.muted : colors.accent
                            }
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!surface.state.workspace
                    spacing: 8
                    AgentIcon { name: "folder2"; size: 15 }
                    Text {
                        Layout.fillWidth: true
                        text: surface.state.workspace || ""
                        font.family: host.fontFamily
                        font.pixelSize: 13
                        color: colors.muted
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                    }
                }
            }
            Item { Layout.fillWidth: true; visible: surface.onboarding }
            AgentButton {
                compact: true
                text: host.tr(msg.AGENT_HISTORY)
                glyph: "clock-history"
                colors: surface.colors
                fontFamily: host.fontFamily
                enabled: !surface.state.busy
                onActivated: controller.showHistory()
            }
            AgentButton {
                compact: true
                visible: !surface.onboarding
                text: surface.startLabel
                glyph: surface.startIcon
                colors: surface.colors
                fontFamily: host.fontFamily
                enabled: !surface.state.busy
                onActivated: controller.newSession()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 11
            color: surface.onboarding ? colors.background : colors.input
            border.width: surface.onboarding ? 0 : 1
            border.color: colors.divider

            ListView {
                id: transcript
                objectName: "agentTranscript"
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                spacing: 6
                model: controller.messages
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    palette: surface.colors.controls
                    onPressedChanged: {
                        if (pressed) {
                            transcript.readIndex = -1
                            transcript.follow = false
                        } else {
                            transcript.follow = transcript.atYEnd
                        }
                    }
                }
                property bool follow: true
                property int readIndex: -1
                property Item readItem: null
                readonly property bool canExpand: !surface.editing && readItem !== null && !!readItem.actionLabel

                function latest() {
                    readIndex = -1
                    follow = true
                    positionViewAtEnd()
                }

                function toggleDetails(item) {
                    follow = false
                    readIndex = item.index
                    item.expanded = !item.expanded
                    Qt.callLater(revealSelection)
                }

                function revealSelection() {
                    if (readItem && readItem.height <= height)
                        positionViewAtIndex(readIndex, ListView.Contain)
                }

                function read(delta) {
                    if (!delta) {
                        latest()
                        return
                    }
                    if (!count)
                        return
                    forceLayout()
                    if (follow)
                        positionViewAtEnd()
                    const visibleIndex = atYEnd ? count - 1 : Math.max(0, indexAt(1, contentY + spacing + 1))
                    const from = readIndex < 0 ? visibleIndex : readIndex
                    const item = itemAtIndex(from)
                    if (item && item.height > height) {
                        const lower = Math.max(originY, item.y)
                        const upper = Math.max(lower, item.y + item.height - height)
                        if ((delta < 0 && contentY > lower + 1) || (delta > 0 && contentY < upper - 1)) {
                            follow = false
                            readIndex = from
                            contentY = Math.max(lower, Math.min(upper, contentY + delta * height * 0.65))
                            return
                        }
                    }
                    if (delta > 0 && from >= count - 1) {
                        if (readIndex < 0 && item && item.actionLabel) {
                            follow = false
                            readIndex = from
                        } else {
                            latest()
                        }
                        return
                    }
                    follow = false
                    readIndex = Math.max(0, Math.min(count - 1, from + delta))
                    positionViewAtIndex(readIndex, ListView.Contain)
                }

                Shared.FocusFrame {
                    parent: transcript.contentItem
                    target: transcript.readItem
                    active: transcript.visible && host.active && !surface.editing && !surface.state.menu.title
                    accent: colors.accent
                    reducedMotion: controller.reducedMotion
                }

                onMovementStarted: { readIndex = -1; follow = false }
                onMovementEnded: follow = atYEnd
                onContentHeightChanged: if (follow) Qt.callLater(restoreEnd)
                onHeightChanged: if (follow) Qt.callLater(restoreEnd)
                function restoreEnd() {
                    if (follow && !moving)
                        positionViewAtEnd()
                }

                Connections {
                    target: controller.messages
                    function onModelReset() {
                        transcript.latest()
                        Qt.callLater(transcript.restoreEnd)
                    }
                    function onRowsInserted() { if (transcript.follow) Qt.callLater(transcript.restoreEnd) }
                    function onRowsRemoved(parent, first, last) {
                        if (transcript.readIndex > last)
                            transcript.readIndex -= last - first + 1
                        else if (transcript.readIndex >= first)
                            transcript.readIndex = -1
                    }
                }

                delegate: RowLayout {
                    id: entry
                    required property string entryKind
                    required property string entryText
                    required property string entryStatus
                    required property string entryDetail
                    required property var entryBlocks
                    required property bool entryStreaming
                    required property string entryOrigin
                    required property int index
                    objectName: "agentReplyRow-" + entryKind
                    readonly property var blocks: entryBlocks || []
                    readonly property var actions: (blocks || []).filter(block => entry.isActionEnabled(block))
                    readonly property int actionCount: actions ? actions.length : 0
                    readonly property bool streaming: entryStreaming
                    readonly property bool reading: index === transcript.readIndex
                    readonly property bool fromUser: entryKind === "user"
                    readonly property bool fromAgent: entryKind === "agent"
                    readonly property bool thought: entryKind === "thought"
                    readonly property bool notice: entryKind === "notice"
                    readonly property bool messageRow: fromUser || fromAgent
                    readonly property bool awaitingUser: entryStatus === "pending"
                        && ["request", "permission", "elicitation"].includes(entryKind)
                    readonly property bool inlineDecision: awaitingUser && actionCount === 2 && blocks.length === 2
                    readonly property bool failed: ["failed", "error", "refusal"].includes(entryStatus)
                    readonly property color statusColor: failed ? colors.error
                        : entryStatus === "completed" || entryStatus === "end_turn" ? "#a7cea4"
                        : streaming || awaitingUser || ["in_progress", "running", "warning"].includes(entryStatus)
                            ? colors.accent : colors.muted
                    readonly property bool collapsible: thought || entryKind === "tool" || entryKind === "compaction"
                        || entryKind === "subagent" || entryKind === "commands" || entryKind === "config"
                        || entryKind === "remote_sessions" || entryKind === "terminal" || notice
                        || entryKind === "session_info" || entryKind === "usage"
                    readonly property bool hasDetails: collapsible &&
                        (!!entryDetail || blocks.length > 0 || (thought && !!entryText))
                    readonly property bool collapsed: hasDetails && !expanded
                    readonly property bool completedTurn: entryKind === "result" && entryStatus === "end_turn"
                        && !entryDetail && blocks.length === 0
                    readonly property bool compactRow: collapsed || completedTurn
                    readonly property bool summarized: !!entryText && (completedTurn || (collapsed && !thought))
                    readonly property int verticalPadding: compactRow ? 3 : 8
                    property Item audioItem: null
                    readonly property string actionLabel: hasDetails && !expanded ? msg.AGENT_DETAILS
                        : actionCount ? msg.ACTIONS
                        : audioItem ? audioItem.audioActionLabel : hasDetails ? msg.AGENT_HIDE_DETAILS : ""
                    readonly property string sender: ({
                        user: host.tr(msg.AGENT_ME),
                        agent: surface.state.agentName,
                        thought: host.tr(msg.AGENT_THOUGHT),
                        tool: host.tr(msg.AGENT_TOOL),
                        plan: host.tr(msg.AGENT_PLAN),
                        attachment: host.tr(msg.AGENT_ATTACHMENT),
                        notice: host.tr(msg.AGENT_UPDATE),
                        compaction: host.tr(msg.AGENT_COMPACTION),
                        subagent: host.tr(msg.AGENT_SUBAGENT),
                        commands: host.tr(msg.AGENT_PROTOCOL_COMMANDS),
                        mode: host.tr(msg.AGENT_PROTOCOL_MODE),
                        config: host.tr(msg.AGENT_PROTOCOL_CONFIG),
                        session_info: host.tr(msg.AGENT_PROTOCOL_SESSION),
                        usage: host.tr(msg.AGENT_PROTOCOL_USAGE),
                        result: host.tr(msg.AGENT_PROTOCOL_RESULT),
                        request: host.tr(msg.AGENT_PROTOCOL_REQUEST),
                        permission: host.tr(msg.AGENT_PERMISSION),
                        auth: host.tr(msg.AGENT_PROTOCOL_AUTH),
                        remote_sessions: host.tr(msg.AGENT_PROTOCOL_REMOTE_SESSIONS),
                        terminal: host.tr(msg.AGENT_PROTOCOL_TERMINAL),
                        elicitation: host.tr(msg.AGENT_PROTOCOL_ELICITATION),
                        child: host.tr(msg.AGENT_PROTOCOL_CHILD),
                        info: host.tr(msg.AGENT_UPDATE)
                    })[entryKind] || ""
                    readonly property string heading: summarized
                        ? (notice || completedTurn ? entryText : sender + "  ·  " + entryText)
                        : sender
                    readonly property string toolStatus: ({
                        pending: host.tr(msg.AGENT_TOOL_PENDING),
                        in_progress: host.tr(msg.RUNNING),
                        completed: host.tr(msg.DONE),
                        failed: host.tr(msg.AGENT_TOOL_FAILED),
                        cancelled: host.tr(msg.AGENT_CANCELLED),
                        running: host.tr(msg.RUNNING),
                        idle: host.tr(msg.AGENT_IDLE)
                    })[entryStatus] || entryStatus

                    width: transcript.width - 12
                    spacing: 10
                    property bool expanded: false

                    function refreshAudio() {
                        for (let i = 0; i < replyBlocks.count; i++) {
                            const block = replyBlocks.itemAt(i)
                            if (block && block.hasAudio) {
                                audioItem = block
                                return
                            }
                        }
                        audioItem = null
                    }

                    function activate() {
                        if (hasDetails && !expanded)
                            transcript.toggleDetails(entry)
                        else if (actionCount === 1)
                            invokeAction(actions[0])
                        else if (actionCount > 1)
                            controller.runSessionAction("choices", {actions: actions, title: sender})
                        else if (audioItem)
                            audioItem.toggleAudio()
                        else if (hasDetails)
                            transcript.toggleDetails(entry)
                    }

                    function invokeAction(block) {
                        if (isActionEnabled(block))
                            controller.runSessionAction(block.action, block.arguments || {})
                    }

                    function isActionEnabled(block) {
                        if (block.type !== "action" || !block.action || block.disabled)
                            return false
                        const connection = surface.state.connectionState
                        if (["mode", "config", "command"].indexOf(block.action) >= 0)
                            return surface.state.canSend
                        return connection !== "idle"
                    }
                    onReadingChanged: {
                        if (reading)
                            transcript.readItem = entry
                        else if (transcript.readItem === entry)
                            transcript.readItem = null
                    }
                    Component.onCompleted: if (reading) transcript.readItem = entry

                    Rectangle {
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: entry.compactRow ? 3 : 7
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: entry.completedTurn ? 20 : 28
                        radius: 7
                        color: entry.reading || entry.fromAgent || entry.awaitingUser ? colors.selected
                            : entry.compactRow ? "transparent" : colors.header
                        AgentIcon {
                            anchors.centerIn: parent
                            name: entry.fromAgent ? (surface.state.agentId || "chat-square-text")
                                  : ({user: "person", tool: "terminal", plan: "list-check",
                                      thought: "clock-history", attachment: "folder2",
                                      compaction: "list-check", subagent: "person", child: "person",
                                      commands: "terminal", config: "three-dots", mode: "three-dots",
                                      usage: "clock-history", terminal: "terminal",
                                      auth: "box-arrow-in-right", remote_sessions: "clock-history",
                                      result: "list-check"})[entry.entryKind] || "chat-square-text"
                            size: entry.compactRow ? 14 : 16
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: message.implicitHeight + 2 * entry.verticalPadding
                        radius: 9
                        color: entry.compactRow ? "transparent" : entry.awaitingUser ? colors.selected
                            : entry.fromAgent ? colors.panel : colors.header
                        border.width: entry.compactRow ? 0 : 1
                        border.color: entry.awaitingUser ? colors.toastBorder : colors.rowBorder

                        ColumnLayout {
                            id: message
                            width: parent.width - 24
                            x: 12
                            y: entry.verticalPadding
                            spacing: 5

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 9
                                Text {
                                    Layout.fillWidth: true
                                    text: [entry.entryOrigin, entry.heading].filter(Boolean).join("  ·  ")
                                    color: entry.fromAgent ? colors.accent
                                        : entry.notice && entry.summarized ? entry.statusColor : colors.muted
                                    font.family: host.fontFamily
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                }
                                Rectangle {
                                    visible: !!statusLabel.text
                                    Layout.preferredWidth: Math.min(statusLabel.implicitWidth + 14, 148)
                                    Layout.preferredHeight: 22
                                    radius: 5
                                    color: entry.failed ? colors.errorSurface : colors.panel
                                    Text {
                                        id: statusLabel
                                        anchors.fill: parent
                                        anchors.leftMargin: 7
                                        anchors.rightMargin: 7
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                        text: entry.streaming ? host.tr(msg.AGENT_RUNNING)
                                            : entry.entryKind === "result" ? "" : entry.toolStatus
                                        color: entry.statusColor
                                        font.family: host.fontFamily
                                        font.pixelSize: 13
                                        textFormat: Text.PlainText
                                    }
                                }
                                AgentButton {
                                    visible: entry.hasDetails
                                    Layout.preferredHeight: 27
                                    text: host.tr(entry.expanded ? msg.AGENT_HIDE_DETAILS : msg.AGENT_DETAILS)
                                    glyph: "chevron-right"
                                    compact: true
                                    colors: surface.colors
                                    fontFamily: host.fontFamily
                                    onActivated: transcript.toggleDetails(entry)
                                }
                            }
                            AgentReplyText {
                                Layout.fillWidth: true
                                visible: !!sourceText && !entry.summarized && (!entry.thought || entry.expanded)
                                sourceText: entry.entryText
                                color: entry.entryStatus === "refusal" ? colors.error : colors.text
                                font.family: host.fontFamily
                                font.pixelSize: entry.messageRow ? 19 : 17
                                codeSurface: colors.panel
                                codeInk: colors.artText
                                markdown: entry.fromAgent || entry.thought || entry.entryKind === "plan"
                                streaming: entry.streaming
                                animate: transcript.visible && host.active && transcript.follow
                                    && (!entry.thought || entry.expanded) && !controller.reducedMotion
                            }
                            Repeater {
                                id: replyBlocks
                                model: entry.inlineDecision || (entry.collapsible && !entry.expanded) ? [] : entry.blocks
                                onItemAdded: Qt.callLater(entry.refreshAudio)
                                onItemRemoved: Qt.callLater(entry.refreshAudio)
                                delegate: AgentReplyBlock {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    value: modelData
                                    actionEnabled: entry.isActionEnabled(modelData)
                                    clip: entry.index + ":" + index
                                    host: surface.host
                                    colors: surface.colors
                                    onActivated: entry.invokeAction(modelData)
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: (!entry.collapsible || entry.expanded) && !!entry.entryDetail
                                text: entry.entryDetail
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                color: colors.muted
                                font.family: ["terminal", "tool"].includes(entry.entryKind) ? "monospace" : host.fontFamily
                                font.pixelSize: 15
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                visible: entry.inlineDecision
                                spacing: 8
                                Item { Layout.fillWidth: true }
                                Repeater {
                                    model: entry.inlineDecision ? entry.actions : []
                                    delegate: AgentButton {
                                        required property var modelData
                                        text: modelData.text
                                        primary: modelData.arguments.decision === "accept"
                                        compact: true
                                        colors: surface.colors
                                        fontFamily: host.fontFamily
                                        onActivated: entry.invokeAction(modelData)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            AgentButton {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.rightMargin: 16
                anchors.bottomMargin: 6
                visible: !transcript.follow && !transcript.atYEnd
                compact: true
                text: host.tr(msg.AGENT_LATEST)
                glyph: "chevron-right"
                colors: surface.colors
                fontFamily: host.fontFamily
                onActivated: transcript.latest()
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 36, 520)
                spacing: 14
                visible: transcript.count === 0

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 64
                    radius: 15
                    color: colors.selected
                    AgentIcon {
                        anchors.centerIn: parent
                        name: "chat-square-text"
                        size: 31
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: host.tr(msg.AGENT_START_TITLE)
                    font.family: host.fontFamily
                    font.pixelSize: 29
                    color: colors.text
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    Layout.fillWidth: true
                    text: host.tr(msg.AGENT_START_BODY)
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    color: colors.muted
                    font.family: host.fontFamily
                    font.pixelSize: 18
                }
                AgentButton {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 3
                    visible: surface.onboarding
                    enabled: !surface.state.busy
                    text: surface.startLabel
                    glyph: surface.startIcon
                    primary: true
                    colors: surface.colors
                    fontFamily: host.fontFamily
                    onActivated: controller.newSession()
                }
            }
        }

        RowLayout {
            visible: surface.attachments.length > 0
            Layout.fillWidth: true
            spacing: 8

            AgentIcon { name: "folder2"; size: 15 }

            Text {
                Layout.fillWidth: true
                text: surface.attachments.join("  ·  ")
                font.family: host.fontFamily
                font.pixelSize: 15
                color: colors.muted
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            AgentButton {
                visible: surface.state.canSend
                compact: true
                text: host.tr(msg.REMOVE)
                colors: surface.colors
                fontFamily: host.fontFamily
                onActivated: controller.runSessionAction("choices", {
                    title: host.tr(msg.REMOVE),
                    actions: surface.attachments.map((name, index) => ({
                        text: name, action: "remove_attachment", arguments: {index: index}
                    }))
                })
            }
        }

        Rectangle {
            id: composerBar
            objectName: "agentComposerBar"
            visible: surface.state.session !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            radius: 10
            color: composer.activeFocus ? colors.header : colors.input
            border.color: composer.activeFocus ? colors.accent : colors.border

            TextField {
                id: composer
                objectName: "agentPrompt"
                property var inputController: controller
                anchors.left: parent.left
                anchors.right: composerAction.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: 1
                anchors.rightMargin: 8
                enabled: surface.state.canSend
                placeholderText: host.tr(surface.editing ? msg.AGENT_PROMPT : msg.AGENT_EDIT_PROMPT)
                selectByMouse: true
                color: colors.text
                palette: surface.colors.controls
                font.family: host.fontFamily
                font.pixelSize: 19
                leftPadding: 12
                rightPadding: 0
                verticalAlignment: TextInput.AlignVCenter
                background: null
                Keys.onPressed: function(event) {
                    if (inputMethodComposing)
                        return
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (!event.isAutoRepeat)
                            surface.send()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Escape) {
                        composer.focus = false
                        host.focusInput()
                        event.accepted = true
                    }
                }
            }
            AgentButton {
                id: composerAction
                objectName: "agentComposerAction"
                anchors.right: composerBar.right
                anchors.rightMargin: 4
                anchors.verticalCenter: composerBar.verticalCenter
                compact: true
                enabled: surface.state.connectionState === "sending" || surface.promptReady
                    || (!surface.state.busy && !surface.state.canSend)
                text: host.tr(surface.state.turn ? msg.AGENT_STOP : surface.state.canSend ? msg.AGENT_SEND
                                                                                          : msg.AGENT_CONTINUE)
                glyph: surface.state.turn ? "stop-fill" : surface.state.canSend ? "send" : "chevron-right"
                primary: surface.promptReady
                destructive: surface.state.turn
                colors: surface.colors
                fontFamily: host.fontFamily
                onActivated: {
                    if (surface.state.turn)
                        controller.stopTurn()
                    else if (surface.state.canSend)
                        surface.send()
                    else
                        controller.resumeSession()
                }
            }
        }

    }

    AgentManage {
        anchors.fill: parent
        anchors.margins: surface.gutter
        anchors.topMargin: 18
        host: surface.host
        colors: surface.colors
        visible: surface.inSettings
    }
}
