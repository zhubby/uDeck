import { albums, tracks, videos, books, readingPages, games, sites } from "./data.js";

const params = new URLSearchParams(location.search);
const appIds = ["music", "video", "browser", "reader", "games"];
const persisted = (() => { try { return JSON.parse(localStorage.getItem("udeck-design-v1") || "{}"); } catch { return {}; } })();
const state = {
  app: appIds.includes(params.get("app")) ? params.get("app") : "music",
  language: ["en", "zh_CN"].includes(params.get("lang")) ? params.get("lang") : persisted.language || "en",
  scenario: ["ready", "empty", "loading", "error", "removed"].includes(params.get("scenario")) ? params.get("scenario") : "ready", focus: "", modalStack: [], history: {}, toast: "", query: "", audioOutput: "speaker",
  music: { view: "library", tab: 0, album: "after-hours", track: "after-hours-0", playing: true, position: 97, queue: tracks.slice(0, 6).map(x => x.id), shuffle: false, repeat: false },
  video: { view: "library", tab: 0, folder: "", selected: "open-road", playing: false, controls: true, position: 1148, subtitle: "English", audio: "Original · Stereo", speed: "1×" },
  browser: { tab: 0, mode: "navigation", zoom: 1, tabs: [{ id: "tab-1", title: "", url: "", history: [] }], bookmarks: persisted.bookmarks || [sites[0].url, sites[1].url], visits: persisted.visits || [], pointer: { x: 380, y: 160 } },
  reader: { view: "library", tab: 0, selected: "small-journeys", page: 42, size: 24, dark: false, bookmarks: persisted.readerBookmarks || [], positions: persisted.positions || {}, query: "", pdfZoom: "fit" },
  games: { view: "library", tab: 0, system: "All", selected: "pocket-orchard", favorites: persisted.favorites || ["pocket-orchard", "tiny-valley"], recent: persisted.recent || ["pocket-orchard", "startrail", "orbital", "tiny-valley"], saves: persisted.saves || {}, slot: 1 },
};
const root = document.querySelector("#app");
const scrollCache = new Map();
let toastTimer;
let tabSequence = 1;
const T = (en, zh) => state.language === "zh_CN" ? zh : en;
const E = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const names = () => ({ music: T("Music", "音乐"), video: T("Video", "视频"), browser: T("Browser", "浏览器"), reader: T("Reader", "阅读"), games: T("Games", "游戏") });
const paths = {
  music: '<path d="M9 18V5l12-2v13M9 8l12-2"/><ellipse cx="6" cy="18" rx="3" ry="2.5"/><ellipse cx="18" cy="16" rx="3" ry="2.5"/>',
  video: '<rect x="3" y="5" width="20" height="16" rx="3"/><path d="m10 9 7 4-7 4Z"/>',
  browser: '<circle cx="13" cy="13" r="10"/><ellipse cx="13" cy="13" rx="4.5" ry="10"/><path d="M3 13h20"/>',
  reader: '<path d="M3 4c4-1 7 0 10 2 3-2 6-3 10-2v17c-4-1-7 0-10 2-3-2-6-3-10-2ZM13 6v17"/>',
  games: '<path d="M7 8h12c3 0 5 3 5 8s-3 6-6 2H8c-3 4-6 3-6-2s2-8 5-8Z"/><path d="M6 12v5m-2-2.5h5m9-2h.1m3 3h.1"/>',
  play: '<path d="m8 4 14 9-14 9Z"/>', pause: '<path d="M8 5v16M18 5v16" stroke-width="4"/>',
  next: '<path d="m5 6 11 7-11 7Zm14 0v14"/>', previous: '<path d="m21 6-11 7 11 7ZM7 6v14"/>',
  wifi: '<path d="M3 9c6-5 14-5 20 0M6 13c4-4 10-4 14 0m-10 4c2-2 4-2 6 0m-3 4h.1"/>',
  battery: '<rect x="2" y="7" width="20" height="12" rx="2"/><path d="M25 10v6M5 10h13v6H5Z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m16 16 7 7"/>',
  folder: '<path d="M3 7h8l3 3h10v12H3ZM3 7V4h8l3 3"/>',
  arrow: '<path d="m10 6 7 7-7 7"/>', back: '<path d="m15 5-8 8 8 8M7 13h16"/>',
  star: '<path d="m13 2 3.4 7 7.6 1.1-5.5 5.4 1.3 7.5-6.8-3.6-6.8 3.6 1.3-7.5L2 10.1 9.6 9Z"/>',
  check: '<path d="m5 13 5 5L22 6"/>', clock: '<circle cx="13" cy="13" r="10"/><path d="M13 7v7l5 3"/>',
  settings: '<path d="M5 3v20M13 3v20M21 3v20"/><path d="M2 8h6m2 11h6m2-11h6" stroke-width="4"/>',
  error: '<path d="M13 3 25 23H1ZM13 9v6m0 4h.1"/>',
  usb: '<path d="M13 24V4m-4 4 4-5 4 5M13 18l-7-5V9m7 5 7-4V6"/><circle cx="6" cy="7" r="2"/><rect x="18" y="2" width="4" height="4"/>',
  lock: '<rect x="5" y="11" width="16" height="12" rx="2"/><path d="M8 11V7a5 5 0 0 1 10 0v4"/>',
  bookmark: '<path d="M6 3h14v21l-7-5-7 5Z"/>', plus: '<path d="M13 4v18M4 13h18"/>',
  volume: '<path d="M3 10h5l6-6v18l-6-6H3Zm15-3c4 4 4 8 0 12m3-15c6 6 6 12 0 18"/>',
};
const icon = name => `<span class="icon" aria-hidden="true"><svg viewBox="0 0 26 26">${paths[name] || paths.folder}</svg></span>`;
const art = (id, cls = "art", alt = "") => `<img class="${cls}" src="assets/${E(id)}.svg" alt="${E(alt)}" draggable="false">`;
const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const progress = (percent, tag = "") => `<div class="progress"><span ${tag ? `data-progress="${tag}"` : ""} style="width:${Math.max(0, Math.min(100, percent))}%"></span></div>`;
const nav = (id, action, extra = "") => `data-nav="${E(id)}" data-action="${E(action)}" ${extra}`;
const row = (id, title, subtitle, action, end = "", number = "") => `<button class="row-item" ${nav(id, action)}>${number ? `<span class="row-number">${E(number)}</span>` : ""}<span class="row-copy"><span class="row-title">${E(title)}</span>${subtitle ? `<span class="row-subtitle">${E(subtitle)}</span>` : ""}</span><span class="row-end">${end || icon("arrow")}</span></button>`;
const track = () => tracks.find(x => x.id === state.music.track) || tracks[0];
const video = () => videos.find(x => x.id === state.video.selected) || videos[0];
const book = () => books.find(x => x.id === state.reader.selected) || books[0];
const game = () => games.find(x => x.id === state.games.selected) || games[0];
const hasGameSave = item => item.saved || Object.keys(state.games.saves[item.id] || {}).length > 0;
const browserTab = () => state.browser.tabs[state.browser.tab];
const viewKey = () => {
  const item = state[state.app];
  return `${state.app}:${item.view || browserTab().id}:${item.tab || 0}:${item.album || item.selected || ""}:${item.view === "reading" ? item.page : ""}:${item.folder || ""}:${state.query}`;
};

