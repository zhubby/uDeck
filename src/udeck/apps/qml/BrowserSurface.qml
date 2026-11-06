// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine

Item {
    id: surface
    property var host
    property var appState:host?host.state:({currentTab:"",webMode:"navigation",menu:{}})
    function focusWeb(){for(let i=0;i<pages.count;i++){const p=pages.itemAt(i);if(p&&p.identifier===appState.currentTab)p.forceActiveFocus()}}
    WebEngineProfile {
        id: browserProfile
        property var downloads: ({})
        offTheRecord:true
        httpCacheMaximumSize:64*1024*1024
        persistentCookiesPolicy:WebEngineProfile.AllowPersistentCookies
        Component.onCompleted:{
            if(!controller.isolatedMode){
                storageName="udeck-browser"
                persistentStoragePath=controller.profilePath
                cachePath=controller.profilePath+"/cache"
                offTheRecord=false
            }
        }
        onDownloadRequested: function(download) {
            const destination=controller.confirmDownload(download.downloadFileName, download.url.toString(), download.view?download.view.identifier:"")
            if(!destination.directory){download.cancel();return}
            download.downloadDirectory=destination.directory
            download.downloadFileName=destination.name
            downloads[download.id]=download
            controller.downloadStarted(download.id, destination.directory+"/"+destination.name)
            download.accept()
        }
        onDownloadFinished: function(download) {
            delete downloads[download.id]
            controller.downloadFinished(download.id, download.state, download.interruptReasonString)
        }
    }
    Connections {
        target:controller
        function onCancelDownload(identifier) {
            const download=browserProfile.downloads[identifier]
            if(download)download.cancel()
        }
    }
    ColumnLayout {
        anchors.fill:parent;spacing:0
        Rectangle {
            Layout.fillWidth:true;Layout.preferredHeight:64;color:"#252b2d"
            RowLayout {
                anchors.fill:parent;anchors.margins:10;spacing:10
                SuiteButton{text:"‹";implicitHeight:44;onActivated:controller.command("back")}
                SuiteButton{text:"›";implicitHeight:44;onActivated:controller.command("forward")}
                SuiteButton{text:appState.loading?"×":"↻";implicitHeight:44;onActivated:controller.command(appState.loading?"stop":"reload")}
                Rectangle {
                    Layout.fillWidth:true;Layout.fillHeight:true;color:"#171b1d";radius:8;border.color:"#6d6a5e"
                    Text{anchors.fill:parent;anchors.margins:10;text:appState.url==="about:blank"?(host?host.tr("Address or search"):""):appState.url||"";color:"#f1eee7";font.pixelSize:20;elide:Text.ElideMiddle}
                    MouseArea{anchors.fill:parent;onClicked:controller.command("address")}
                }
                Text{text:host?host.tr(({navigation:"Link navigation",reading:"Reading",pointer:"Virtual pointer",text:"Text input"})[appState.webMode]||"Link navigation"):"";color:"#edb866";font.pixelSize:17}
            }
        }
        Item {
            id:viewport;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            Repeater {
                id:pages;model:controller.browserModel
                delegate:WebEngineView {
                    id:web
                    required property var tabObject
                    property string identifier:tabObject.tabId
                    anchors.fill:viewport
                    visible:identifier===appState.currentTab&&appState.webMode!=="reading"
                    lifecycleState:visible?WebEngineView.LifecycleState.Active:recommendedState
                    profile:browserProfile
                    url:tabObject.initialUrl
                    zoomFactor:appState.zoom||1
                    focus:visible&&appState.webMode==="text"&&!appState.menu.title
                    settings.localContentCanAccessFileUrls:false
                    settings.localContentCanAccessRemoteUrls:false
                    settings.javascriptCanOpenWindows:true
                    function update(error=""){controller.webUpdated(identifier,url.toString(),title,loading,canGoBack,error)}
                    onUrlChanged:update()
                    onTitleChanged:update()
                    onCanGoBackChanged:update()
                    onLoadingChanged:function(request){update(request.status===WebEngineView.LoadFailedStatus?request.errorString:"")}
                    onNewWindowRequested:function(request){controller.openLink(request.requestedUrl.toString())}
                    onFeaturePermissionRequested:function(origin,feature){controller.permission(identifier,origin.toString(),feature)}
                    onCertificateError:function(error){error.rejectCertificate();update("Certificate rejected: "+error.description)}
                    onFullScreenRequested:function(request){request.accept()}
                    onRenderProcessTerminated:function(status,code){update("Page process ended ("+code+"). Reload to recover.")}
                    Connections {
                        target:controller
                        function onWebAction(action,payload){
                            const d=JSON.parse(payload);if(d.id!==web.identifier)return
                            if(action==="navigate")web.url=d.url
                            else if(action==="back")web.goBack()
                            else if(action==="forward")web.goForward()
                            else if(action==="reload")web.reload()
                            else if(action==="stop")web.stop()
                            else if(action==="permission")web.grantFeaturePermission(d.origin,d.feature,d.allow)
                            else if(action==="reading")web.runJavaScript("(document.querySelector('article,main,[role=main]')||document.body).innerText",function(text){controller.readingReady(web.identifier,text||"",d.generation)})
                            else if(action==="mode"){
                                if(d.mode==="text")web.forceActiveFocus()
                                else web.runJavaScript("document.activeElement && document.activeElement.blur()")
                            } else if(action==="input"){
                                if(d.mode==="reading")readingScroll.contentItem.contentY=Math.max(0,Math.min(readingScroll.contentItem.contentHeight-readingScroll.height,readingScroll.contentItem.contentY+(d.action==="up"?-160:160)))
                                else if(d.mode==="pointer"){
                                    if(d.action==="accept"){
                                        const pos=pointer.mapToItem(null,pointer.width/2,pointer.height/2)
                                        controller.webClick(web.identifier,pos.x,pos.y)
                                    }else{pointer.x=Math.max(0,Math.min(viewport.width-pointer.width,pointer.x+(d.action==="left"?-26:d.action==="right"?26:0)));pointer.y=Math.max(0,Math.min(viewport.height-pointer.height,pointer.y+(d.action==="up"?-26:d.action==="down"?26:0)))}
                                } else if(d.mode==="text")controller.webKey(d.action)
                                else web.runJavaScript(controller.navigationScript(d.action),function(result){
                                    if(d.action==="accept"&&result&&controller.acceptsWebResult(web.identifier,d.generation)){
                                        if(result.x!==undefined){const point=web.mapToItem(null,result.x,result.y);controller.webClick(web.identifier,point.x,point.y)}
                                        controller.webInput(web.identifier,result.editing===true)
                                    }
                                })
                            }
                        }
                    }
                }
            }
            Rectangle {
                anchors.fill:parent;visible:appState.url==="about:blank";color:"#171b1d"
                Column {
                    anchors.centerIn:parent;width:Math.min(parent.width-80,700);spacing:22
                    Text{text:"uDeck Browser";color:"#f1eee7";font.pixelSize:40}
                    Text{width:parent.width;text:host?host.tr("Open a website or search the web. Your tabs, bookmarks and history stay on this device."):"";color:"#a8acae";font.pixelSize:24;wrapMode:Text.Wrap}
                    SuiteButton{text:"A  "+(host?host.tr("Address or search"):"");selected:true;onActivated:controller.command("address")}
                    SuiteButton{text:host?host.tr("Bookmarks"):"";onActivated:controller.command("bookmarks")}
                }
            }
            ScrollView {
                id:readingScroll;anchors.fill:parent;visible:appState.webMode==="reading";clip:true
                background:Rectangle{color:"#ece7da"}
                TextArea{readOnly:true;text:appState.readingText||"";color:"#282722";font.pixelSize:Math.round(24*(appState.zoom||1));wrapMode:TextEdit.Wrap;leftPadding:50;rightPadding:50;topPadding:30;bottomPadding:40;background:null}
            }
            Rectangle {
                id:pointer;visible:appState.webMode==="pointer";x:viewport.width/2;y:viewport.height/2;width:22;height:22;radius:11;color:"#40edb866";border.color:"#edb866";border.width:3;z:4
                Rectangle{anchors.centerIn:parent;width:4;height:4;radius:2;color:"white"}
            }
            Rectangle {
                anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;height:loadError.implicitHeight+24;visible:!!appState.webError;color:"#542e2a";z:5
                Text{id:loadError;anchors.fill:parent;anchors.margins:12;text:appState.webError||"";color:"#f1eee7";font.pixelSize:20;wrapMode:Text.Wrap;maximumLineCount:3;elide:Text.ElideRight}
            }
        }
    }
}
