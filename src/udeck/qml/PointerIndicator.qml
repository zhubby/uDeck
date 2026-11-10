import QtQuick

Item {
    id: layer
    property QtObject cursor: null
    required property QtObject colors
    visible: cursor !== null && cursor.visible
    enabled: false

    Rectangle {
        id: orb
        objectName: "pointerOrb"
        x: layer.cursor ? layer.cursor.position.x - width / 2 : 0
        y: layer.cursor ? layer.cursor.position.y - height / 2 : 0
        width: layer.cursor ? layer.cursor.diameter : 18
        height: width
        radius: width / 2
        antialiasing: true
        border.width: 1
        border.color: layer.colors.accentText
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.lighter(layer.colors.accent, 1.35) }
            GradientStop { position: 0.5; color: layer.colors.accent }
            GradientStop { position: 1; color: Qt.darker(layer.colors.accent, 1.18) }
        }

        Rectangle {
            x: 4
            y: 3
            width: 5
            height: 3
            radius: 2
            color: "#aaffffff"
            antialiasing: true
        }
    }
}
