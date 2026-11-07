"""Exercise the offline design in Chromium; no production packages are needed.

Requires agent-browser on PATH. Screenshots and a machine-readable report are
written outside the design sources, under artifacts/app-suite/verification.
"""

import argparse
import hashlib
import json
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

APPS = ("music", "video", "browser", "reader", "games")
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
LAYOUT = """(() => {
  const issues = [], app = document.querySelector('#app');
  if (app.clientWidth !== innerWidth || app.clientHeight !== innerHeight)
    issues.push('viewport size');
  if (document.documentElement.scrollWidth > innerWidth || app.scrollTop)
    issues.push('outer overflow');
  const modal = document.querySelector('.modal');
  if (modal) {
    const r = modal.getBoundingClientRect();
    if (r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight)
      issues.push('dialog outside viewport');
  }
  const focused = document.querySelector('.focused');
  if (focused) {
    const r = focused.getBoundingClientRect();
    let bounds = {left:0,top:0,right:innerWidth,bottom:innerHeight};
    for (let p = focused.parentElement; p; p = p.parentElement) {
      const style = getComputedStyle(p), pr = p.getBoundingClientRect();
      if (/(auto|scroll|hidden)/.test(style.overflowY)) {
        bounds.top = Math.max(bounds.top, pr.top);
        bounds.bottom = Math.min(bounds.bottom, pr.bottom);
      }
      if (/(auto|scroll|hidden)/.test(style.overflowX)) {
        bounds.left = Math.max(bounds.left, pr.left);
        bounds.right = Math.min(bounds.right, pr.right);
      }
    }
    if (r.left < bounds.left - 2 || r.top < bounds.top - 2 ||
        r.right > bounds.right + 2 || r.bottom > bounds.bottom + 2)
      issues.push('focus clipped: ' + focused.dataset.nav);
    if (modal && !modal.contains(focused)) issues.push('focus outside dialog');
    if (focused.dataset.nav !== udeckStudy.state.focus) issues.push('focus disagreement');
    if (focused.disabled) issues.push('disabled focus');
  }
  if ([...document.images].some(x => !x.complete || !x.naturalWidth))
    issues.push('missing artwork');
  for (const image of document.querySelectorAll('.input-prompt-icon')) {
    const r = image.getBoundingClientRect();
    if (r.width < 24 || r.height < 24 || r.left < 0 || r.top < 0 ||
        r.right > innerWidth || r.bottom > innerHeight)
      issues.push('input icon outside viewport: ' + image.alt);
  }
  const hints = document.querySelector('.button-hints')?.getBoundingClientRect();
  const context = document.querySelector('.footer-context')?.getBoundingClientRect();
  if (hints && context && hints.right > context.left - 6)
    issues.push('input prompt groups overlap');
  return issues;
})()"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class Review:
    def __init__(self, base, output):
        self.base = base
        self.output = output
        self.session = "udeck-suite-verify"
        self.checks = []
        self.screens = []
        self.locale = "en"

    def browser(self, *args):
        result = subprocess.run(
            ["rtk", "proxy", "agent-browser", "--session", self.session, "--json", *args],
            capture_output=True, text=True, timeout=40, check=False,
        )
        if not result.stdout.strip():
            raise AssertionError(result.stderr or f"agent-browser exited {result.returncode}")
        payload = json.loads(result.stdout)
        if not payload.get("success"):
            raise AssertionError(payload.get("error"))
        return payload.get("data", {})

    def evaluate(self, script):
        return self.browser("eval", script).get("result")

    def check(self, script, name):
        result = self.evaluate(script)
        if result is not True:
            raise AssertionError(f"{name}: {result!r}")
        self.checks.append(name)

    def press(self, key):
        self.browser("press", key)

    def choose(self, en, zh=None):
        value = zh if self.locale == "zh_CN" and zh else en
        self.check("""(() => {
          const text = __TEXT__;
          const item = [...document.querySelectorAll('.modal .row-title')]
            .find(x => x.textContent === text)?.closest('button');
          if (!item || item.disabled) return false;
          item.click(); return true;
        })()""".replace("__TEXT__", json.dumps(value)), f"choose {value}")

    def reset(self, app, locale="en"):
        self.locale = locale
        self.browser("open", self.base + f"?app={app}&lang={locale}&capture=1")
        self.evaluate("localStorage.removeItem('udeck-design-v1'); true")
        self.browser("open", self.base + f"?app={app}&lang={locale}&capture=1")
        self.evaluate("udeckStudy.state.music.playing=false; true")
        self.check(f"udeckStudy.state.app === {json.dumps(app)}", f"open {app} {locale}")

    def shot(self, name):
        self.evaluate("document.getAnimations().filter(x=>x.effect.getTiming().iterations!==Infinity).forEach(x=>x.finish()); true")
        self.evaluate("document.fonts.ready.then(()=>true)")
        issues = self.evaluate(LAYOUT)
        if issues:
            self.browser("screenshot", str(self.output / f"FAIL-{name}.png"))
            raise AssertionError(f"{name}: {issues}")
        self.checks.append(f"layout {name}")
        target = self.output / f"{name}.png"
        self.browser("screenshot", str(target))
        self.screens.append(target.name)

    def matrix(self):
        for width, height in ((1280, 720), (960, 600)):
            self.browser("set", "viewport", str(width), str(height))
            for locale in ("en", "zh_CN"):
                for app in APPS:
                    self.reset(app, locale)
                    prefix = f"{app}-{locale}-{width}"
                    self.shot(prefix + "-home")
                    before = self.evaluate("udeckStudy.state.focus")
                    self.press("F2")
                    self.shot(prefix + "-actions")
                    self.press("Escape")
                    self.check(f"udeckStudy.state.focus === {json.dumps(before)}",
                               f"{prefix} context returns focus")
                    self.press("F3")
                    self.choose("Interface language", "界面语言")
                    self.shot(prefix + "-language")
                    self.press("Escape")
                    self.press("Escape")
                    self.press("Enter")
                    if app == "music":
                        self.shot(prefix + "-album")
                        self.press("Enter")
                        self.shot(prefix + "-player")
                        self.press("Escape")
                        self.press("Escape")
                    elif app == "video":
                        self.shot(prefix + "-resume")
                        self.press("Enter")
                        self.shot(prefix + "-player")
                        self.press("F2")
                        self.shot(prefix + "-tracks")
                        self.press("Escape")
                        self.press("Escape")
                        self.check("!udeckStudy.state.video.playing", prefix + " back pauses")
                    elif app == "browser":
                        self.shot(prefix + "-page")
                        self.press("Enter")
                        self.shot(prefix + "-reading")
                        self.press("Escape")
                        self.press("Escape")
                        self.check("!udeckStudy.state.browser.tabs[0].url", prefix + " page back")
                    elif app == "reader":
                        self.shot(prefix + "-reading")
                        self.press("PageDown")
                        self.check("udeckStudy.state.reader.page === 43", prefix + " page turn")
                        self.press("Escape")
                        self.check("udeckStudy.state.reader.positions['small-journeys'] === 43",
                                   prefix + " reading position")
                    else:
                        self.shot(prefix + "-details")
                        self.press("Enter")
                        self.shot(prefix + "-gameplay-study")
                        self.press("Escape")
                        self.press("b")
                        self.check("udeckStudy.state.games.view === 'running' && !udeckStudy.state.modalStack.length",
                                   prefix + " B belongs to gameplay")
                        self.press("Control+Alt+m")
                        self.shot(prefix + "-pause")
                        self.choose("Save & return to library", "保存并返回媒体库")
                    self.check(f"udeckStudy.state.focus === {json.dumps(before)}",
                               prefix + " primary return focus")
                    for scenario in ("empty", "loading", "error", "removed"):
                        self.evaluate(f"udeckStudy.setScenario('{scenario}'); true")
                        self.shot(prefix + "-" + scenario)
                        self.check("!udeckStudy.state.modalStack.length && !!document.querySelector('[data-nav=scenario-action]')",
                                   prefix + " " + scenario + " recovery")
                    self.check("performance.getEntriesByType('resource').every(x=>x.name.startsWith(location.origin))",
                               prefix + " offline resources")
        print("Bilingual viewport matrix passed", flush=True)

    def detailed_flows(self):
        self.browser("set", "viewport", "1280", "720")
        self.reset("music")
        self.press("F2")
        self.choose("Search music")
        for key in "abxy":
            self.press(key)
        self.check("document.querySelector('input').value === 'abxy' && udeckStudy.state.modalStack.length === 2",
                   "ordinary letters remain text")
        self.check("""(() => {
          const input=document.querySelector('input');
          input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true}));
          return udeckStudy.state.modalStack.length === 2 && input.value === 'abxy';
        })()""", "IME composition Enter does not submit")
        self.press("F6")
        self.locale = "zh_CN"
        self.check("document.querySelector('input').value === 'abxy'", "locale keeps draft")
        self.press("Enter")
        self.check("!!document.querySelector('[data-nav=clear-search]') && !document.querySelector('.modal')",
                   "empty search has recovery")
        self.shot("music-no-results-zh_CN")
        self.press("Enter")
        self.check("!udeckStudy.state.query", "clear search")
        self.reset("music")
        self.evaluate("udeckStudy.action('now'); udeckStudy.focus('open-queue'); true")
        self.press("Enter")
        self.check("udeckStudy.state.music.tab === 2", "player opens queue")
        self.press("Escape")
        self.check("udeckStudy.state.music.view === 'now' && udeckStudy.state.focus === 'open-queue'",
                   "queue B returns to player")
        before = self.evaluate("udeckStudy.state.music.position")
        self.press("F3")
        self.choose("Audio output")
        self.choose("Studio Headphones")
        self.check(f"udeckStudy.state.audioOutput === 'headphones' && udeckStudy.state.music.position === {before}",
                   "output selection keeps position")
        self.reset("music")
        self.press("PageDown")
        self.press("PageDown")
        self.evaluate("udeckStudy.focus('track-after-hours-1'); true")
        self.press("F2")
        self.choose("Move up in queue")
        self.check("udeckStudy.state.music.queue[0] === 'after-hours-1' && udeckStudy.state.focus === 'track-after-hours-1'",
                   "queue move preserves identity")
        self.press("F2")
        self.choose("Remove from queue")
        self.check("!udeckStudy.state.music.queue.includes('after-hours-1') && udeckStudy.state.focus === 'track-after-hours-0'",
                   "queue removal chooses neighbor")
        self.evaluate("udeckStudy.setScenario('removed'); udeckStudy.action('choose-source'); true")
        self.press("ArrowDown")
        self.check("udeckStudy.state.modalStack.at(-1).index === 2 && document.activeElement.dataset.nav === 'modal-2'",
                   "menu skips disabled SD source")
        self.shot("source-removed-disabled")
        self.press("Escape")
        self.reset("video")
        self.press("PageDown")
        self.press("PageDown")
        self.press("Enter")
        self.check("document.querySelectorAll('.video-card').length === 3 && udeckStudy.state.video.folder === 'Films'",
                   "video folder filters")
        self.shot("video-folder")
        self.press("Escape")
        self.check("udeckStudy.state.video.tab === 2 && udeckStudy.state.focus === 'folder-Films'",
                   "video folder return")
        self.reset("video")
        self.press("Enter")
        self.press("Enter")
        self.evaluate("udeckStudy.state.video.playing=false; true")
        self.press("PageDown")
        self.check("udeckStudy.state.video.position === 2120", "next chapter uses boundary")
        self.press("F2")
        self.choose("Hide controls")
        self.check("!document.querySelector('.video-overlay') && !document.querySelector('.footer') && !!document.querySelector('.subtitle-line')",
                   "subtitles survive hidden controls")
        self.shot("video-hidden-controls-subtitles")
        self.press("Enter")
        self.evaluate("udeckStudy.focus('video-tracks'); true")
        self.press("Enter")
        self.choose("Chapters")
        self.press("F6")
        self.check("document.querySelector('.modal .row-title').textContent.includes('出发')",
                   "open chapters translate immediately")
        self.reset("browser")
        self.press("Control+l")
        self.browser("fill", "[data-modal-input]", "javascript:alert(1)")
        self.press("Enter")
        self.check("!!document.querySelector('[data-modal-input]') && !udeckStudy.state.browser.tabs[0].url && !!document.querySelector('.toast')",
                   "address rejects active URL scheme")
        self.browser("fill", "[data-modal-input]", "https://journal.example/abxy?q=%3Ctag%3E")
        self.press("F6")
        self.check("document.querySelector('input').value.includes('/abxy')", "address draft survives locale")
        self.press("F6")
        self.press("Enter")
        self.check("document.querySelector('.url').textContent.endsWith('/abxy?q=%3Ctag%3E')", "address remains literal")
        self.press("F3")
        self.choose("Text size")
        self.choose("125%")
        self.press("Escape")
        self.check("parseFloat(getComputedStyle(document.querySelector('.web-page')).fontSize) === 26.25",
                   "browser zoom changes content")
        self.press("F2")
        self.choose("Page interaction")
        self.choose("Read the page")
        self.check("getComputedStyle(document.querySelector('.web-columns')).display === 'block'", "reader mode reflows")
        self.press("Escape")
        self.press("F2")
        self.choose("Page interaction")
        self.choose("Type into the page")
        self.browser("fill", "[data-inline-input]", "abxy 普通文字")
        self.press("F6")
        self.check("document.activeElement.value === 'abxy 普通文字'", "page input preserves draft")
        self.press("F6")
        self.press("Enter")
        self.check("udeckStudy.state.browser.mode === 'navigation' && udeckStudy.state.query === 'abxy 普通文字'",
                   "page Enter commits local draft")
        self.press("F2")
        self.choose("Add this page to bookmarks")
        self.check("udeckStudy.state.browser.bookmarks.length === 3", "browser bookmark added")
        self.press("F2")
        self.choose("Bookmarks")
        self.choose("https://journal.example/abxy?q=%3Ctag%3E")
        self.choose("Remove bookmark")
        self.check("udeckStudy.state.browser.bookmarks.length === 2", "browser bookmark removed")
        self.press("F2")
        self.choose("History")
        self.press("Enter")
        self.check("!document.querySelector('.modal') && udeckStudy.state.browser.visits.length === 1",
                   "browser history opens same tab")
        self.press("F2")
        self.choose("Page interaction")
        self.choose("Virtual pointer")
        self.press("ArrowRight")
        self.check("udeckStudy.state.browser.pointer.x === 406", "virtual pointer moves")
        self.evaluate("""const page=document.querySelector('.web-page'), link=document.querySelector('[data-nav=article-read]');
          link.scrollIntoView({block:'center'}); const p=page.getBoundingClientRect(),r=link.getBoundingClientRect();
          udeckStudy.state.browser.pointer={x:r.left+r.width/2-p.left,y:r.top+r.height/2-p.top};
          udeckStudy.render(); true""")
        self.press("Enter")
        self.check("udeckStudy.state.browser.mode === 'reader'", "virtual pointer clicks scrolled link")
        self.press("Escape")
        self.evaluate("for(let i=0;i<12;i++) udeckStudy.action('new-tab'); true")
        self.check("new Set(udeckStudy.state.browser.tabs.map(x=>x.id)).size === 13", "rapid tabs have distinct IDs")
        self.shot("browser-many-tabs")
        self.press("Tab")
        self.check("document.activeElement.dataset.nav === udeckStudy.state.focus", "native Tab synchronizes focus")
        self.reset("reader")
        self.press("Enter")
        self.press("F2")
        self.choose("Saved bookmarks")
        self.check("document.activeElement.textContent.includes('Back')", "empty bookmarks can return")
        self.press("Escape")
        self.press("Escape")
        self.press("F2")
        self.choose("Bookmark this page")
        self.check("udeckStudy.state.reader.bookmarks.includes('small-journeys:42')", "reader bookmark")
        self.press("F2")
        self.choose("Go to page")
        self.browser("fill", "[data-modal-input]", "999")
        self.press("Enter")
        self.check("udeckStudy.state.reader.page === 42 && !!document.querySelector('[data-modal-input]')",
                   "page range validated")
        self.browser("fill", "[data-modal-input]", "17")
        self.press("Enter")
        self.check("udeckStudy.state.reader.page === 17 && !document.querySelector('.modal')", "go to page")
        self.press("F2")
        self.choose("Find in document")
        self.browser("fill", "[data-modal-input]", "river")
        self.press("Enter")
        self.check("document.querySelectorAll('mark').length > 0", "document search highlights")
        self.shot("reader-search")
        self.press("Escape")
        self.evaluate("udeckStudy.action('book:wayland-notes'); true")
        self.check("!document.querySelector('.toast')", "new document clears old notification")
        self.shot("reader-pdf-fit-width")
        self.press("F3")
        self.check("document.querySelector('.modal .row-title').textContent === 'PDF zoom'",
                   "PDF settings reflect fixed layout")
        self.press("Escape")
        self.press("F2")
        self.choose("PDF zoom")
        self.choose("200%")
        self.press("Escape")
        self.press("ArrowRight")
        self.check("document.querySelector('.reading-body').scrollLeft > 0 && udeckStudy.state.reader.page === 8",
                   "PDF pans independently of pages")
        self.press("PageDown")
        self.check("udeckStudy.state.reader.page === 9", "PDF shoulder page turn")
        self.browser("open", self.base + "?app=reader&lang=en&capture=1")
        self.check("udeckStudy.state.reader.positions['wayland-notes'] === 9", "reading position survives reload")
        self.reset("games")
        self.press("ArrowRight")
        self.check("document.querySelector('.game-summary h2').textContent === 'Star Trail'", "game preview follows focus")
        self.press("Enter")
        self.press("Enter")
        self.check("document.querySelector('.modal-body').textContent.includes('firmware') && udeckStudy.state.games.view !== 'running'",
                   "BIOS check prevents launch")
        self.shot("games-missing-bios")
        self.press("Escape")
        self.press("Escape")
        self.press("PageDown")
        self.evaluate("udeckStudy.focus('game-moon-base'); true")
        self.press("Enter")
        self.press("Enter")
        self.check("document.querySelector('.modal-body').textContent.includes('core')", "missing core explained")
        self.shot("games-missing-core")
        self.reset("games")
        self.evaluate("udeckStudy.action('game:orbital'); true")
        self.press("F2")
        self.choose("Load saved game")
        self.press("Escape")
        self.press("Escape")
        self.check("document.querySelector('[data-nav=game-launch]').textContent.includes('Start game')",
                   "empty slot inspection is not a resume point")
        self.reset("games")
        self.press("Enter")
        self.press("Enter")
        self.press("Control+Alt+m")
        self.choose("Load state")
        self.check("document.activeElement.textContent.includes('Back')", "empty save slots can return")
        self.press("Escape")
        self.choose("Save state")
        self.choose("Slot 1")
        self.check("!!udeckStudy.state.games.saves['pocket-orchard']['1']", "manual state saved")
        self.choose("Slot 1")
        self.check("!document.querySelector('.toast')", "confirmation clears old save notification")
        self.shot("games-overwrite-confirm")
        self.press("Escape")
        self.check("document.querySelector('.modal h1').textContent === 'Save states'", "overwrite B returns to slots")
        self.choose("Slot 1")
        self.choose("Replace")
        self.press("Escape")
        self.choose("Load state")
        self.choose("Slot 1")
        self.choose("Load state")
        self.check("udeckStudy.state.games.view === 'running' && !udeckStudy.state.modalStack.length", "load returns to game")
        self.press("Control+Alt+m")
        self.choose("Save state")
        self.choose("Slot 1")
        before = self.evaluate("JSON.stringify(udeckStudy.state.games.saves)")
        self.evaluate("udeckStudy.setScenario('removed'); true")
        self.check("!udeckStudy.state.modalStack.length && udeckStudy.state.games.view === 'detail'", "source loss closes game dialogs")
        self.check(f"JSON.stringify(udeckStudy.state.games.saves) === {json.dumps(before)}", "source loss claims no new save")
        self.shot("games-source-loss-during-save")
        self.browser("open", self.base + "?app=games&lang=en&capture=1")
        self.check("!!udeckStudy.state.games.saves['pocket-orchard']['1'] && udeckStudy.state.games.view === 'library'",
                   "save metadata survives reload without auto launch")
        errors = self.browser("errors")
        if errors.get("errors"):
            raise AssertionError(errors)
        print("Detailed keyboard and recovery flows passed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / "artifacts/app-suite/verification")
    parser.add_argument("--only", choices=("all", "matrix", "flows"), default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "prototype/assets").glob("*.svg"):
        ElementTree.parse(path)
    handler = partial(QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    review = Review(f"http://127.0.0.1:{server.server_port}/prototype/", args.output)
    report = {
        "scope": "offline design prototype; no native engines or hardware",
        "passed": False,
        "sourceSha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "prototype").rglob("*") if path.is_file() and "__pycache__" not in path.parts
        },
    }
    try:
        if args.only in ("all", "matrix"):
            review.matrix()
        if args.only in ("all", "flows"):
            review.detailed_flows()
        report["passed"] = True
    except Exception as exc:
        report["failure"] = str(exc)
        raise
    finally:
        report.update(checks=review.checks, screenshots=review.screens)
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        review.browser("close")
        server.shutdown()
        server.server_close()
        print(f"{len(review.checks)} checks; {len(review.screens)} screenshots; {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
