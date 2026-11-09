// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

QtObject {
    id: colors
    objectName: "themeColors"
    property string theme: "classic"
    property string profile: "shell"
    readonly property bool dark: theme === "dark"
    readonly property color background: dark ? "#0B0E12" : profile === "apps" ? "#171b1d" : "#151719"
    readonly property color text: dark ? "#F5F2EB" : "#f1eee7"
    readonly property color muted: dark ? "#B6BDC7" : "#a8acae"
    readonly property color accent: "#edb866"
    readonly property color accentText: "#252019"
    readonly property color brandInk: dark ? accentText : "#25201a"
    readonly property color panel: dark ? "#14191F" : profile === "apps" ? "#252b2d" : "#202326"
    readonly property color header: dark ? panel : profile === "apps" ? "#202628" : "#202426"
    readonly property color footer: dark ? panel : "#1d2224"
    readonly property color selected: dark ? "#302719" : profile === "apps" ? "#393227" : "#302c25"
    readonly property color selectedText: dark ? text : "#d5c8b0"
    readonly property color selectedTab: dark ? selected : profile === "apps" ? "#383025" : profile === "terminal" ? "#303537" : "#30302b"
    readonly property color tabBorder: dark ? border : "#514937"
    readonly property color border: dark ? "#717D8A" : profile === "apps" ? "#42494a" : "#33373a"
    readonly property color rowBorder: dark ? border : "#303437"
    readonly property color divider: dark ? "#343D48" : profile === "apps" ? "#464b49" : "#363a3d"
    readonly property color headerDivider: dark ? divider : "#414448"
    readonly property color keyBorder: dark ? border : "#929694"
    readonly property color pointer: dark ? muted : "#828886"
    readonly property color signalInactive: "#606D7A"
    readonly property color dialog: dark ? "#1D242C" : profile === "apps" ? "#222729" : profile === "terminal" ? "#24292b" : "#222528"
    readonly property color dialogBorder: dark ? border : profile === "apps" ? "#68675f" : profile === "terminal" ? "#48504f" : "#62605a"
    readonly property color menuSelected: dark ? selected : profile === "apps" ? selected : profile === "terminal" ? "#3f4239" : "#393329"
    readonly property color input: dark ? background : profile === "apps" ? "#161b1d" : profile === "terminal" ? background : "#16191b"
    readonly property color inputBorder: dark ? border : "#6d6a5e"
    readonly property color button: dark ? panel : profile === "apps" ? "#292f31" : "#2c3033"
    readonly property color buttonSelected: dark ? selected : profile === "apps" ? "#3d3428" : "#3d3426"
    readonly property color buttonBorder: dark ? border : profile === "apps" ? "#454b4b" : "#505452"
    readonly property color track: dark ? border : "#444746"
    readonly property color rowTrack: dark ? border : "#454541"
    readonly property color toast: dark ? dialog : profile === "apps" ? "#363027" : "#343027"
    readonly property color toastBorder: dark ? border : profile === "apps" ? "#967c51" : "#92764b"
    readonly property color error: dark ? "#FFB4AB" : "#e3ac91"
    readonly property color errorSurface: dark ? "#361E22" : "#542e2a"
    readonly property color scrim: profile === "apps" ? "#b5000000" : profile === "terminal" ? "#b0000000" : "#b8000000"
    readonly property color videoControls: dark ? "#e61D242C" : "#d1171b1d"
    readonly property color artTint: "#18edb866"
    readonly property color artText: dark ? accent : "#e8cc9f"

    function artwork(kind) {
        const classic = {music:"#344749", video:"#42495a", reader:"#4e4535", emulator:"#384738"}
        const night = {music:"#193034", video:"#252c40", reader:"#3a2f1f", emulator:"#243426"}
        return (dark ? night : classic)[kind] || (dark ? panel : "#334346")
    }

    // Basic Qt Quick Controls otherwise inherit the platform's light palette.
    readonly property Palette controls: Palette {
        window: colors.dialog
        windowText: colors.text
        base: colors.input
        alternateBase: colors.panel
        text: colors.text
        button: colors.button
        buttonText: colors.text
        mid: colors.border
        dark: colors.track
        light: colors.border
        highlight: colors.accent
        highlightedText: colors.accentText
        placeholderText: colors.muted
        disabled.text: colors.muted
        disabled.buttonText: colors.muted
        disabled.highlight: colors.muted
    }
}