function persist() {
  try { localStorage.setItem("udeck-design-v1", JSON.stringify({ language: state.language, bookmarks: state.browser.bookmarks, visits: state.browser.visits, readerBookmarks: state.reader.bookmarks, positions: state.reader.positions, favorites: state.games.favorites, recent: state.games.recent, saves: state.games.saves })); } catch { notify(T("Changes could not be saved in this browser", "当前浏览器无法保存更改")); }
}
function notify(message) {
  clearTimeout(toastTimer); state.toast = message; render();
  toastTimer = setTimeout(() => { state.toast = ""; render(); }, 2800);
}
function dismissToast() { clearTimeout(toastTimer); state.toast = ""; }
function header() {
  const status = state.app === "browser" ? T("Web", "网页") : state.app === "games" ? T("Game library", "游戏库") : state.app === "reader" ? T("Document library", "文档库") : T("Local library", "本地媒体库");
  return `<header class="topbar"><button class="brand" data-action="apps" aria-label="${T("Choose application", "选择应用")}"><span class="brand-mark">${icon(state.app)}</span><span>uDeck</span><span class="brand-divider">|</span><span class="brand-name">${names()[state.app]}</span></button><div class="status"><span>${status}</span>${icon("wifi")}<span>${icon("battery")} 83%</span><time class="clock">21:08</time></div></header>`;
}
function tabLabels() {
  return ({
    music: [T("Albums", "专辑"), T("Tracks", "曲目"), T("Queue", "播放队列"), T("Folders", "文件夹")],
    video: [T("Continue watching", "继续观看"), T("All videos", "全部视频"), T("Folders", "文件夹")],
    reader: [T("Continue reading", "继续阅读"), T("Bookshelf", "书架"), T("Folders", "文件夹")],
    games: [T("Recently played", "最近游玩"), T("All systems", "全部平台"), T("Favorites", "收藏")],
  })[state.app];
}
function tabbar() {
  if (state.app === "browser") return `<nav class="tabs browser-tabs" data-scroll="browser-tabs" aria-label="${T("Browser tabs", "浏览器标签")}">${state.browser.tabs.map((item, index) => `<button class="tab ${index === state.browser.tab ? "active" : ""}" ${nav(`tab-${item.id}`, `browser-tab:${index}`)}>${E(item.title || T("New tab", "新标签"))}</button>`).join("")}<button class="tab" ${nav("new-tab", "new-tab")} aria-label="${T("New tab", "新标签")}">＋</button></nav>`;
  const labels = tabLabels();
  return `<nav class="tabs" aria-label="${T("Library sections", "媒体分类")}">${labels.map((label, index) => `<button class="tab ${index === state[state.app].tab ? "active" : ""}" ${nav(`section-${index}`, `tab:${index}`)}>${label}</button>`).join("")}</nav>`;
}
function heading(title, subtitle = "", aside = "") {
  return `<div class="section-head"><div><h1>${E(title)}</h1>${subtitle ? `<p class="subline">${E(subtitle)}</p>` : ""}</div>${aside ? `<span class="section-aside">${E(aside)}</span>` : ""}</div>`;
}
function hints() {
  let accept = T("Open", "打开"), back = T("Back", "返回"), context = T("Actions", "更多"), settings = T("Settings", "设置"), detail = T("L / R Sections", "L / R 切换分类");
  if (state.app === "music" && state.music.view === "now") { accept = state.music.playing ? T("Pause", "暂停") : T("Play", "播放"); back = T("Library", "媒体库"); detail = T("← / → Seek · L / R Tracks", "← / → 定位 · L / R 切歌"); }
  if (state.app === "video" && state.video.view === "playing") { accept = state.video.playing ? T("Pause", "暂停") : T("Play", "播放"); back = T("Library", "媒体库"); context = T("Tracks", "音轨字幕"); detail = T("← / → 10 sec · L / R Chapters", "← / → 10 秒 · L / R 章节"); }
  if (state.app === "reader" && state.reader.view === "reading") { accept = T("Contents", "目录"); detail = book().format === "PDF" ? T("Arrows Pan · L / R Pages", "方向键平移 · L / R 翻页") : T("← / → or L / R Turn page", "← / → 或 L / R 翻页"); }
  if (state.app === "browser") { accept = state.browser.mode === "navigation" ? T("Open", "打开") : T("Interact", "操作"); detail = T("L / R Tabs · Ctrl+L Address", "L / R 标签 · Ctrl+L 地址"); }
  if (state.app === "games" && state.games.view === "detail") { accept = T("Start", "启动"); detail = T("L / R Games", "L / R 切换游戏"); }
  if (state.modalStack.length) { accept = T("Confirm", "确认"); back = T("Back", "返回"); detail = T("↑ / ↓ Choose", "↑ / ↓ 选择"); }
  return `<footer class="footer ${state.app === "video" && state.video.view === "playing" ? "overlay-footer" : ""}"><div class="button-hints">${[["A", accept, "accept"], ["B", back, "back"], ["X", context, "context"], ["Y", settings, "settings"]].map(([key, label, action]) => `<button class="button-hint" data-action="dispatch:${action}" aria-label="${key} ${label}"><span class="keycap ${key === "A" ? "a" : ""}">${key}</span>${label}</button>`).join("")}</div><span class="footer-context">${detail}</span></footer>`;
}
function emptyCollection() {
  return `<div class="collection-empty"><h2>${state.query ? T("No matches found", "没有找到匹配内容") : T("Nothing here yet", "这里还没有内容")}</h2><p class="subline">${state.query ? E(state.query) : T("Try another section or add a content folder.", "可以切换分类，或添加内容文件夹。")}</p><button class="text-action" ${nav("clear-search", "clear-search")}>${state.query ? T("Clear search", "清除搜索") : T("Browse all", "浏览全部")}</button></div>`;
}
function musicView() {
  const current = track(), m = state.music;
  if (m.view === "now") return `<section class="content">${heading(T("Now playing", "正在播放"), `${current.album} · ${T("Local file", "本地文件")}`, "FLAC · 44.1 kHz / 16-bit")}<div class="player-layout">${art(current.albumId, "player-art", current.album)}<div><div class="eyebrow">${m.playing ? T("Playing", "播放中") : T("Paused", "已暂停")}</div><h2 class="track-title">${E(current.title)}</h2><p class="track-credit">${E(current.artist)}</p>${progress(m.position / current.seconds * 100, "music")}<div class="time-line"><span data-position="music">${time(m.position)}</span><span>${time(current.seconds)}</span></div><div class="transport"><button ${nav("music-prev", "track-step:-1")} aria-label="${T("Previous track", "上一曲")}">${icon("previous")}</button><button class="main-control" ${nav("music-toggle", "music-toggle")}>${icon(m.playing ? "pause" : "play")}${m.playing ? T("Pause", "暂停") : T("Play", "播放")}</button><button ${nav("music-next", "track-step:1")} aria-label="${T("Next track", "下一曲")}">${icon("next")}</button></div><p class="queue-banner">${T("Up next", "下一首")} · ${E(tracks.find(x => x.id === m.queue[m.queue.indexOf(current.id) + 1])?.title || T("End of queue", "队列末尾"))}</p><button class="text-action" ${nav("open-queue", "queue")}>${T("View queue", "查看播放队列")} · ${m.queue.length} ${T("tracks", "首")}</button></div></div></section>`;
  if (m.view === "album") {
    const album = albums.find(x => x.id === m.album);
    return `<section class="content">${heading(T("Album", "专辑"), `${album.year} · ${album.tracks.length} ${T("tracks", "首")} · ${album.length}`)}<div class="album-detail"><aside>${art(album.id, "art", album.title)}<h2>${E(album.title)}</h2><p class="subline">${E(album.artist)}</p><button class="text-action" ${nav("play-album", `play-album:${album.id}`)}>${icon("play")} ${T("Play album", "播放专辑")}</button></aside><div class="row-list scroll" data-scroll="album-tracks">${tracks.filter(x => x.albumId === album.id).map(x => row(`track-${x.id}`, x.title, x.id === current.id ? T("Now playing", "正在播放") : "", `play-track:${x.id}`, time(x.seconds), x.number)).join("")}</div></div></section>`;
  }
  if (m.tab === 1 || m.tab === 2) {
    const queue = m.tab === 2;
    const items = (queue ? m.queue.map(id => tracks.find(x => x.id === id)) : tracks).filter(x => x && matches(x.title + " " + x.artist));
    return `<section class="content">${heading(queue ? T("Your listening queue", "接下来听什么") : T("Every track, in one place", "所有曲目，一处浏览"), queue ? T("X to move or remove a track", "X 移动或移除曲目") : T("Search by title or artist", "按曲名或艺术家搜索"), `${items.length} ${T("tracks", "首")}`)}<div class="row-list scroll" data-scroll="tracks">${items.map((x, i) => row(`track-${x.id}`, x.title, `${x.artist} · ${x.album}`, `play-track:${x.id}`, x.id === current.id ? icon(m.playing ? "volume" : "pause") : time(x.seconds), queue ? i + 1 : "")).join("")}</div></section>`;
  }
  if (m.tab === 3) return folderView("Music", albums.map(x => ({ id: x.id, name: `${x.artist} / ${x.title}`, sub: `${x.tracks.length} ${T("tracks", "首")} · FLAC`, action: `album:${x.id}` })));
  return `<section class="content">${heading(T("Good music, close at hand.", "把喜欢的音乐带在身边"), state.query ? `${T("Search", "搜索")} · ${state.query}` : T("Your collection, ready when you are.", "你的收藏，随时可听。"), `${albums.filter(x => matches(x.title + x.artist)).length} ${T("albums", "张专辑")}`)}<div class="music-library"><div class="grid albums scroll" data-scroll="albums">${albums.filter(x => matches(x.title + x.artist)).map(x => `<button class="cover-card" ${nav(`album-${x.id}`, `album:${x.id}`)}>${art(x.id, "art", x.title)}<span class="card-title">${E(x.title)}</span><span class="card-meta">${E(x.artist)}</span></button>`).join("")}</div><aside class="now-aside"><div class="eyebrow">${T("Now playing", "正在播放")}</div>${art(current.albumId, "art", current.album)}<h2>${E(current.title)}</h2><p class="subline">${E(current.artist)}</p>${progress(m.position / current.seconds * 100, "music")}<div class="time-line"><span data-position="music">${time(m.position)}</span><span>${time(current.seconds)}</span></div><div class="mini-buttons"><button class="icon-button" ${nav("mini-prev", "track-step:-1")} aria-label="${T("Previous", "上一曲")}">${icon("previous")}</button><button class="icon-button primary" ${nav("mini-toggle", "music-toggle")} aria-label="${m.playing ? T("Pause", "暂停") : T("Play", "播放")}">${icon(m.playing ? "pause" : "play")}</button><button class="icon-button" ${nav("mini-next", "track-step:1")} aria-label="${T("Next", "下一曲")}">${icon("next")}</button></div><button class="text-action" ${nav("now-playing", "now")}>${T("Open player", "打开播放界面")} ${icon("arrow")}</button></aside></div></section>`;
}
function folderView(folder, items) {
  return `<section class="content">${heading(folder, `/home/demo/${folder}`, T("Local folders", "本地文件夹"))}<div class="row-list scroll" data-scroll="folders">${items.map(x => row(`folder-${x.id}`, x.name, x.sub, x.action, icon("folder"))).join("")}</div></section>`;
}
function subtitleLine() {
  const subtitle = state.video.subtitle;
  return subtitle === "Off" ? "" : `<p class="subtitle-line">${subtitle === "简体中文" ? "沿着这条路，总会找到方向。" : "The road has a way of finding you."}</p>`;
}
function videoView() {
  const v = state.video, item = video();
  if (v.view === "playing") return `<section class="playing-video" aria-label="${E(item.title)}">${art(item.id, "", item.title)}${v.controls ? `<div class="video-overlay"><div class="video-heading"><div><h1>${E(item.title)}</h1><p class="subline">${E(item.subtitle)} · ${item.detail}</p></div><span class="video-state">${v.playing ? T("Playing", "播放中") : T("Paused", "已暂停")}</span></div>${subtitleLine()}<div class="video-controls"><div class="time-line"><span data-position="video">${time(v.position)}</span><span>${time(item.duration)}</span></div>${progress(v.position / item.duration * 100, "video")}<div class="transport"><button ${nav("video-back10", "seek:-10")}>−10s</button><button class="main-control" ${nav("video-toggle", "video-toggle")}>${icon(v.playing ? "pause" : "play")}${v.playing ? T("Pause", "暂停") : T("Play", "播放")}</button><button ${nav("video-forward10", "seek:10")}>+10s</button><button ${nav("video-tracks", "video-tracks")}>${T("Subtitles & audio", "字幕与音轨")}</button></div></div></div>` : `${subtitleLine()}<span class="video-no-controls">A ${T("Show controls", "显示控制")} · B ${T("Back", "返回")}</span>`}</section>`;
  if (v.tab === 2) return folderView("Videos", ["Films", "Series", "Workshop"].map(id => ({ id, name: id, sub: `${videos.filter(x => x.folder === id).length} ${T("videos", "个视频")}`, action: `video-folder:${id}` })));
  const items = videos.filter(x => (!v.folder || x.folder === v.folder) && (v.tab !== 0 || x.position > 0) && matches(x.title));
  return `<section class="content">${heading(v.folder || (v.tab === 0 ? T("Pick up where you left off.", "接着上次，继续观看") : T("A little screen. A bigger world.", "小屏幕，也有大世界")), state.query || T("Films, series and your own recordings.", "电影、剧集，还有自己的影像。"), `${items.length} ${T("videos", "个视频")}`)}<div class="grid video-grid scroll" data-scroll="videos">${items.map(x => `<button class="cover-card video-card" ${nav(`video-${x.id}`, `video:${x.id}`)}><div class="video-thumb">${art(x.id, "art", x.title)}<span class="video-badge">${time(x.duration)}</span>${x.position ? progress(x.position / x.duration * 100) : ""}</div><span class="card-title">${E(x.title)}</span><span class="card-meta">${x.position ? `${T("Resume at", "从")} ${time(x.position)} ${T("", "继续")}` : x.subtitle}</span></button>`).join("")}</div></section>`;
}
function browserView() {
  const b = state.browser, tab = browserTab();
  const address = '<div class="address-row"><button class="icon-button" ' + nav("web-back", "web-back") + ' aria-label="' + T("Back in page history", "返回上一网页") + '" ' + (!tab.history.length ? "disabled" : "") + '>' + icon("back") + '</button><button class="address-bar" ' + nav("address", "address") + '>' + icon("browser") + '<span class="url">' + E(tab.url || T("Search or enter an address", "搜索或输入网址")) + '</span>' + icon("search") + '</button><button class="icon-button" ' + nav("bookmarks", "bookmarks") + ' aria-label="' + T("Bookmarks", "书签") + '">' + icon("star") + '</button></div>';
  if (!tab.url) return address + '<section class="content scroll" data-scroll="browser-home"><div class="browser-start"><div class="eyebrow">' + T("A window to the web", "打开互联网的一扇窗") + '</div><h1>' + T("Where would you like to go?", "今天想去哪里？") + '</h1><p class="subline">' + T("Your favorite places, one button away.", "常去的地方，按一下就到。") + '</p><div class="grid site-grid">' + sites.map(x => '<button class="site-card" ' + nav("site-" + x.id, "site:" + x.id) + '><span class="site-letter">' + x.letter + '</span><span class="row-title">' + E(x.title) + '</span><span class="card-meta">' + x.host + '</span></button>').join("") + '</div><div class="eyebrow">' + T("Recently visited", "最近访问") + '</div>' + (b.visits.length ? b.visits.slice(0,3).map((x,i) => row("visit-"+i, x.title, x.url, "visit:"+i, icon("clock"))).join("") : '<p class="subline">' + T("Pages you visit will appear here.", "访问过的网页会显示在这里。") + '</p>') + '</div></section>';
  const readMode = b.mode === "reader";
  const site = sites.find(x => tab.url.startsWith(x.url)) || sites[0];
  const article = {
    journal: ["The joy of a pocket computer", "A few tools, a little curiosity, and a whole world that fits in your bag. Making space for the things you love.", "The best computer is sometimes the one you already have with you. A place to listen, to read, and to follow a thought a little further."],
    wiki: ["A field guide to small computers", "A small computer brings a keyboard, a screen and familiar tools into one place.", "Start with a reliable way to navigate. Keep your notes close, and give every action a clear path back."],
    manual: ["At home with uDeck", "Use the direction keys to choose, A to open, and B to go back one level.", "Music, books and the web share the same focus outline. Your keyboard remains ready for ordinary text."],
    radio: ["A signal from somewhere", "Local Radio · Evening selections · Original sample page", "Take a moment, find a quiet place, and listen to the world around you. This offline page does not stream audio."]
  }[site.id];
  const banner = b.mode === "pointer" ? T("Pointer mode · Arrows move · A clicks · B returns to navigation", "指针模式 · 方向移动 · A 点击 · B 返回导航") : readMode ? T("Reading mode · ↑ / ↓ Scroll · B returns to the page", "阅读模式 · ↑ / ↓ 滚动 · B 返回网页") : b.mode === "text" ? T("Text input · Physical keyboard · Esc leaves the field", "文字输入 · 使用实体键盘 · Esc 离开输入框") : T("Page navigation · Arrows select links · X for page actions", "网页导航 · 方向键选择链接 · X 打开页面操作");
  return address + '<div class="mode-banner">' + icon(readMode ? "reader" : "browser") + '<span>' + banner + '</span></div><article tabindex="-1" class="web-page ' + (readMode ? "web-reading" : "") + '" style="--web-zoom:' + b.zoom + '" data-scroll="web-page"><div class="web-nav"><strong>' + E(site.title) + '</strong><span>Field notes / 08</span></div><div class="web-columns"><div><div class="web-kicker" style="margin-top:25px">FIELD NOTES / NO. 08</div><h1>' + E(article[0]) + '</h1><p>' + E(article[1]) + '</p>' + (!readMode ? '<button class="web-link" ' + nav("article-read", "reader-mode") + '>Read the story ' + icon("arrow") + '</button>' : '') + '</div>' + (!readMode ? art("making-room", "web-illustration", "Original landscape illustration") : "") + '</div><p>' + E(article[2]) + '</p><p>Good tools leave room for attention. A little space to think, a reliable place to return, and enough time to follow one idea to the next.</p><button class="web-link" ' + nav("article-next", "web-next") + '>More field notes ' + icon("arrow") + '</button>' + (b.mode === "text" ? '<input class="text-input" aria-label="' + T("Message to the journal", "给期刊留言") + '" placeholder="Write a note" value="' + E(state.query) + '" data-inline-input><p class="web-input-note">' + T("Draft stays on this page; nothing is sent.", "草稿保留在此页面，不会发送。") + '</p>' : "") + (b.mode === "pointer" ? '<span class="virtual-cursor" style="left:' + b.pointer.x + 'px;top:' + b.pointer.y + 'px"></span>' : "") + '</article>';
}
function readerBlocks(item = book(), page = state.reader.page) {
  if (item.format === "PDF") return ["Windows and input", "A small computer should feel just as complete when it is operated with physical buttons. Every view needs a visible focus, a clear action, and a reliable way back.", "Input follows the active application. Release held buttons when ownership changes, and wait until the target window has focus before forwarding new actions."];
  if (item.format === "TXT") return ["从这里开始", "把电脑装进口袋，也把熟悉的操作方式带在身边。方向键移动焦点，A 进入，B 返回。每一次返回，都应该回到刚刚离开的地方。", "阅读时不需要寻找细小的按钮。L 和 R 翻页，X 打开目录、书签与搜索，Y 调整字号和配色。合上书，下次从这里继续。", "普通键盘上的字母保持原样，不会因为它们恰好写作 A、B、X、Y 就触发界面动作。"];
  return readingPages[(page - 1) % readingPages.length];
}
function pdfScale() {
  return state.reader.pdfZoom === "fit" ? (root.clientWidth - (root.clientWidth <= 1100 ? 128 : 166)) / 680 : state.reader.pdfZoom;
}
function readerView() {
  const r = state.reader, item = book();
  if (r.view === "reading") {
    const blocks = readerBlocks(), scale = pdfScale();
    const text = '<h1>' + highlight(blocks[0], r.query) + '</h1>' + blocks.slice(1).map(text => '<p>' + highlight(text, r.query) + '</p>').join("");
    const content = item.format === "PDF" ? '<div class="pdf-canvas" style="width:' + 680 * scale + 'px;height:' + 880 * scale + 'px"><div class="pdf-sheet" style="transform:scale(' + scale + ')"><div class="eyebrow" style="color:#576b5a">UDECK FIELD EDITIONS / TECHNICAL NOTES · ' + r.page + '</div>' + text + '<div class="diagram"><span>Controller</span>→<span>Focus</span>→<span>Application</span></div></div></div>' : text;
    return '<section tabindex="-1" class="reader-view ' + (r.dark ? "dark" : "") + '" style="--reading-size:' + r.size + 'px"><div class="reading-head"><span>' + E(item.title) + '</span><span>' + (item.format === "PDF" ? (r.pdfZoom === "fit" ? T("Fit width", "适宽") : Math.round(scale * 100) + "%") : E(item.chapter)) + (r.bookmarks.includes(item.id + ":" + r.page) ? " · ★" : "") + '</span></div><div class="reading-body" data-scroll="reading-body">' + content + '</div><div class="reading-foot"><span>' + r.page + ' / ' + item.pages + '</span>' + progress(r.page / item.pages * 100) + '<span>' + Math.round(r.page / item.pages * 100) + '% · ' + item.format + '</span></div></section>';
  }
  if (r.tab === 2) return folderView("Documents", books.map(x => ({ id: x.id, name: x.title + "." + x.format.toLowerCase(), sub: x.format, action: "book:" + x.id })));
  const items = books.filter(x => matches(x.title + x.author));
  return '<section class="content">' + heading(r.tab === 0 ? T("A few pages, just for you.", "留一点时间，读几页书") : T("Your pocket bookshelf", "口袋里的书架"), T("Pick up a book. Leave the rest behind.", "翻开一本书，让时间慢下来。"), items.length + " " + T("documents", "份文档")) + '<div class="grid book-grid scroll" data-scroll="books">' + items.map(x => {
    const page = r.positions[x.id] || x.page;
    return '<button class="cover-card book-card" ' + nav("book-" + x.id, "book:" + x.id) + '>' + art(x.id, "art", x.title) + '<div><div class="card-title">' + E(x.title) + '</div><div class="card-meta">' + E(x.author) + '</div><div class="card-meta" style="margin-top:8px">' + x.format + ' · ' + page + ' / ' + x.pages + '</div>' + progress(page / x.pages * 100) + '<div class="card-meta">' + T("Continue reading", "继续阅读") + ' · ' + Math.round(page / x.pages * 100) + '%</div></div></button>';
  }).join("") + '</div></section>';
}
function gameSummary() {
  const item = game();
  return '<div class="eyebrow">' + T("Selected game", "当前游戏") + '</div><h2>' + E(item.title) + '</h2><p>' + E(item.description[state.language === "zh_CN" ? 1 : 0]) + '</p>' + art(item.id, "save-thumb", item.title) + '<div class="subline">' + item.system + ' · ' + item.time + '</div><button class="text-action" ' + nav("game-resume", "game:" + item.id) + '>' + T("View game", "查看游戏") + ' ' + icon("arrow") + '</button>';
}
function gamesView() {
  const g = state.games, item = game();
  if (g.view === "running") return `<section class="game-running">${art(item.id === "pocket-orchard" ? "orchard-screen" : item.id, "game-screen", "Original gameplay layout study, not a running emulator")}<span class="game-caption">${E(item.title)} · ${item.system}</span><span class="game-return">Ctrl + Alt + M · ${T("Game menu", "游戏菜单")}</span></section>`;
  if (g.view === "detail") return `<section class="content">${heading(item.title, `${item.system} · ${item.year} · ${item.genre}`, g.favorites.includes(item.id) ? `★ ${T("Favorite", "已收藏")}` : "")}<div class="game-detail">${art(item.id, "art", item.title)}<div><div class="eyebrow">${T("Your next little adventure", "下一段小小冒险")}</div><p class="description">${E(item.description[state.language === "zh_CN" ? 1 : 0])}</p><dl class="metadata"><dt>${T("Play time", "游玩时长")}</dt><dd>${item.time}</dd><dt>${T("Emulator", "模拟器核心")}</dt><dd>${item.core}</dd><dt>${T("Source", "来源")}</dt><dd>SD / Games / ${item.system}</dd></dl><div class="action-row"><button class="primary-action" ${nav("game-launch", "game-launch")}>${icon("play")}${hasGameSave(item) ? T("Continue", "继续游戏") : T("Start game", "开始游戏")}</button><button class="secondary-action" ${nav("game-new", "game-new")}>${T("Start fresh", "重新开始")}</button></div>${hasGameSave(item) ? `<div class="save-summary">${art("orchard-screen", "save-thumb", "Sample save preview")}<span class="quiet"><strong>${T("Last session", "上次游玩")}</strong>${T("Automatic save", "自动存档")} · ${T("Today", "今天")} 18:42</span></div>` : ""}</div></div></section>`;
  const candidates = g.tab === 0 ? g.recent.map(id => games.find(x => x.id === id)).filter(Boolean) : games;
  const items = candidates.filter(x => (g.system === "All" || x.system === g.system) && (g.tab !== 2 || g.favorites.includes(x.id)) && matches(x.title));
  if (items.length && !items.some(x => x.id === g.selected)) g.selected = items[0].id;
  return `<section class="content">${heading(T("One more adventure.", "再来一段冒险"), T("Your games. Your place to return to.", "喜欢的游戏，总有地方继续。"), `${items.length} ${T("games", "个游戏")}`)}${g.tab === 1 ? `<div class="game-systems" style="margin-bottom:18px">${["All", "GB", "GBA", "SNES", "PS1"].map(system => `<button class="system-chip ${g.system === system ? "active" : ""}" ${nav(`system-${system}`, `system:${system}`)}>${system === "All" ? T("All", "全部") : system}</button>`).join("")}</div>` : ""}<div class="game-library"><div class="grid game-grid scroll" data-scroll="games">${items.map(x => `<button class="cover-card game-card" ${nav(`game-${x.id}`, `game:${x.id}`)}>${art(x.id, "art", x.title)}<span class="card-title">${E(x.title)}</span><span class="card-meta">${x.system} ${g.favorites.includes(x.id) ? " · ★" : ""}</span></button>`).join("") || emptyCollection()}</div><aside class="game-summary">${gameSummary()}</aside></div></section>`;
}
function matches(text) { return !state.query || text.toLocaleLowerCase().includes(state.query.toLocaleLowerCase()); }
function highlight(text, query) {
  if (!query) return E(text);
  return text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi")).map((part, i) => i % 2 ? `<mark>${E(part)}</mark>` : E(part)).join("");
}

