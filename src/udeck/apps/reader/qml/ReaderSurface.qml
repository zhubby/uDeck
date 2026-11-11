// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtWebEngine
import "../../../qml" as Shared
import "../../common/qml"

Item {
    id: surface
    required property var colors
    required property var host
    property var appState:host?host.state:({current:{},position:{}})
    property bool pdf:appState.current.format==="PDF"
    WebEngineProfile { id: bookProfile; offTheRecord:true; storageName:"" }
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            objectName: "readerDocumentHeader"
            Layout.fillWidth: true; Layout.preferredHeight: 36; color:surface.colors.panel
            RowLayout {
                anchors.fill:parent;anchors.leftMargin:20;anchors.rightMargin:20;spacing:16
                Text {
                    objectName: "readerBookTitle"
                    font.family: surface.host.fontFamily; Layout.fillWidth:true; Layout.minimumWidth:0
                    text:appState.current.title||"";color:surface.colors.text;font.pixelSize:18;elide:Text.ElideRight
                }
                Text {
                    objectName: "readerSectionTitle"
                    font.family: surface.host.fontFamily
                    Layout.maximumWidth:Math.min(220,surface.width*0.25)
                    text:surface.pdf?((appState.pdfPage+1)+" / "+appState.pdfPages+"  ·  "+(appState.pdfFit?(host?host.tr("Fit width"):""):Math.round(appState.pdfZoom*100)+"%")):(appState.readerLabel||"")
                    visible:text.length>0;color:surface.colors.muted;font.pixelSize:16;elide:Text.ElideRight
                }
                ProgressBar {
                    id: readingProgress; objectName: "readerProgress"
                    Layout.preferredWidth:surface.width<1000?120:160
                    Layout.preferredHeight:6;Layout.alignment:Qt.AlignVCenter
                    from:0;to:1;padding:0
                    value:surface.pdf?(appState.pdfPages>0?(appState.pdfPage+1)/appState.pdfPages:0):(appState.position.fraction||0)
                    Accessible.name:appState.current.title||""
                    background:Rectangle { implicitHeight:6;radius:3;color:surface.colors.border }
                    contentItem:Item {
                        implicitHeight:6
                        Rectangle { width:parent.width*readingProgress.position;height:parent.height;radius:3;color:surface.colors.accent }
                    }
                }
            }
        }
        Item {
            Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            Rectangle{anchors.fill:parent;color:surface.appState.backgroundColor||(surface.appState.dark?"#202426":"#d9d4c9")}
            Flickable {
                id: pdfView; anchors.fill:parent;visible:surface.pdf;clip:true
                contentWidth:Math.max(width,pdfImage.width+40);contentHeight:pdfImage.height+40
                boundsBehavior:Flickable.StopAtBounds
                Image {
                    id:pdfImage;x:20;y:20
                    width:(pdfView.width-40)*(appState.pdfFit?1:appState.pdfZoom)
                    height:width*(appState.pdfRatio||1.4)
                    source:surface.pdf&&appState.readerReady?"image://pdf/"+(appState.current.id||"")+"/"+appState.pdfRevision:""
                    sourceSize.width:Math.min(2800,Math.round(width*Screen.devicePixelRatio))
                    fillMode:Image.PreserveAspectFit
                    cache:false
                    Repeater {
                        model:appState.pdfHighlights||[]
                        delegate:Rectangle {
                            required property var modelData
                            x:modelData.x*pdfImage.width;y:modelData.y*pdfImage.height
                            width:modelData.width*pdfImage.width;height:modelData.height*pdfImage.height
                            color:"#80edb866";border.color:"#b88a3f";border.width:1
                        }
                    }
                }
                ScrollBar.vertical:ScrollBar{palette:surface.colors.controls;}
                ScrollBar.horizontal:ScrollBar{palette:surface.colors.controls;}
                onContentXChanged:controller.pdfPan(contentX,contentY)
                onContentYChanged:controller.pdfPan(contentX,contentY)
            }
            WebEngineView {
                id: book; anchors.fill:parent;visible:!surface.pdf;profile:bookProfile
                property string documentUrl:appState.readerUrl||"about:blank"
                url:"about:blank"
                onDocumentUrlChanged:if(url.toString()!==documentUrl)url=documentUrl
                focus:false
                settings.localContentCanAccessFileUrls:false
                settings.localContentCanAccessRemoteUrls:false
                settings.javascriptCanOpenWindows:false
                onJavaScriptConsoleMessage:function(level,message,line,source){controller.readerConsole(message);if(message.startsWith("UDECK_READER:"))controller.readerEvent(message.slice(13))}
                onNavigationRequested:function(request){if(request.isMainFrame&&request.url.toString()!=="about:blank"&&!request.url.toString().startsWith(appState.readerUrl.replace("index.html","")))request.reject()}
                onCertificateError:function(error){error.rejectCertificate()}
                onFeaturePermissionRequested:function(origin,feature){grantFeaturePermission(origin,feature,false)}
                onRenderProcessTerminated:function(status,code){controller.readerEvent(JSON.stringify({session:(appState.readerUrl||"").split("/")[3],type:"error",error:"Reading process ended ("+code+")"}))}
            }
        }
        Rectangle {
            visible:surface.pdf
            Layout.fillWidth:true;Layout.preferredHeight:32;color:surface.colors.panel
            Row {
                anchors.centerIn: parent; spacing: 20
                Shared.InputPrompt { keys: ["keyboard_arrows"]; label: host ? host.tr("Pan") : ""; fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 17 }
                Shared.InputPrompt { keys: ["gamecube_trigger_l", "/", "gamecube_trigger_r"]; label: host ? host.tr("Pages") : ""; fontFamily: surface.host.fontFamily; textColor: surface.colors.muted; fontSize: 17 }
            }
        }
    }
    Connections {
        target:controller
        function onWebAction(action,payload){
            const data=JSON.parse(payload)
            if(action==="pan") {
                const step=100
                if(data.direction==="left")pdfView.contentX=Math.max(0,pdfView.contentX-step)
                if(data.direction==="right")pdfView.contentX=Math.max(0,Math.min(pdfView.contentWidth-pdfView.width,pdfView.contentX+step))
                if(data.direction==="up")pdfView.contentY=Math.max(0,pdfView.contentY-step)
                if(data.direction==="down")pdfView.contentY=Math.max(0,Math.min(pdfView.contentHeight-pdfView.height,pdfView.contentY+step))
            } else book.runJavaScript("window.udeckReader && window.udeckReader("+JSON.stringify(action)+","+JSON.stringify(data.value)+","+JSON.stringify(data.session)+")")
        }
        function onPdfMoved(){Qt.callLater(function(){pdfView.contentX=appState.pdfX||0;pdfView.contentY=appState.pdfY||0})}
    }
    Component.onCompleted: Qt.callLater(function() {
        pdfView.contentX = appState.pdfX || 0
        pdfView.contentY = appState.pdfY || 0
        if (!surface.pdf && book.url.toString() !== book.documentUrl) book.url = book.documentUrl
    })
}
