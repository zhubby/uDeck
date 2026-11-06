"""Generate original, offline sample artwork for the interface studies."""

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent


def svg(name, width, height, body):
    (ROOT / (name + ".svg")).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{body}</svg>', encoding="utf-8")


albums = [
    ("after-hours", "AFTER HOURS", "MIRA VALE", "#384950", "#efad75"),
    ("still-water", "STILL WATER", "NORTH WINDOW", "#b8bca5", "#243b38"),
    ("slow-orbit", "SLOW ORBIT", "JUNE RADIO", "#bd7a5e", "#e8d9b1"),
    ("field-notes", "FIELD NOTES", "A. MORI", "#53634f", "#d6cfae"),
    ("blue-hour", "BLUE HOUR", "MIRA VALE", "#344c6a", "#d3dfde"),
    ("home-tapes", "HOME TAPES", "SIDE B", "#d1ba8e", "#69503f"),
    ("daybreak", "DAYBREAK", "SOFT SIGNAL", "#a3b0a3", "#584739"),
    ("long-way", "THE LONG WAY HOME", "NORTH WINDOW", "#51575e", "#d6cdb9"),
]
for index, (name, title, artist, bg, ink) in enumerate(albums):
    art = f'<rect width="400" height="400" fill="{bg}"/>'
    if index % 4 == 0:
        art += f'<circle cx="262" cy="145" r="78" fill="{ink}"/>'
        for x in range(30, 400, 24):
            art += f'<path d="M{x} 210v190" stroke="#101b24" stroke-width="11"/>'
    elif index % 4 == 1:
        for y in range(115, 360, 21):
            art += f'<path d="M25 {y}q80 -35 175 0t175 0" stroke="{ink}" stroke-width="2" fill="none"/>'
        art += f'<circle cx="200" cy="160" r="54" fill="{ink}"/>'
    elif index % 4 == 2:
        for radius in (110, 83, 56, 29):
            art += f'<circle cx="200" cy="225" r="{radius}" stroke="{ink}" stroke-width="7" fill="none"/>'
        art += f'<circle cx="288" cy="151" r="22" fill="{ink}"/>'
    else:
        for x in range(45, 380, 46):
            art += f'<path d="M{x} 340v-180l-18 30m18 5 16-24m-16 62-22-20m22 38 20-16" stroke="{ink}" stroke-width="3" fill="none"/>'
    art += f'<text x="27" y="47" font-family="sans-serif" font-size="23" font-weight="600" letter-spacing="2" fill="{ink}">{escape(title)}</text>'
    art += f'<text x="28" y="77" font-family="sans-serif" font-size="12" letter-spacing="3" fill="{ink}">{artist}</text>'
    svg(name, 400, 400, art)

landscapes = [
    ("open-road", "#a1b6b5", "#53695e", "#253e3c", "#e4bf86"),
    ("quiet-coast", "#c3c6b5", "#6e9297", "#3f626c", "#ede2ba"),
    ("night-train", "#293b4c", "#314b4d", "#172c30", "#e3b675"),
    ("mountain-light", "#cec4ab", "#89918a", "#424e4e", "#e9d3a1"),
    ("making-room", "#c3b69c", "#8c9a86", "#485c53", "#e6d9ab"),
    ("city-rhythm", "#7d9292", "#5d7270", "#2a4042", "#d9c09b"),
]
for index, (name, sky, far, near, sun) in enumerate(landscapes):
    art = f'<rect width="960" height="540" fill="{sky}"/><circle cx="710" cy="142" r="54" fill="{sun}"/>'
    art += f'<path d="M0 290 170 190 285 270 475 145 660 285 800 200 960 275v265H0Z" fill="{far}"/>'
    art += f'<path d="M0 360 200 285 370 350 570 280 780 345 960 305v235H0Z" fill="{near}"/>'
    if index % 3 == 0:
        art += '<path d="M360 540 525 310h15l75 230" fill="#a5a594"/><path d="m490 540 42-225" stroke="#e6d7ad" stroke-width="3" stroke-dasharray="25 30"/>'
    elif index % 3 == 1:
        art += f'<path d="M0 390q250-65 480-10t480 0v160H0Z" fill="{far}"/>'
        for y in (410, 445, 480):
            art += f'<path d="M{y // 3} {y}h{640-y // 2}" stroke="{sun}" stroke-width="2"/>'
    else:
        art += '<path d="m0 490 960-130v42L0 532Z" fill="#b4a88b"/>'
        for x in range(90, 800, 135):
            art += f'<rect x="{x}" y="330" width="110" height="75" rx="4" fill="#283b3d"/><rect x="{x+15}" y="342" width="75" height="27" fill="{sun}"/>'
    svg(name, 960, 540, art)