function scenarioView() {
  const s = state.scenario, browser = state.app === "browser";
  const copy = browser ? {
    empty: ["bookmark", T("A new place to start", "从这里开始上网"), T("Add a bookmark or enter an address. Your browsing history will appear here.", "可以添加书签或输入网址，访问历史会保留在这里。"), T("Enter address", "输入网址"), "address"],
    loading: ["clock", T("Opening the page…", "正在打开网页…"), T("Other tabs stay available. You can stop loading and return to your start page.", "可以使用其他标签，也可以停止加载并返回起始页。"), T("Stop loading", "停止加载"), "browser-home"],
    error: ["error", T("This page could not be opened", "暂时无法打开网页"), T("Check the address or try again. Your tabs and bookmarks have been kept.", "请检查网址或重试，标签与书签已保留。"), T("Try again", "重试"), "retry"],
    removed: ["wifi", T("Your connection is unavailable", "网络连接暂时不可用"), T("This page is kept. Reconnect, then reload when you are ready.", "已保留当前页面，重新联网后可以再次加载。"), T("Try again", "重试"), "retry"],
  }[s] : {
    empty: ["folder", T("Your library starts here", "从这里建立内容库"), T("Choose a local folder or a removable drive. Your files stay where they are.", "选择本地文件夹或移动存储，文件会留在原来的位置。"), T("Choose folder", "选择文件夹"), "choose-source"],
    loading: ["clock", T("Looking for your files…", "正在查找内容…"), T("Scanning does not change your files. You can cancel and keep browsing.", "扫描不会更改文件，可以取消并继续浏览。"), T("Cancel scan", "取消扫描"), "scan-cancel"],
    error: ["error", T("This item could not be opened", "暂时无法打开此项目"), T("The file may be incomplete or use an unsupported format. Your library entry and position are kept.", "文件可能不完整或格式暂不支持，已保留内容库条目与位置。"), T("Try again", "重试"), "retry"],
    removed: ["usb", T("Your SD card is no longer available", "SD 卡暂时不可用"), state.app === "games" ? T("The game has stopped. Existing saves stay in local storage. No new save is claimed; check the card before launching again.", "已停止游戏，本地已有存档保留。没有写入新的存档，请检查存储卡后再启动。") : T("Playback or reading is paused. Reconnect the card to return to the same item.", "已暂停播放或阅读，重新接入后可以回到原来的内容。"), T("Check again", "重新检测"), "retry"],
  }[s];
  return '<section class="content"><div class="empty-state">' + (s === "loading" ? '<div class="spinner" aria-label="' + T("Loading", "正在加载") + '"></div>' : icon(copy[0])) + '<h1>' + copy[1] + '</h1><p>' + copy[2] + '</p><button class="primary-action" ' + nav("scenario-action", copy[4]) + '>' + copy[3] + '</button>' + (s === "removed" && !browser ? '<button class="text-action" ' + nav("another-source", "choose-source") + '>' + T("Choose another source", "选择其他来源") + '</button>' : "") + '<span class="details">' + (browser ? "journal.example" : s === "removed" ? "SD / Media · /media/demo/POCKET" : T("Local files · Folders · Removable storage", "本地文件 · 文件夹 · 移动存储")) + '</span></div></section>';
}
function initialFocus() {
  if (state.scenario !== "ready") return "scenario-action";
  if (state.app === "music") return state.music.view === "now" ? "music-toggle" : state.music.view === "album" ? `track-${tracks.find(x => x.albumId === state.music.album).id}` : state.music.tab === 0 ? "album-after-hours" : state.music.tab === 3 ? "folder-after-hours" : `track-${state.music.tab === 2 ? state.music.queue[0] : tracks[0].id}`;
  if (state.app === "video") return state.video.view === "playing" ? "video-toggle" : "video-open-road";
  if (state.app === "browser") return browserTab().url ? "article-read" : "site-journal";
  if (state.app === "reader") return "book-small-journeys";
  return state.games.view === "detail" ? "game-launch" : `game-${state.games.selected}`;
}
function render() {
  const key = root.dataset.viewKey;
  for (const element of root.querySelectorAll("[data-scroll]")) scrollCache.set(`${key}:${element.dataset.scroll}`, element.scrollTop);
  const input = root.querySelector("input:focus");
  const caret = input?.selectionStart;
  const fullVideo = state.app === "video" && state.video.view === "playing" && state.scenario === "ready";
  const fullGame = state.app === "games" && state.games.view === "running" && state.scenario === "ready";
  let content = state.scenario !== "ready" ? scenarioView() : ({ music: musicView, video: videoView, browser: browserView, reader: readerView, games: gamesView })[state.app]();
  const showTabs = !fullVideo && !fullGame && (state.app === "browser" || state[state.app].view === "library");
  root.innerHTML = `${!fullVideo && !fullGame ? header() : ""}${showTabs ? tabbar() : ""}${content}${!fullGame && (!fullVideo || state.video.controls) ? hints() : ""}${state.toast ? `<div class="toast" role="status">${E(state.toast)}</div>` : ""}${renderModal()}`;
  for (const empty of root.querySelectorAll(".albums, .video-grid, .book-grid, [data-scroll=tracks]")) {
    if (!empty.children.length) empty.innerHTML = emptyCollection();
  }
  root.dataset.viewKey = viewKey();
  root.dataset.app = state.app;
  root.dataset.scenario = state.scenario;
  document.documentElement.lang = state.language === "zh_CN" ? "zh-CN" : "en";
  for (const element of root.querySelectorAll("[data-scroll]")) element.scrollTop = scrollCache.get(`${viewKey()}:${element.dataset.scroll}`) || 0;
  const pointerPage = root.querySelector(".web-page"), cursor = pointerPage?.querySelector(".virtual-cursor");
  if (cursor) { cursor.style.left = `${state.browser.pointer.x + pointerPage.scrollLeft}px`; cursor.style.top = `${state.browser.pointer.y + pointerPage.scrollTop}px`; }
  const modal = state.modalStack.at(-1);
  if (modal?.type === "text") {
    const field = root.querySelector("[data-modal-input]");
    field.focus({ preventScroll: true });
    if (caret != null) field.setSelectionRange(caret, caret);
  } else if (state.app === "browser" && state.browser.mode === "text" && !modal) {
    const field = root.querySelector("[data-inline-input]");
    field?.focus({ preventScroll: true });
    if (field && caret != null) field.setSelectionRange(caret, caret);
  } else if (!modal && state.scenario === "ready" && state.app === "browser" && ["reader", "pointer"].includes(state.browser.mode)) {
    root.querySelector(".web-page")?.focus({ preventScroll: true });
  } else if (!modal && state.app === "reader" && state.reader.view === "reading" && state.scenario === "ready") {
    root.querySelector(".reader-view")?.focus({ preventScroll: true });
  } else focus(modal ? `modal-${modal.index}` : state.focus || initialFocus());
  document.querySelector("#application").value = state.app;
  document.querySelector("#language").value = state.language;
  document.querySelector("#scenario").value = state.scenario;
}
function focus(id, scroll = true) {
  const options = focusable();
  const element = options.find(x => x.dataset.nav === id) || options.find(x => !x.classList.contains("tab")) || options[0];
  root.querySelectorAll(".focused").forEach(x => x.classList.remove("focused"));
  if (!element) return;
  state.focus = element.dataset.nav;
  const modal = state.modalStack.at(-1);
  if (modal?.type === "menu") modal.index = Number(element.dataset.nav.slice(6));
  element.classList.add("focused"); element.focus({ preventScroll: true });
  if (scroll) element.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
  if (!state.modalStack.length && state.app === "games" && state.games.view === "library" && element.dataset.nav.startsWith("game-") && games.some(x => `game-${x.id}` === element.dataset.nav)) {
    state.games.selected = element.dataset.nav.slice(5);
    const panel = root.querySelector(".game-summary");
    if (panel) panel.innerHTML = gameSummary();
  }
}
function focusable() {
  const owner = root.querySelector(".modal") || root;
  return [...owner.querySelectorAll("[data-nav]:not(:disabled)")].filter(x => x.getClientRects().length);
}
function move(direction) {
  const modal = state.modalStack.at(-1);
  if (modal) {
    if (modal.type === "text") return;
    const delta = direction === "up" || direction === "left" ? -1 : 1;
    const enabled = modal.options.flatMap((option, index) => option.disabled ? [] : [index]);
    const current = Math.max(0, enabled.indexOf(modal.index));
    modal.index = enabled[Math.max(0, Math.min(enabled.length - 1, current + delta))];
    render(); return;
  }
  if (state.app === "music" && state.music.view === "now" && ["left", "right"].includes(direction)) { seek(direction === "left" ? -10 : 10); return; }
  if (state.app === "video" && state.video.view === "playing" && ["left", "right"].includes(direction)) { seek(direction === "left" ? -10 : 10); return; }
  if (state.app === "reader" && state.reader.view === "reading") {
    if (["left", "right"].includes(direction)) {
      if (book().format === "PDF") root.querySelector(".reading-body")?.scrollBy({ left: direction === "left" ? -130 : 130 });
      else turnPage(direction === "left" ? -1 : 1);
      return;
    }
    root.querySelector(".reading-body")?.scrollBy({ top: direction === "down" ? 130 : -130 }); return;
  }
  if (state.app === "browser" && state.browser.mode !== "navigation") {
    if (state.browser.mode === "reader" && ["up", "down"].includes(direction)) root.querySelector(".web-page")?.scrollBy({ top: direction === "down" ? 160 : -160 });
    if (state.browser.mode === "pointer") {
      const page = root.querySelector(".web-page");
      const p = state.browser.pointer;
      p.x = Math.max(0, Math.min(page.clientWidth - 22, p.x + (direction === "right" ? 26 : direction === "left" ? -26 : 0)));
      p.y = Math.max(0, Math.min(page.clientHeight - 28, p.y + (direction === "down" ? 26 : direction === "up" ? -26 : 0)));
      const cursor = page.querySelector(".virtual-cursor");
      cursor.style.left = `${p.x + page.scrollLeft}px`; cursor.style.top = `${p.y + page.scrollTop}px`;
    }
    return;
  }
  const options = focusable(), current = options.find(x => x.dataset.nav === state.focus) || options[0];
  if (!current) return;
  const a = current.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  const candidates = options.filter(x => x !== current).map(element => {
    const b = element.getBoundingClientRect(), dx = b.left + b.width / 2 - ax, dy = b.top + b.height / 2 - ay;
    const forward = direction === "left" ? -dx : direction === "right" ? dx : direction === "up" ? -dy : dy;
    const side = ["left", "right"].includes(direction) ? Math.abs(dy) : Math.abs(dx);
    return { element, forward, score: forward + side * 3 };
  }).filter(x => x.forward > 6).sort((a, b) => a.score - b.score);
  if (candidates[0]) focus(candidates[0].element.dataset.nav);
}
function navigate(view, fields = {}) {
  dismissToast();
  const current = state[state.app];
  (state.history[state.app] ||= []).push({ view: current.view, tab: current.tab, album: current.album, selected: current.selected, folder: current.folder, focus: state.focus, query: state.query });
  Object.assign(current, fields, { view }); state.focus = ""; render();
}
function switchApp(id) {
  if (!appIds.includes(id)) return;
  dismissToast();
  state.modalStack = []; state.history.appFocus ||= {}; state.history.appFocus[state.app] = state.focus;
  state.app = id; state.focus = state.history.appFocus[id] || ""; state.query = ""; state.toast = "";
  document.title = `uDeck · ${names()[id]}`;
  render();
}
function switchTab(index) {
  if (state.modalStack.length) return;
  const item = state[state.app], labels = tabLabels();
  if (index < 0 || index >= labels.length) return;
  item.tabFocus ||= {}; item.tabFocus[item.tab] = state.focus;
  item.tab = index; item.view = "library"; if (state.app === "video") item.folder = ""; state.query = ""; state.focus = item.tabFocus[index] || "";
  if (state.app === "games" && index !== 1) item.system = "All";
  state.history[state.app] = []; render();
}
function back() {
  if (state.modalStack.length) {
    const modal = state.modalStack.pop(); state.focus = modal.returnFocus; render(); return;
  }
  if (state.app === "games" && state.games.view === "running") return;
  if (state.app === "browser") {
    if (state.browser.mode !== "navigation") { state.browser.mode = "navigation"; state.focus = state.browser.returnFocus || "article-read"; render(); return; }
    if (browserTab().history.length || browserTab().url) { webBack(); return; }
  }
  if (state.app === "reader" && state.reader.view === "reading") saveReading();
  if (state.app === "video" && state.video.view === "playing") { state.video.playing = false; video().position = state.video.position; }
  const previous = state.history[state.app]?.pop();
  if (previous) { const { focus: id, query, ...fields } = previous; Object.assign(state[state.app], fields); state.focus = id; state.query = query; render(); return; }
  if (state[state.app].view && state[state.app].view !== "library") { state[state.app].view = "library"; state.focus = ""; render(); return; }
  appMenu();
}
function setLanguage(language) { state.language = language === "zh_CN" ? "zh_CN" : "en"; persist(); render(); }
function setScenario(value) {
  dismissToast();
  state.scenario = ["ready", "empty", "loading", "error", "removed"].includes(value) ? value : "ready";
  if (state.scenario !== "ready") {
    state.modalStack = [];
    if (state.app === "music") state.music.playing = false;
    if (state.app === "video") state.video.playing = false;
    if (state.app === "reader" && state.reader.view === "reading") saveReading();
    if (state.app === "games" && state.games.view === "running") state.games.view = "detail";
  }
  state.focus = ""; render();
}
function menu(title, options, body = "", index = 0) {
  dismissToast();
  if (!options.some(option => !option.disabled)) options = [...options, { label: () => T("Back", "返回"), run: () => {} }];
  if (options[index]?.disabled) index = options.findIndex(option => !option.disabled);
  state.modalStack.push({ type: "menu", title, options, body, index, returnFocus: state.focus }); render();
}
function textPrompt(title, body, value, accept) {
  state.modalStack.push({ type: "text", title, body, text: value, accept, index: 0, returnFocus: state.focus }); render();
}
function confirm(title, body, accept, positive = () => T("Confirm", "确认")) {
  menu(title, [{ label: () => T("Cancel", "取消"), run: () => {} }, { label: positive, run: accept }], body);
}
const label = value => typeof value === "function" ? value() : value;
function renderModal() {
  const modal = state.modalStack.at(-1);
  if (!modal) return "";
  return `<div class="modal-shade"><section class="modal" role="dialog" aria-modal="true" aria-label="${E(label(modal.title))}"><h1>${E(label(modal.title))}</h1>${modal.body ? `<p class="modal-body">${E(label(modal.body))}</p>` : ""}${modal.type === "text" ? `<input class="text-input" data-modal-input aria-label="${E(label(modal.title))}" value="${E(modal.text)}" autocomplete="off"><div class="modal-actions"><button class="secondary-action" data-nav="modal-cancel" data-action="dispatch:back">${T("Cancel", "取消")}</button><button class="primary-action" data-nav="modal-submit" data-action="text-submit">${T("Confirm", "确认")}</button></div>` : `<div class="row-list modal-options" data-scroll="modal">${modal.options.map((option, index) => `<button class="row-item" ${nav(`modal-${index}`, `modal:${index}`)} ${option.disabled ? "disabled" : ""}><span class="row-copy"><span class="row-title">${E(label(option.label))}</span>${option.subtitle ? `<span class="row-subtitle">${E(label(option.subtitle))}</span>` : ""}</span><span class="row-end">${option.child ? icon("arrow") : label(option.selected) ? "✓" : ""}</span></button>`).join("")}</div>`}<p class="modal-footer">${modal.type === "text" ? T("Physical keyboard · Enter Confirm · Esc Cancel", "实体键盘输入 · Enter 确认 · Esc 取消") : T("A Confirm · B Back", "A 确认 · B 返回")}</p></section></div>`;
}
function choose(index) {
  const modal = state.modalStack.at(-1), option = modal?.options?.[index];
  if (!option || option.disabled) return;
  modal.index = index;
  if (!option.keep && !option.child) { state.modalStack.pop(); state.focus = modal.returnFocus; }
  option.run?.(); render();
}
function textSubmit() {
  const modal = state.modalStack.at(-1);
  if (modal?.type !== "text") return;
  const result = modal.accept(modal.text);
  if (result === false) return;
  if (state.modalStack.includes(modal)) state.modalStack.splice(state.modalStack.indexOf(modal), 1);
  state.focus = modal.returnFocus; render();
}
function appMenu() {
  menu(() => T("Your uDeck", "你的 uDeck"), appIds.map(id => ({ label: () => names()[id], subtitle: () => ({ music: T("Albums, tracks and listening queues", "专辑、曲目与播放队列"), video: T("Films and a place to continue", "电影与继续观看"), browser: T("Bookmarks, tabs and the web", "书签、标签与网页"), reader: T("Books, documents and quiet time", "书籍、文档与阅读时光"), games: T("Your library of little adventures", "你的游戏冒险库") })[id], run: () => switchApp(id) })));
}
function settings() {
  if (state.app === "games" && state.games.view === "running") { gameMenu(); return; }
  const options = [
    { label: () => T("Interface language", "界面语言"), subtitle: () => state.language === "en" ? "English" : "简体中文", child: true, run: languageMenu },
    { label: () => T("Content folders", "内容文件夹"), subtitle: "/home/demo · SD / Media", child: true, run: chooseSource },
  ];
  if (["music", "video"].includes(state.app)) options.unshift({ label: () => T("Audio output", "音频输出"), subtitle: () => state.audioOutput === "speaker" ? T("Built-in speaker", "内置扬声器") : "Studio Headphones", child: true, run: () => menu(() => T("Audio output", "音频输出"), [
    { label: () => T("Built-in speaker", "内置扬声器"), selected: () => state.audioOutput === "speaker", run: () => { state.audioOutput = "speaker"; } },
    { label: "Studio Headphones", subtitle: () => T("Bluetooth · Connected", "蓝牙 · 已连接"), selected: () => state.audioOutput === "headphones", run: () => { state.audioOutput = "headphones"; } },
  ]) });
  if (state.app === "reader" && state.reader.view === "reading") options.unshift(
    book().format === "PDF" ? { label: () => T("PDF zoom", "PDF 缩放"), child: true, run: pdfZoomMenu } : { label: () => T("Text size", "字号"), subtitle: () => `${state.reader.size} px`, child: true, run: () => menu(() => T("Text size", "字号"), [22, 24, 28, 32].map(size => ({ label: `${size} px`, selected: size === state.reader.size, run: () => { state.reader.size = size; } }))) },
    { label: () => T("Reading color", "阅读配色"), subtitle: () => state.reader.dark ? T("Night", "夜间") : T("Paper", "纸张"), run: () => { state.reader.dark = !state.reader.dark; } },
  );
  if (state.app === "browser") options.unshift(
    { label: () => T("Page interaction", "网页操作"), child: true, run: browserModes },
    { label: () => T("Text size", "文字大小"), subtitle: () => `${Math.round(state.browser.zoom * 100)}%`, child: true, run: () => menu(() => T("Text size", "文字大小"), [1, 1.25, 1.5].map(zoom => ({ label: `${Math.round(zoom * 100)}%`, selected: () => state.browser.zoom === zoom, run: () => { state.browser.zoom = zoom; } }))) },
  );
  if (state.app === "games") options.unshift(
    { label: () => T("Emulator setup", "模拟器设置"), child: true, run: () => menu(() => T("Emulator setup", "模拟器设置"), [
      { label: "Game Boy · Gambatte", subtitle: () => T("Ready", "已就绪"), run: () => notify(T("Per-system settings kept", "平台设置已保留")) },
      { label: "Game Boy Advance · mGBA", subtitle: () => T("Ready", "已就绪"), run: () => notify(T("Per-system settings kept", "平台设置已保留")) },
      { label: "PlayStation · PCSX ReARMed", subtitle: () => T("Check firmware for each game", "启动前检查所需固件"), run: () => notify(T("Firmware directory · SD / BIOS", "固件目录 · SD / BIOS")) },
    ]) },
    { label: () => T("Controller & return shortcut", "手柄与返回快捷键"), subtitle: "Ctrl + Alt + M", run: () => notify(T("Game input belongs to the emulator. Ctrl+Alt+M opens its menu.", "游戏输入交给模拟器，Ctrl+Alt+M 打开菜单。")) },
  );
  menu(() => T(`${names()[state.app]} settings`, `${names()[state.app]}设置`), options);
}
function languageMenu() {
  menu(() => T("Interface language", "界面语言"), [
    { label: "English", keep: true, selected: () => state.language === "en", run: () => setLanguage("en") },
    { label: "简体中文", keep: true, selected: () => state.language === "zh_CN", run: () => setLanguage("zh_CN") },
  ], () => T("Applies to the interface. Your content stays as it is.", "立即更新界面，内容保持原文。"), state.language === "en" ? 0 : 1);
}
function chooseSource() {
  menu(() => T("Choose content folder", "选择内容文件夹"), [
    { label: () => T("Home folder", "个人文件夹"), subtitle: "/home/demo", run: () => { state.scenario = "ready"; state.modalStack = []; state.focus = ""; notify(T("Folder added to your library", "文件夹已加入媒体库")); } },
    { label: "SD / Media", subtitle: state.scenario === "removed" ? () => T("Not connected", "未连接") : "/media/demo/POCKET", disabled: state.scenario === "removed", run: () => { state.scenario = "ready"; state.modalStack = []; state.focus = ""; } },
    { label: () => T("Enter a folder path…", "输入文件夹路径…"), child: true, run: () => textPrompt(() => T("Folder path", "文件夹路径"), () => T("Choose a local folder. Files will not be moved.", "选择本地文件夹，原文件不会移动。"), "/home/demo/", path => { if (!path.startsWith("/") || path.includes("\0")) { notify(T("Enter an absolute local path", "请输入完整的本地路径")); return false; } state.scenario = "ready"; state.modalStack = []; state.focus = ""; return true; }) },
  ]);
}
function context() {
  if (state.modalStack.length) return;
  if (state.app === "music") {
    const queueId = state.focus.startsWith("track-") ? state.focus.slice(6) : track().id;
    const albumId = state.focus.startsWith("album-") ? state.focus.slice(6) : state.music.album;
    const options = [
      { label: () => T("Search music", "搜索音乐"), child: true, run: search },
      { label: () => T("Now playing", "正在播放"), run: () => navigate("now") },
      { label: () => T("Add to end of queue", "添加到队列末尾"), run: () => { const ids = state.focus.startsWith("album-") ? tracks.filter(x => x.albumId === albumId).map(x => x.id) : [queueId]; state.music.queue.push(...ids.filter(id => !state.music.queue.includes(id))); notify(T("Added to the queue", "已加入播放队列")); } },
      { label: () => state.music.shuffle ? T("Shuffle · On", "随机播放 · 开") : T("Shuffle · Off", "随机播放 · 关"), run: () => { state.music.shuffle = !state.music.shuffle; } },
      { label: () => state.music.repeat ? T("Repeat queue · On", "循环队列 · 开") : T("Repeat queue · Off", "循环队列 · 关"), run: () => { state.music.repeat = !state.music.repeat; } },
    ];
    if (state.music.tab === 2 && state.music.view === "library") options.unshift(
      { label: () => T("Move up in queue", "在队列中上移"), run: () => { const i = state.music.queue.indexOf(queueId); if (i > 0) [state.music.queue[i - 1], state.music.queue[i]] = [state.music.queue[i], state.music.queue[i - 1]]; } },
      { label: () => T("Remove from queue", "从队列移除"), run: () => { const i = state.music.queue.indexOf(queueId); const next = state.music.queue[i + 1] || state.music.queue[i - 1]; state.music.queue = state.music.queue.filter(id => id !== queueId); state.focus = next ? `track-${next}` : ""; } },
    );
    menu(() => T("Music actions", "音乐操作"), options); return;
  }
  if (state.app === "video") { state.video.view === "playing" ? videoTracks() : menu(() => T("Video actions", "视频操作"), [{ label: () => T("Search videos", "搜索视频"), child: true, run: search }, { label: () => T("Open file or folder", "打开文件或文件夹"), child: true, run: chooseSource }]); return; }
  if (state.app === "reader") { readerActions(); return; }
  if (state.app === "browser") {
    menu(() => T("Page actions", "网页操作"), [
      { label: () => T("Enter address", "输入网址"), child: true, run: addressPrompt },
      { label: () => T("New tab", "新标签"), run: newTab },
      { label: () => T("Bookmarks", "书签"), child: true, run: bookmarkMenu },
      { label: () => T("History", "历史记录"), child: true, run: historyMenu },
      { label: () => T("Add this page to bookmarks", "收藏当前网页"), disabled: !browserTab().url, run: () => { if (!state.browser.bookmarks.includes(browserTab().url)) state.browser.bookmarks.push(browserTab().url); persist(); notify(T("Bookmark saved", "书签已保存")); } },
      { label: () => T("Page interaction", "网页操作模式"), child: true, run: browserModes },
      { label: () => T("Close this tab", "关闭当前标签"), run: () => { state.browser.tabs.splice(state.browser.tab, 1); state.browser.tab = Math.max(0, state.browser.tab - 1); if (!state.browser.tabs.length) state.browser.tabs.push({ id: `tab-${++tabSequence}`, title: "", url: "", history: [] }); state.browser.mode = "navigation"; state.focus = ""; } },
    ]); return;
  }
  if (state.games.view === "running") { gameMenu(); return; }
  const item = state.games.view === "detail" ? game() : games.find(x => `game-${x.id}` === state.focus) || game();
  menu(() => T("Game actions", "游戏操作"), [
    { label: () => state.games.favorites.includes(item.id) ? T("Remove from favorites", "取消收藏") : T("Add to favorites", "加入收藏"), run: () => { const list = state.games.favorites; state.games.favorites = list.includes(item.id) ? list.filter(id => id !== item.id) : [...list, item.id]; persist(); } },
    { label: () => T("Search games", "搜索游戏"), child: true, run: search },
    { label: () => T("Load saved game", "读取已有存档"), child: true, run: () => saveSlots(true) },
    { label: () => T("Emulator details", "模拟器信息"), subtitle: item.core, child: true, run: () => menu(() => T("Emulator details", "模拟器信息"), [{ label: () => T("Back", "返回"), run: () => {} }], () => `${item.core} · ${item.missingCore ? T("Not installed", "未安装") : T("Installed", "已安装")} · ${item.system}`) },
  ]);
}

