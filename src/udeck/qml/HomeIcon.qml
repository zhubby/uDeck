import QtQuick

Image {
    id: icon
    required property string kind
    property color ink: "#edb866"
    readonly property var drawings: ({
        terminal: "M13 18L27 32L13 46M33 46H52",
        music: "M25 44V18L49 12V38M25 25L49 19M25 44A7 5 0 1 1 11 44A7 5 0 1 1 25 44M49 38A7 5 0 1 1 35 38A7 5 0 1 1 49 38",
        video: "M14 13H50Q54 13 54 17V47Q54 51 50 51H14Q10 51 10 47V17Q10 13 14 13ZM27 23L42 32L27 41Z",
        reader: "M32 17Q22 10 9 15V49Q22 44 32 51Q42 44 55 49V15Q42 10 32 17V51M16 23Q22 21 26 24M16 31Q22 29 26 32M38 24Q44 21 48 23M38 32Q44 29 48 31",
        emulator: "M19 19H45Q52 19 54 27L58 44Q59 51 53 51Q49 51 43 43H21Q15 51 11 51Q5 51 6 44L10 27Q12 19 19 19ZM16 31H28M22 25V37M42 28A2 2 0 1 1 38 28A2 2 0 1 1 42 28M50 35A2 2 0 1 1 46 35A2 2 0 1 1 50 35",
        settings: "M15 9V25M15 35V55M9 25H21V35H9ZM32 9V37M32 47V55M26 37H38V47H26ZM49 9V17M49 27V55M43 17H55V27H43Z"
    })
    source: "data:image/svg+xml;utf8," + encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><path fill='none' stroke='" + ink.toString() + "' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' d='" + (drawings[kind] || drawings.settings) + "'/></svg>")
    sourceSize.width: Math.ceil(width * 2)
    sourceSize.height: Math.ceil(height * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
}
