// SPDX-License-Identifier: GPL-2.0-or-later
function(action) {
    const editable = el => el && (el.matches('input,textarea,select') || el.isContentEditable)
    const current = document.querySelector('[data-udeck-focus]') || document.activeElement
    if(action === 'accept') {
        if(current && current !== document.body) {
            current.focus()
            const r=current.getBoundingClientRect()
            return {editing:!!editable(current),x:r.x+r.width/2,y:r.y+r.height/2}
        }
        return {editing:false}
    }
    const candidates = [...document.querySelectorAll('a[href],button,input,textarea,select,[tabindex],[role=button]')]
        .filter(el => !el.disabled && el.getAttribute('aria-hidden') !== 'true' && el.getAttribute('tabindex') !== '-1')
        .map(el=>({el,r:el.getBoundingClientRect()})).filter(x=>x.r.width>0&&x.r.height>0&&getComputedStyle(x.el).visibility!=='hidden')
    const rect = current?.getBoundingClientRect()
    const horizontal = action === 'left' || action === 'right'
    const sign = action === 'left' || action === 'up' ? -1 : 1
    const center = r => ({x:r.x+r.width/2,y:r.y+r.height/2})
    const origin = rect && current !== document.body ? center(rect) : {x:0,y:0}
    const ranked = candidates.filter(x=>x.el!==current).map(x=>{
        const c=center(x.r),primary=(horizontal?c.x-origin.x:c.y-origin.y)*sign,secondary=Math.abs(horizontal?c.y-origin.y:c.x-origin.x)
        return {...x,primary,score:primary+secondary*2.5}
    }).filter(x=>x.primary>3).sort((a,b)=>a.score-b.score)
    let next=ranked[0]?.el
    if(!next && (!current || current===document.body))next=candidates[0]?.el
    if(next) {
        document.querySelectorAll('[data-udeck-focus]').forEach(el=>{el.removeAttribute('data-udeck-focus');el.style.outline=el.dataset.udeckOldOutline||''})
        next.dataset.udeckOldOutline=next.style.outline
        next.setAttribute('data-udeck-focus','1');next.style.outline='3px solid #edb866'
        next.focus({preventScroll:true});next.scrollIntoView({block:'nearest',inline:'nearest'})
    } else window.scrollBy({top:horizontal?0:sign*200,left:horizontal?sign*200:0})
    return false
}
