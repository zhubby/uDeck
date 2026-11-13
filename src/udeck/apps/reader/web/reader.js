// SPDX-License-Identifier: GPL-2.0-or-later
import './foliate/view.js'
import { EPUB } from './foliate/epub.js'
const cfg = await (await fetch('config.json')).json()
const view = document.querySelector('foliate-view')
const emit = (type, data={}) => console.log('UDECK_READER:' + JSON.stringify({session:cfg.session,type,...data}))
const readerError = (message, errorCode, errorDetail='') => Object.assign(Error(message), {errorCode,errorDetail})
const reportError = error => emit('error',{error:String(error),errorCode:error?.errorCode,errorDetail:error?.errorDetail})
let searchGeneration = 0
const fonts = {sans:'system-ui, sans-serif', serif:"Georgia, 'Noto Serif CJK SC', serif", mono:'ui-monospace, monospace'}
const backgrounds = {
    paper:{background:'#ece7da', text:'#282722'},
    warm:{background:'#f2e5c7', text:'#332a1d'},
    gray:{background:'#d7dadd', text:'#202426'},
    night:{background:'#202426', text:'#eee8da'},
}
const style = preferences => {
    const palette = backgrounds[preferences.background] || backgrounds.paper
    const font = fonts[preferences.fontFamily] || fonts.sans
    const size = Number.isFinite(preferences.fontSize) ? preferences.fontSize : 24
    const lineHeight = Number.isFinite(preferences.lineHeight) ? preferences.lineHeight : 1.7
    const contentWidth = Number.isFinite(preferences.contentWidth) ? preferences.contentWidth : 1000
    return {css:`html,body {font-size:${size}px!important;color:${palette.text}!important;background:${palette.background}!important} body,body * {line-height:${lineHeight}!important;font-family:${font}!important} p {margin-block:0 1em} img {max-width:100%} a{color:#a77731}`,
        contentWidth}
}
const applyStyle = preferences => {
    const rendered = style(preferences)
    view.renderer.setAttribute('max-inline-size', rendered.contentWidth + 'px')
    view.renderer.setStyles(rendered.css)
}
try {
    let book
    if (cfg.format === 'EPUB') {
        const fetchEntry = async name => {
            if (!(name in cfg.entries)) return null
            const response = await fetch('book/' + name.split('/').map(encodeURIComponent).join('/'))
            if (!response.ok) throw readerError('Cannot read EPUB resource: ' + name, 'epub-resource', name)
            return response
        }
        book = await new EPUB({
            loadText: async name => (await fetchEntry(name))?.text(),
            loadBlob: async name => (await fetchEntry(name))?.blob(),
            getSize: name => cfg.entries[name] ?? 0,
        }).init()
    } else if (cfg.format === 'MOBI') {
        const { MOBI } = await import('./foliate/mobi.js')
        // Foliate reads PDB records through Blob.slice(). Fetch only those ranges,
        // so a large illustrated book need not be held in memory in its entirety.
        const file = {
            slice: (start = 0, end = cfg.mobiSize) => ({
                arrayBuffer: async () => {
                    const response = await fetch(`mobi/${start}/${end}`)
                    if (!response.ok) throw readerError('Cannot read MOBI record', 'mobi-record')
                    return response.arrayBuffer()
                },
            }),
        }
        book = await new MOBI({
            unzlib: async data => new Uint8Array(await new Response(
                new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate'))
            ).arrayBuffer()),
        }).open(file)
    } else {
        const text = await (await fetch('text.txt')).text()
        const chunks = text.match(/[\s\S]{1,16000}/g) || ['']
        const escape = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
        book = {metadata:{title:cfg.title}, toc:chunks.map((_,i)=>({label:String(i+1),href:String(i)})),
            splitTOCHref:href=>[String(href),null],getTOCFragment:doc=>doc.body,
            resolveHref:href=>({index:Number(href),anchor:doc=>doc.body}),isExternal:()=>false,
            sections:chunks.map((text,i) => {
            const markup = `<html xmlns="http://www.w3.org/1999/xhtml"><head><title>${i+1}</title></head><body>${escape(text).split('\n').map(x=>'<p>'+x+'</p>').join('')}</body></html>`
            const blob = new Blob([markup],{type:'application/xhtml+xml'})
            const url = URL.createObjectURL(blob)
            return {id:String(i),size:text.length,linear:'yes',load:()=>url,
                createDocument:()=>new DOMParser().parseFromString(markup,'application/xhtml+xml')}
        })}
    }
    view.addEventListener('relocate', e => {
        const d=e.detail
        emit('position',{cfi:d.cfi,fraction:d.fraction??0,label:d.tocItem?.label??'',section:d.section?.current??0})
    })
    // Books cannot run scripts: the HTTP CSP only trusts this nonce module graph.
    view.addEventListener('external-link', e=>{e.preventDefault();emit('external',{url:e.detail.href_})})
    await view.open(book)
    view.renderer.setAttribute('max-column-count','1')
    view.renderer.setAttribute('gap','10%')
    applyStyle(cfg.preferences)
    await view.init({lastLocation:cfg.position.cfi,showTextStart:true})
    const toc=[]
    const walk = (items,depth=0)=>{for(const x of items||[]){toc.push({title:x.label,href:x.href,depth});walk(x.subitems,depth+1)}}
    walk(book.toc)
    emit('ready',{toc})
    window.udeckReader = async (action,value,session) => {
        if(session!==cfg.session)return
        try {
            if(action==='next') await view.next()
            else if(action==='previous') await view.prev()
            else if(action==='goto') await view.goTo(value)
            else if(action==='fraction') await view.goToFraction(value)
            else if(action==='style') applyStyle({...cfg.preferences,...value})
            else if(action==='scroll') await view.renderer.scrollBy?.(0,value)
            else if(action==='clear') {searchGeneration++;view.clearSearch()}
            else if(action==='search') {
                const generation=++searchGeneration
                const results=[]
                for await(const result of view.search({query:value})) {
                    if(generation!==searchGeneration) return
                    for(const item of result.subitems || (result.cfi?[result]:[])) {
                        const excerpt=item.excerpt
                        results.push({cfi:item.cfi,title:typeof excerpt==='string'?excerpt:[excerpt?.pre,excerpt?.match,excerpt?.post].filter(Boolean).join('')})
                        if(results.length>=200) break
                    }
                    if(results.length>=200) break
                }
                if(generation===searchGeneration) emit('search',{results,query:value})
            }
        } catch(error) {reportError(error)}
    }
} catch(error) {reportError(error)}