function search() {
  textPrompt(() => T("Search your library", "搜索媒体库"), () => T("Type a title, name or artist. Ordinary letters stay ordinary letters.", "输入标题、名称或艺术家，字母按键保持正常输入。"), state.query, text => { state.query = text.trim(); state[state.app].view = "library"; state[state.app].tab = 1; if (state.app === "video") state.video.folder = ""; if (state.app === "games") state.games.system = "All"; state.modalStack = []; state.focus = ""; return true; });
}
function playTrack(id) {
  const item = tracks.find(x => x.id === id);
  if (!item) return;
  if (!state.music.queue.includes(id)) state.music.queue = tracks.filter(x => x.albumId === item.albumId).map(x => x.id);
  state.music.track = id; state.music.position = 0; state.music.playing = true;
  navigate("now");
}
function stepTrack(delta) {
  let list = state.music.queue;
  if (!list.length) list = [track().id];
  let index = list.indexOf(track().id) + delta;
  if (state.music.shuffle && list.length > 1) { const choices = list.filter(id => id !== track().id); index = list.indexOf(choices[Math.floor(Math.random() * choices.length)]); }
  if (state.music.repeat) index = (index + list.length) % list.length;
  if (index < 0 || index >= list.length) { notify(T("End of queue", "已到队列末尾")); return; }
  state.music.track = list[index]; state.music.position = 0; render();
}
function chapterStep(delta) {
  const boundaries = [0, 1, 2, 3].map(index => Math.floor(index * video().duration / 4));
  const target = delta > 0 ? boundaries.find(position => position > state.video.position + 1) : boundaries.toReversed().find(position => position < state.video.position - 1);
  if (target != null) state.video.position = target;
  state.video.controls = true; render();
}
function seek(delta) {
  if (state.app === "music") state.music.position = Math.max(0, Math.min(track().seconds, state.music.position + delta));
  else { state.video.position = Math.max(0, Math.min(video().duration, state.video.position + delta)); state.video.controls = true; }
  render();
}
function openVideo(id, start = false) {
  const item = videos.find(x => x.id === id);
  state.video.selected = id;
  const play = position => { state.video.position = position; state.video.playing = true; state.video.controls = true; navigate("playing"); };
  if (item.position && !start) menu(() => T("Continue watching?", "继续观看？"), [
    { label: () => `${T("Resume at", "从")} ${time(item.position)} ${T("", "继续")}`, run: () => play(item.position) },
    { label: () => T("Start from beginning", "从头开始"), run: () => play(0) },
  ], item.title);
  else play(0);
}
function videoTracks() {
  menu(() => T("Playback options", "播放选项"), [
    { label: () => T("Subtitles", "字幕"), subtitle: () => state.video.subtitle === "Off" ? T("Off", "关闭") : state.video.subtitle, child: true, run: () => menu(() => T("Subtitles", "字幕"), ["Off", "English", "简体中文", "English · External SRT"].map(subtitle => ({ label: () => subtitle === "Off" ? T("Off", "关闭") : subtitle, selected: state.video.subtitle === subtitle, run: () => { state.video.subtitle = subtitle; } }))) },
    { label: () => T("Audio track", "音轨"), subtitle: () => state.video.audio, child: true, run: () => menu(() => T("Audio track", "音轨"), ["Original · Stereo", "Commentary · Stereo"].map(audio => ({ label: audio, selected: state.video.audio === audio, run: () => { state.video.audio = audio; } }))) },
    { label: () => T("Chapters", "章节"), child: true, run: () => menu(() => T("Chapters", "章节"), [["01 · Setting out", "01 · 出发"], ["02 · Along the river", "02 · 沿河前行"], ["03 · The open road", "03 · 开阔的公路"], ["04 · On the way home", "04 · 归途"]].map((title, index) => ({ label: () => T(...title), subtitle: time(index * video().duration / 4), run: () => { state.video.position = Math.floor(index * video().duration / 4); } }))) },
    { label: () => T("Playback speed", "播放速度"), subtitle: () => state.video.speed, child: true, run: () => menu(() => T("Playback speed", "播放速度"), ["0.75×", "1×", "1.25×", "1.5×", "2×"].map(speed => ({ label: speed, selected: state.video.speed === speed, run: () => { state.video.speed = speed; } }))) },
    { label: () => T("Hide controls", "隐藏控制栏"), run: () => { state.video.controls = false; } },
  ]);
}
function addressPrompt() {
  textPrompt(() => T("Search or enter address", "搜索或输入网址"), () => T("Use the physical keyboard. Enter opens the address in this tab.", "使用实体键盘，Enter 在当前标签中打开。"), browserTab().url, value => {
    value = value.trim();
    if (!value) return false;
    if (/^(javascript|data|file):/i.test(value)) { notify(T("Enter an http or https address", "请输入 http 或 https 网址")); return false; }
    const url = /^https?:\/\//i.test(value) ? value : /^[^\s]+\.[^\s]+$/.test(value) ? `https://${value}` : `https://search.example/?q=${encodeURIComponent(value)}`;
    openSite(url); return true;
  });
}
function openSite(url) {
  const tab = browserTab();
  if (tab.url !== url) tab.history.push({ url: tab.url, title: tab.title });
  tab.url = url; tab.title = sites.find(x => url.startsWith(x.url))?.title || T("Sample page", "示例网页");
  state.browser.visits = [{ url, title: tab.title }, ...state.browser.visits.filter(x => x.url !== url)].slice(0, 30);
  persist(); state.scenario = "ready"; state.modalStack = [];
  state.browser.mode = "navigation"; state.focus = "article-read"; render();
}
function webBack() {
  const tab = browserTab(), previous = tab.history.pop() || { url: "", title: "" };
  Object.assign(tab, previous); state.browser.mode = "navigation"; state.focus = ""; render();
}
function switchBrowserTab(index) {
  if (!state.browser.tabs[index]) return;
  browserTab().focus = state.focus;
  state.browser.tab = index; state.browser.mode = "navigation";
  state.focus = browserTab().focus || ""; render();
}
function newTab() {
  browserTab().focus = state.focus;
  state.browser.tabs.push({ id: "tab-" + ++tabSequence, title: "", url: "", history: [] });
  switchBrowserTab(state.browser.tabs.length - 1); state.focus = "site-journal"; render();
}
function bookmarkMenu() {
  menu(() => T("Bookmarks", "书签"), state.browser.bookmarks.map(url => ({
    label: sites.find(x => x.url === url)?.title || url, subtitle: url, child: true,
    run: () => menu(() => T("Bookmark actions", "书签操作"), [
      { label: () => T("Open in this tab", "在当前标签打开"), run: () => openSite(url) },
      { label: () => T("Remove bookmark", "移除书签"), run: () => { state.browser.bookmarks = state.browser.bookmarks.filter(x => x !== url); persist(); state.modalStack = []; notify(T("Bookmark removed", "书签已移除")); } }
    ], url)
  })), () => state.browser.bookmarks.length ? T("Choose a page to open or remove.", "选择网页，可以打开或移除。") : T("No bookmarks yet. Use X on a page to add one.", "还没有书签，在网页中按 X 可以收藏。"));
}
function historyMenu() {
  menu(() => T("History", "历史记录"), state.browser.visits.map(item => ({ label: item.title, subtitle: item.url, run: () => openSite(item.url) })), () => T("Pages open in the current tab.", "在当前标签中打开网页。"));
}
function setBrowserMode(mode) {
  state.browser.returnFocus = state.modalStack[0]?.returnFocus || state.focus;
  state.browser.mode = mode; state.modalStack = []; render();
}
function browserModes() {
  menu(() => T("Page interaction", "网页操作模式"), [
    { label: () => T("Navigate links", "链接导航"), subtitle: () => T("Arrows select · A opens · B goes back", "方向键选择 · A 打开 · B 返回"), run: () => setBrowserMode("navigation") },
    { label: () => T("Read the page", "阅读模式"), subtitle: () => T("Larger text · Up / Down scroll", "放大正文 · 上下滚动"), disabled: !browserTab().url, run: () => setBrowserMode("reader") },
    { label: () => T("Virtual pointer", "虚拟指针"), subtitle: () => T("Arrows move · A clicks · B leaves pointer mode", "方向键移动 · A 点击 · B 退出指针模式"), disabled: !browserTab().url, run: () => setBrowserMode("pointer") },
    { label: () => T("Type into the page", "网页内文字输入"), subtitle: () => T("Physical keyboard and input method keep control", "实体键盘与输入法正常使用"), disabled: !browserTab().url, run: () => setBrowserMode("text") },
  ]);
}
function saveReading() { state.reader.positions[book().id] = state.reader.page; persist(); }
function turnPage(delta) { state.reader.page = Math.max(1, Math.min(book().pages, state.reader.page + delta)); saveReading(); render(); }
function readerContents() {
  const en = ["A small departure", "The way north", "A place to begin", "The long afternoon", "What we carry"];
  const zh = ["小小的出发", "向北的路", "开始的地方", "漫长的午后", "我们随身带着什么"];
  menu(() => T("Contents", "目录"), en.map((_, i) => {
    const page = Math.floor(i * book().pages / 5) + 1;
    return { label: () => (i + 1) + " · " + T(en[i], zh[i]), subtitle: () => T("Page ", "第 ") + page + T("", " 页"), run: () => { state.reader.page = page; state.modalStack = []; saveReading(); } };
  }));
}
function readerMatches(query = state.reader.query) {
  if (!query.trim()) return [];
  return Array.from({ length: book().pages }, (_, i) => i + 1).filter(page => readerBlocks(book(), page).join(" ").toLocaleLowerCase().includes(query.toLocaleLowerCase()));
}
function nextReaderMatch(initial = false) {
  const pages = readerMatches();
  if (!pages.length) { notify(T("No matches in this document", "文档中没有找到匹配内容")); return; }
  state.reader.page = pages.find(page => initial ? page >= state.reader.page : page > state.reader.page) || pages[0];
  state.modalStack = []; saveReading(); notify(T("Match on page ", "匹配位于第 ") + state.reader.page + T("", " 页"));
}
function pdfZoomMenu() {
  menu(() => T("PDF zoom", "PDF 缩放"), ["fit", 0.8, 1, 1.25, 1.5, 2].map(zoom => ({
    label: () => zoom === "fit" ? T("Fit width", "适宽") : Math.round(zoom * 100) + "%",
    selected: () => state.reader.pdfZoom === zoom, run: () => { state.reader.pdfZoom = zoom; }
  })));
}
function readerActions() {
  if (state.reader.view !== "reading") { menu(() => T("Reading actions", "阅读操作"), [{ label: () => T("Search documents", "搜索文档"), child: true, run: search }, { label: () => T("Open a folder", "打开文件夹"), child: true, run: chooseSource }]); return; }
  const key = book().id + ":" + state.reader.page, marked = state.reader.bookmarks.includes(key);
  const options = [
    { label: () => T("Contents", "目录"), child: true, run: readerContents },
    { label: () => marked ? T("Remove this bookmark", "移除此页书签") : T("Bookmark this page", "收藏此页"), run: () => { state.reader.bookmarks = marked ? state.reader.bookmarks.filter(x => x !== key) : [...state.reader.bookmarks, key]; persist(); notify(marked ? T("Bookmark removed", "书签已移除") : T("Bookmark saved", "书签已保存")); } },
    { label: () => T("Saved bookmarks", "已保存的书签"), child: true, run: () => menu(() => T("Saved bookmarks", "已保存的书签"), state.reader.bookmarks.filter(x => x.startsWith(book().id + ":")).map(item => ({ label: () => T("Page ", "第 ") + item.split(":")[1] + T("", " 页"), run: () => { state.reader.page = Number(item.split(":")[1]); state.modalStack = []; saveReading(); } })), () => T("Bookmarks keep your place without changing the document. If none are saved, use X to add one.", "书签帮助记住位置，不会更改文档。尚无书签时，可以按 X 收藏当前页。")) },
    { label: () => T("Go to page", "跳转页面"), child: true, run: () => textPrompt(() => T("Go to page", "跳转页面"), "1 – " + book().pages, String(state.reader.page), value => { const page = Number(value); if (!Number.isInteger(page) || page < 1 || page > book().pages) { notify(T("Enter a page within the document", "请输入文档范围内的页码")); return false; } state.reader.page = page; state.modalStack = []; saveReading(); return true; }) },
    { label: () => T("Find in document", "在文档中查找"), child: true, run: () => textPrompt(() => T("Find in document", "在文档中查找"), () => T("Find text, then use X for the next matching page.", "查找文字后，可以按 X 跳到下一个匹配页。"), state.reader.query, value => { state.reader.query = value.trim(); if (!value.trim()) { state.modalStack = []; return true; } if (!readerMatches().length) { notify(T("No matches in this document", "文档中没有找到匹配内容")); return false; } nextReaderMatch(true); return true; }) },
  ];
  if (state.reader.query) options.push(
    { label: () => T("Next matching page", "下一个匹配页"), run: () => nextReaderMatch() },
    { label: () => T("Clear search highlights", "清除搜索高亮"), run: () => { state.reader.query = ""; } }
  );
  if (book().format === "PDF") options.unshift({ label: () => T("PDF zoom", "PDF 缩放"), subtitle: () => state.reader.pdfZoom === "fit" ? T("Fit width", "适宽") : Math.round(state.reader.pdfZoom * 100) + "%", child: true, run: pdfZoomMenu });
  menu(() => T("Reading actions", "阅读操作"), options);
}
function gameLaunch(fresh = false) {
  const item = game();
  if (item.missingCore || item.missingBios) {
    menu(() => T("Before you play", "启动前检查"), [
      { label: () => item.missingCore ? T("Choose an installed emulator", "选择已安装的模拟器") : T("Check firmware folder", "检查固件文件夹"), child: true, run: () => menu(() => T("Setup needed", "需要完成设置"), [{ label: () => T("Return to game details", "返回游戏详情"), run: () => { state.modalStack = []; state.games.view = "detail"; state.focus = "game-launch"; } }], () => item.missingCore ? T("This game needs an emulator core. Install it with your Linux package manager, then scan again.", "此游戏缺少模拟器核心，请通过 Linux 软件包管理器安装后重新扫描。") : T("Required firmware is missing. Add your firmware to SD / BIOS and check again.", "缺少所需固件，请将自己的固件放入 SD / BIOS 后重新检测。")) },
      { label: () => T("Back to library", "返回媒体库"), run: () => { state.games.view = "library"; state.modalStack = []; state.focus = `game-${item.id}`; } },
    ], () => item.missingCore ? T("Emulator core not found. Nothing has been started.", "未找到模拟器核心，尚未启动游戏。") : T("Required firmware is missing. Your save data is safe.", "缺少所需固件，已有存档保持完整。")); return;
  }
  const run = () => { state.games.recent = [item.id, ...state.games.recent.filter(id => id !== item.id)]; persist(); state.games.view = "running"; state.modalStack = []; state.focus = ""; render(); };
  if (fresh && (hasGameSave(item))) confirm(() => T("Start from the beginning?", "从头开始游戏？"), () => T("Your existing manual save states will be kept. The automatic resume point may change after this session.", "保留已有手动存档，本次结束后自动续玩位置可能更新。"), run, () => T("Start fresh", "重新开始"));
  else run();
}
function gameMenu() {
  menu(() => T("Game paused", "游戏已暂停"), [
    { label: () => T("Return to game", "继续游戏"), run: () => {} },
    { label: () => T("Save state", "保存即时存档"), child: true, run: () => saveSlots(false) },
    { label: () => T("Load state", "读取即时存档"), child: true, run: () => saveSlots(true) },
    { label: () => T("Controls", "按键说明"), child: true, run: () => menu(() => T("Controls", "按键说明"), [{ label: () => T("Back", "返回"), run: () => {} }], () => T("A/B/X/Y and L/R belong to the game. Ctrl+Alt+M opens this menu; Ctrl+Alt+Esc returns to uDeck.", "A/B/X/Y 与 L/R 交给游戏。Ctrl+Alt+M 打开此菜单，Ctrl+Alt+Esc 返回 uDeck。")) },
    { label: () => T("Save & return to library", "保存并返回媒体库"), run: () => { state.games.saves[game().id] ||= {}; state.games.saves[game().id].auto = "Today 21:08"; persist(); state.games.view = "library"; state.history.games = []; state.focus = `game-${game().id}`; state.modalStack = []; } },
  ], game().title);
}
function saveSlots(load = false) {
  const saves = state.games.saves[game().id] ||= {};
  menu(() => load ? T("Load state", "读取即时存档") : T("Save states", "即时存档"), [1, 2, 3].map(slot => ({
    label: () => `${T("Slot", "存档槽")} ${slot}`, subtitle: () => saves[slot] || T("Empty", "空"), disabled: load && !saves[slot], keep: true,
    run: () => {
      const save = () => { state.games.saves[game().id] ||= {}; state.games.saves[game().id][slot] = "Today 21:08"; persist(); notify(T(`Saved to slot ${slot}`, `已保存到存档槽 ${slot}`)); };
      if (load) confirm(() => T("Load this save state?", "读取此存档？"), () => T("Current progress since the last save will be replaced.", "将替换上次存档之后的当前进度。"), () => { state.modalStack = []; state.games.view = "running"; notify(T("Save state loaded", "已读取存档")); }, () => T("Load state", "读取存档"));
      else if (saves[slot]) confirm(() => T("Replace this save state?", "覆盖此即时存档？"), () => T("Other slots and the automatic resume point will be kept.", "保留其他存档槽与自动续玩位置。"), save, () => T("Replace", "覆盖"));
      else save();
    },
  })), load ? () => T("Only occupied slots can be loaded.", "只能读取已有存档的槽位。") : () => T("Manual saves are separate from the automatic resume point.", "手动存档与自动续玩位置分别保存。"));
}
function dispatch(action) {
  if (state.app === "games" && state.games.view === "running" && !state.modalStack.length && action !== "game-menu") return;
  if (["up", "down", "left", "right"].includes(action)) { move(action); return; }
  if (action === "back") { back(); return; }
  if (action === "accept") {
    if (state.modalStack.at(-1)?.type === "text") { const action = document.activeElement?.dataset.action; action ? actionRun(action) : textSubmit(); return; }
    if (state.modalStack.length) { choose(state.modalStack.at(-1).index); return; }
    if (state.app === "reader" && state.reader.view === "reading") { readerContents(); return; }
    if (state.app === "video" && state.video.view === "playing" && !state.video.controls) { state.video.controls = true; state.focus = "video-toggle"; render(); return; }
    if (state.app === "browser" && state.browser.mode === "pointer") {
      const page = root.querySelector(".web-page"), bounds = page.getBoundingClientRect();
      const element = document.elementFromPoint(bounds.left + state.browser.pointer.x, bounds.top + state.browser.pointer.y)?.closest("[data-action]");
      if (element) actionRun(element.dataset.action);
      return;
    }
    const target = focusable().find(x => x.dataset.nav === state.focus); if (target) actionRun(target.dataset.action); return;
  }
  if (action === "context") { context(); return; }
  if (action === "settings") { if (!state.modalStack.length) settings(); return; }
  if (action === "game-menu") { if (!state.modalStack.length) gameMenu(); return; }
  if (action === "previous" || action === "next") {
    if (state.modalStack.length) return;
    const delta = action === "previous" ? -1 : 1;
    if (state.app === "reader" && state.reader.view === "reading") turnPage(delta);
    else if (state.app === "music" && state.music.view === "now") stepTrack(delta);
    else if (state.app === "video" && state.video.view === "playing") chapterStep(delta);
    else if (state.app === "browser") switchBrowserTab(state.browser.tab + delta);
    else if (state.app === "games" && state.games.view === "detail") { const next = games.indexOf(game()) + delta; if (games[next]) { state.games.selected = games[next].id; state.focus = "game-launch"; render(); } }
    else switchTab(state[state.app].tab + delta);
  }
}
function actionRun(value) {
  const [action, ...args] = value.split(":"), id = args.join(":");
  if (action === "dispatch") { dispatch(id); return; }
  if (action === "modal") { choose(Number(id)); return; }
  if (action === "text-submit") { textSubmit(); return; }
  if (action === "apps") { appMenu(); return; }
  if (action === "tab") { switchTab(Number(id)); return; }
  if (action === "album") { navigate("album", { album: id }); return; }
  if (action === "play-album") { state.music.queue = tracks.filter(x => x.albumId === id).map(x => x.id); playTrack(state.music.queue[0]); return; }
  if (action === "play-track") { playTrack(id); return; }
  if (action === "now") { navigate("now"); return; }
  if (action === "queue") { navigate("library", { tab: 2 }); state.focus = `track-${track().id}`; render(); return; }
  if (action === "music-toggle") { state.music.playing = !state.music.playing; render(); return; }
  if (action === "track-step") { stepTrack(Number(id)); return; }
  if (action === "video") { openVideo(id); return; }
  if (action === "video-toggle") { state.video.playing = !state.video.playing; render(); return; }
  if (action === "video-tracks") { videoTracks(); return; }
  if (action === "seek") { seek(Number(id)); return; }
  if (action === "video-folder") { state.query = ""; navigate("library", { tab: 1, folder: id }); return; }
  if (action === "address") { addressPrompt(); return; }
  if (action === "site") { openSite(sites.find(x => x.id === id).url); return; }
  if (action === "web-next") { openSite("https://journal.example/field-notes"); return; }
  if (action === "reader-mode") { setBrowserMode("reader"); return; }
  if (action === "web-back") { webBack(); return; }
  if (action === "bookmarks") { bookmarkMenu(); return; }
  if (action === "new-tab") { newTab(); return; }
  if (action === "browser-tab") { switchBrowserTab(Number(id)); return; }
  if (action === "visit") { openSite(state.browser.visits[Number(id)].url); return; }
  if (action === "clear-search") { state.query = ""; const item = state[state.app]; item.tab = 1; item.system = "All"; state.focus = ""; render(); return; }
  if (action === "browser-home") { state.scenario = "ready"; webBack(); return; }
  if (action === "book") { const item = books.find(x => x.id === id); state.reader.query = ""; state.reader.page = state.reader.positions[id] || item.page; navigate("reading", { selected: id }); return; }
  if (action === "game") { navigate("detail", { selected: id }); return; }
  if (action === "system") { state.games.system = id; state.focus = `system-${id}`; render(); return; }
  if (action === "game-launch" || action === "game-new") { gameLaunch(action === "game-new"); return; }
  if (action === "choose-source") { chooseSource(); return; }
  if (action === "retry" || action === "scan-cancel") { state.scenario = "ready"; state.focus = ""; render(); return; }
}
root.addEventListener("click", event => {
  const element = event.target.closest("[data-action]");
  if (!element || element.disabled || state.modalStack.length && !element.closest(".modal")) return;
  if (element.dataset.nav) state.focus = element.dataset.nav;
  actionRun(element.dataset.action);
});
root.addEventListener("focusin", event => {
  if (!event.target.dataset.nav || event.target.disabled) return;
  if (state.focus !== event.target.dataset.nav) focus(event.target.dataset.nav, false);
});
root.addEventListener("input", event => {
  if (event.target.hasAttribute("data-modal-input")) state.modalStack.at(-1).text = event.target.value;
  if (event.target.hasAttribute("data-inline-input")) state.query = event.target.value;
});
document.addEventListener("keydown", event => {
  if (!document.querySelector("#review-help").hidden) { if (event.key === "Escape") { document.querySelector("#review-help").hidden = true; focus(state.focus); } return; }
  if (event.target.closest(".studio")) return;
  if (event.isComposing || event.keyCode === 229) return;
  if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "m" && state.app === "games" && state.games.view === "running") { event.preventDefault(); dispatch("game-menu"); return; }
  if (state.app === "games" && state.games.view === "running" && !state.modalStack.length) return;
  if (event.key === "Tab") {
    const owner = root.querySelector(".modal") || root;
    const options = state.modalStack.at(-1)?.type === "text" ? [...owner.querySelectorAll("input, [data-nav]:not(:disabled)")] : focusable();
    if (options.length) { event.preventDefault(); const i = options.indexOf(document.activeElement); const next = options[(i + (event.shiftKey ? -1 : 1) + options.length) % options.length]; next.focus(); }
    return;
  }
  if (event.key === "F1") { event.preventDefault(); appMenu(); return; }
  if (event.key === "F6") { event.preventDefault(); setLanguage(state.language === "en" ? "zh_CN" : "en"); return; }
  if (state.app === "games" && state.games.view === "running" && !state.modalStack.length) return;
  if (!state.modalStack.length && event.ctrlKey && event.key.toLowerCase() === "l" && state.app === "browser") { event.preventDefault(); addressPrompt(); return; }
  if (event.target.hasAttribute("data-inline-input") && event.key === "Enter") { event.preventDefault(); state.browser.mode = "navigation"; state.focus = state.browser.returnFocus || "article-read"; render(); return; }
  if (event.target.matches("input") && !["Escape", "Enter"].includes(event.key)) return;
  const mapped = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "accept", Escape: "back", F2: "context", F3: "settings", PageUp: "previous", PageDown: "next" }[event.key];
  if (mapped) { event.preventDefault(); if (!event.repeat || ["up", "down", "left", "right"].includes(mapped)) dispatch(mapped); }
});
document.querySelector("#application").addEventListener("change", event => switchApp(event.target.value));
document.querySelector("#language").addEventListener("change", event => setLanguage(event.target.value));
document.querySelector("#scenario").addEventListener("change", event => setScenario(event.target.value));
document.querySelector("#help-toggle").addEventListener("click", () => { document.querySelector("#review-help").hidden = false; document.querySelector("#help-close").focus(); });
document.querySelector("#help-close").addEventListener("click", () => { document.querySelector("#review-help").hidden = true; focus(state.focus); });
if (params.get("capture") === "1") document.body.classList.add("capture");

