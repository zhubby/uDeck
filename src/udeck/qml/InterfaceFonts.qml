// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

QtObject {
    id: fonts
    objectName: "interfaceFonts"
    property string language: "en"
    readonly property string family: language === "zh_CN" ? chinese.name : regular.name

    // Bundle the original fonts for consistent offline rendering. Explicit
    // bindings update existing Text and Controls when the language changes.
    readonly property FontLoader regular: FontLoader { source: "../fonts/SairaSemiCondensed-Regular.ttf" }
    readonly property FontLoader medium: FontLoader { source: "../fonts/SairaSemiCondensed-Medium.ttf" }
    readonly property FontLoader semibold: FontLoader { source: "../fonts/SairaSemiCondensed-SemiBold.ttf" }
    readonly property FontLoader bold: FontLoader { source: "../fonts/SairaSemiCondensed-Bold.ttf" }
    readonly property FontLoader chinese: FontLoader { source: "../fonts/LXGWWenKaiScreen.ttf" }
}