books = [
    ("small-journeys", "SMALL", "JOURNEYS", "A FIELD JOURNAL", "#c7b58d", "#30483f"),
    ("wayland-notes", "WAYLAND", "NOTES", "A PRACTICAL GUIDE", "#455f60", "#e3ddbe"),
    ("garden-time", "GARDEN", "TIME", "NOTES ON GROWING", "#607354", "#e1d8b0"),
    ("keyboard-guide", "THE POCKET", "COMPUTER", "USER HANDBOOK", "#a36f51", "#f2e4c8"),
]
for name, first, second, subtitle, bg, ink in books:
    art = f'<rect width="280" height="410" fill="{bg}"/><rect x="13" y="13" width="254" height="384" fill="none" stroke="{ink}" stroke-width="1"/>'
    art += f'<text x="30" y="70" font-family="serif" font-size="30" fill="{ink}">{first}</text><text x="30" y="112" font-family="serif" font-size="30" fill="{ink}">{second}</text>'
    art += f'<text x="30" y="150" font-family="sans-serif" font-size="10" letter-spacing="2" fill="{ink}">{subtitle}</text>'
    art += f'<circle cx="140" cy="258" r="57" stroke="{ink}" stroke-width="1" fill="none"/><path d="M65 285 115 220l30 30 28-47 45 82Z" stroke="{ink}" fill="none" stroke-width="2"/>'
    art += f'<text x="30" y="365" font-family="sans-serif" font-size="11" letter-spacing="3" fill="{ink}">UDECK FIELD EDITIONS</text>'
    svg(name, 280, 410, art)

games = [("pocket-orchard", "POCKET", "ORCHARD", "#b8c68a", "#36583f"),
         ("orbital", "ORBITAL", "COURIER", "#6b7c91", "#23364b"),
         ("tiny-valley", "TINY", "VALLEY", "#c1b38d", "#6a6148"),
         ("startrail", "STAR", "TRAIL", "#807895", "#35334c"),
         ("rally-day", "RALLY", "DAY", "#9ca58d", "#3f5955"),
         ("harbor", "HARBOR", "LIGHT", "#95a9ad", "#334e5b"),
         ("meadow", "MEADOW", "QUEST", "#b3bf8f", "#4e6445"),
         ("moon-base", "MOON", "BASE", "#aea3a6", "#554c67")]
for index, (name, first, second, bg, ink) in enumerate(games):
    art = f'<rect width="280" height="340" fill="{bg}"/><rect x="12" y="12" width="256" height="316" fill="none" stroke="{ink}" stroke-width="3"/>'
    art += f'<text x="140" y="61" text-anchor="middle" font-family="monospace" font-size="29" font-weight="700" fill="{ink}">{first}</text><text x="140" y="93" text-anchor="middle" font-family="monospace" font-size="29" font-weight="700" fill="{ink}">{second}</text>'
    for x in range(28, 260, 16):
        art += f'<rect x="{x}" y="{240+(x%3)*8}" width="16" height="{70-(x%3)*8}" fill="{ink}" opacity=".6"/>'
    if index % 2 == 0:
        for x in (55, 183):
            art += f'<rect x="{x+14}" y="189" width="12" height="60" fill="{ink}"/><rect x="{x-4}" y="153" width="48" height="45" fill="{ink}"/><rect x="{x+6}" y="163" width="8" height="8" fill="#e1ba70"/>'
        art += f'<path d="M127 211h25v32h-25Zm-8-10h40v12h-40Z" fill="{ink}"/>'
    else:
        for x, y in ((40, 140), (200, 160), (80, 214), (228, 120)):
            art += f'<path d="M{x} {y}h8v-8h8v8h8v8h-8v8h-8v-8h-8Z" fill="{ink}"/>'
        art += f'<path d="M131 170h18v12h12v30h-12v20h-18v-20h-12v-30h12Z" fill="{ink}"/>'
    art += f'<text x="140" y="305" text-anchor="middle" font-family="monospace" font-size="10" fill="{bg}">UDECK ORIGINAL SAMPLE</text>'
    svg(name, 280, 340, art)

art = '<rect width="640" height="576" fill="#bfd198"/>'
for x in range(0, 640, 32):
    for y in range(0, 576, 32):
        art += f'<path d="M{x+4} {y+11}h5v-4m9 12h4v-4" stroke="#a5bc80" stroke-width="3" fill="none"/>'
art += '<path d="M0 390h640v70H0ZM290 0h70v576h-70Z" fill="#dfd7a5"/>'
for x, y in ((80, 120), (176, 192), (480, 100), (528, 276), (96, 476)):
    art += f'<path d="M{x+22} {y+36}h16v52h-16Z" fill="#526b43"/><path d="M{x} {y}h60v60h-60Z" fill="#426f43"/><path d="M{x+8} {y+10}h12v12h-12Zm32 23h12v12h-12Z" fill="#c48c51"/>'
art += '<path d="M360 230h150v100H360Z" fill="#c3bc85"/><path d="m350 235 85-60 85 60Z" fill="#607d4b"/><path d="M420 280h30v50h-30Z" fill="#4c6b40"/>'
art += '<path d="M310 345h28v28h-28Zm-8-12h45v14h-45Z" fill="#365f3d"/><path d="M307 375h10v14h-10Zm22 0h10v14h-10Z" fill="#365f3d"/>'
art += '<rect x="20" y="18" width="600" height="46" fill="#365f3d"/><text x="38" y="49" font-family="monospace" font-size="23" fill="#e0e7bc">DAY 08       ORCHARD       240 G</text>'
svg("orchard-screen", 640, 576, art)