// Deliberately separate review/QA API. These controls never appear in the product viewport.
window.udeckStudy = { state, dispatch, action: actionRun, switchApp, setLanguage, setScenario, render, focus, context, settings, back, snapshot: () => JSON.parse(JSON.stringify(state)) };
if (state.scenario === "ready") render(); else setScenario(state.scenario);
setInterval(() => {
  if (state.scenario !== "ready") return;
  if (state.music.playing) {
    state.music.position = Math.min(track().seconds, state.music.position + 1);
    if (state.music.position >= track().seconds) {
      const more = state.music.queue.indexOf(track().id) < state.music.queue.length - 1;
      if (more || state.music.repeat || state.music.shuffle) stepTrack(1);
      else { state.music.playing = false; render(); }
    }
  }
  if (state.video.playing) {
    state.video.position = Math.min(video().duration, state.video.position + parseFloat(state.video.speed));
    if (state.video.position >= video().duration) { state.video.playing = false; state.video.controls = true; render(); }
  }
  for (const name of ["music", "video"]) {
    root.querySelectorAll(`[data-position="${name}"]`).forEach(element => { element.textContent = time(state[name].position); });
    root.querySelectorAll(`[data-progress="${name}"]`).forEach(element => { element.style.width = `${state[name].position / (name === "music" ? track().seconds : video().duration) * 100}%`; });
  }
}, 1000);
