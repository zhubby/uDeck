/*
[INPUT]: 依赖 ListView/GridView 的当前代理、边界和可见状态。
[OUTPUT]: 选择改变时立即停止旧滚动，再定位十二像素安全区。
[POS]: 焦点视图共用的滚动协调器；不改变选择或输入归属。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: root
    property var view: null
    property bool active: true
    property bool reducedMotion: false
    readonly property bool animating: scroll.running
    readonly property real safeInset: 12
    property bool ready: false
    property bool immediatePending: false
    visible: false
    MotionTimings { id: motion; reducedMotion: root.reducedMotion }

    function schedule(immediate) {
        if (!ready || !active) return
        immediatePending = immediatePending || !!immediate
        Qt.callLater(synchronize)
    }
    function synchronize() {
        const immediate = immediatePending
        immediatePending = false
        ensureVisible(immediate)
    }
    function ensureVisible(immediate = false) {
        if (!ready || !active || !view || view.currentIndex < 0 || !view.count) return
        let item = view.currentItem
        if (!item) {
            scroll.stop()
            view.positionViewAtIndex(view.currentIndex, ListView.Contain)
            item = view.currentItem
            if (!item) return
            immediate = true
        }
        const minimumX = view.originX - view.leftMargin
        const minimumY = view.originY - view.topMargin
        const maximumX = Math.max(minimumX, view.originX + view.contentWidth - view.width + view.rightMargin)
        const maximumY = Math.max(minimumY, view.originY + view.contentHeight - view.height + view.bottomMargin)
        let nextX = view.contentX
        let nextY = view.contentY
        if (item.x < nextX + safeInset) nextX = item.x - safeInset
        else if (item.x + item.width > nextX + view.width - safeInset)
            nextX = item.x + item.width - view.width + safeInset
        if (item.y < nextY + safeInset) nextY = item.y - safeInset
        else if (item.y + item.height > nextY + view.height - safeInset)
            nextY = item.y + item.height - view.height + safeInset
        nextX = Math.max(minimumX, Math.min(maximumX, nextX))
        nextY = Math.max(minimumY, Math.min(maximumY, nextY))
        if (scroll.running && Math.abs(moveX.to - nextX) < 0.1 && Math.abs(moveY.to - nextY) < 0.1
                && !immediate && !reducedMotion) return
        scroll.stop()
        if (immediate || reducedMotion) {
            view.contentX = nextX
            view.contentY = nextY
        } else if (Math.abs(view.contentX - nextX) > 0.1 || Math.abs(view.contentY - nextY) > 0.1) {
            moveX.to = nextX; moveY.to = nextY
            scroll.start()
        }
    }
    onActiveChanged: {
        scroll.stop()
        if (active) schedule(true)
    }
    onReducedMotionChanged: if (reducedMotion) ensureVisible(true)
    onViewChanged: schedule(true)
    Component.onCompleted: { ready = true; schedule(true) }
    Connections {
        target: root.view
        ignoreUnknownSignals: true
        function onCurrentIndexChanged() {
            scroll.stop()
            root.schedule(false)
        }
        function onCurrentItemChanged() { root.schedule(false) }
        function onWidthChanged() { root.schedule(true) }
        function onHeightChanged() { root.schedule(true) }
        function onCountChanged() { root.schedule(false) }
        function onContentWidthChanged() { root.schedule(false) }
        function onContentHeightChanged() { root.schedule(false) }
    }
    Connections {
        target: root.view ? root.view.currentItem : null
        ignoreUnknownSignals: true
        function onXChanged() { root.schedule(false) }
        function onYChanged() { root.schedule(false) }
        function onWidthChanged() { root.schedule(true) }
        function onHeightChanged() { root.schedule(true) }
    }
    ParallelAnimation {
        id: scroll
        NumberAnimation { id: moveX; target: root.view; property: "contentX"; duration: motion.scroll; easing.type: Easing.OutCubic }
        NumberAnimation { id: moveY; target: root.view; property: "contentY"; duration: motion.scroll; easing.type: Easing.OutCubic }
    }
}
