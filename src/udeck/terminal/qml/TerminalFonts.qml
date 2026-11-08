import QtQuick

QtObject {
    property string language: "en"
    property var hostController: null
    property int pixelSize: 20
    readonly property string family: language === "zh_CN"
        ? (chinese.name || "LXGW WenKai Mono") : (regular.name || "JetBrains Mono")
    readonly property font contentFont: hostController && regular.status === FontLoader.Ready
        && bold.status === FontLoader.Ready && chinese.status === FontLoader.Ready
        && symbols.status === FontLoader.Ready
        ? hostController.terminalFont(language, pixelSize)
        : Qt.font({family: family, pixelSize: pixelSize})
    readonly property FontLoader regular: FontLoader { source: "../fonts/JetBrainsMono-Regular.ttf" }
    readonly property FontLoader bold: FontLoader { source: "../fonts/JetBrainsMono-Bold.ttf" }
    readonly property FontLoader chinese: FontLoader { source: "../fonts/LXGWWenKaiMono-Regular.ttf" }
    readonly property FontLoader symbols: FontLoader { source: "../fonts/SymbolsNerdFontMono-Regular.ttf" }
}
