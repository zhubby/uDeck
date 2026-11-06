// Original fixture content. Titles and filenames stay literal in either UI language.
export const albums = [
  { id: "after-hours", title: "After Hours", artist: "Mira Vale", year: 2025, tracks: ["Window Seat", "Last Light", "After Hours", "A Little Further", "Back to You", "Night Ferry"], length: "26 min" },
  { id: "still-water", title: "Still Water", artist: "North Window", year: 2024, tracks: ["Low Tide", "Still Water", "Out of the Blue", "On the Shore", "Driftwood"], length: "31 min" },
  { id: "slow-orbit", title: "Slow Orbit", artist: "June Radio", year: 2026, tracks: ["Slow Orbit", "Signals", "Halfway There", "Gravity", "Come Around"], length: "24 min" },
  { id: "field-notes", title: "Field Notes", artist: "A. Mori", year: 2023, tracks: ["Walking North", "Field Notes", "Moss", "Two Pines", "An Open Window"], length: "37 min" },
  { id: "blue-hour", title: "Blue Hour", artist: "Mira Vale", year: 2024, tracks: ["Blue Hour", "Quiet Street", "Distant Lights", "Home Again"], length: "22 min" },
  { id: "home-tapes", title: "Home Tapes", artist: "Side B", year: 2025, tracks: ["Side A", "The Kitchen", "Sunday", "Side B"], length: "18 min" },
  { id: "daybreak", title: "Daybreak", artist: "Soft Signal", year: 2026, tracks: ["Daybreak", "First Train", "Empty Platform", "Morning Sun"], length: "28 min" },
  { id: "long-way", title: "The Long Way Home — Live at North Pier", artist: "North Window", year: 2025, tracks: ["The Long Way Home", "North Pier", "One Last Song"], length: "42 min" },
];
export const tracks = albums.flatMap(album => album.tracks.map((title, index) => ({
  id: `${album.id}-${index}`, albumId: album.id, title, artist: album.artist,
  album: album.title, number: index + 1, seconds: 218 + index * 27,
})));
export const videos = [
  { id: "open-road", title: "The Open Road", subtitle: "A film by North Window", duration: 4240, position: 1148, detail: "1080p · H.264 · 24 fps", folder: "Films" },
  { id: "quiet-coast", title: "A Quiet Coast", subtitle: "Field studies / Episode 03", duration: 1810, position: 496, detail: "720p · H.264 · 25 fps", folder: "Series" },
  { id: "night-train", title: "Night Train to Somewhere", subtitle: "Travel journal", duration: 3240, position: 0, detail: "1080p · H.265 · 24 fps", folder: "Films" },
  { id: "mountain-light", title: "Mountain Light", subtitle: "Field studies / Episode 04", duration: 1980, position: 0, detail: "720p · VP9 · 30 fps", folder: "Series" },
  { id: "making-room", title: "Making Room for Small Things", subtitle: "Workshop / Part 01", duration: 1460, position: 0, detail: "1080p · H.264 · 30 fps", folder: "Workshop" },
  { id: "city-rhythm", title: "City Rhythm", subtitle: "A short film", duration: 770, position: 0, detail: "720p · H.264 · 24 fps", folder: "Films" },
];
export const books = [
  { id: "small-journeys", title: "Small Journeys", author: "Nora Fields", format: "EPUB", page: 42, pages: 186, chapter: "03 · A place to begin" },
  { id: "wayland-notes", title: "Wayland Notes", author: "uDeck Field Editions", format: "PDF", page: 8, pages: 32, chapter: "02 · Windows and input" },
  { id: "garden-time", title: "Garden Time", author: "A. Mori", format: "EPUB", page: 18, pages: 124, chapter: "02 · Taking the time" },
  { id: "keyboard-guide", title: "掌机随行手册 · Pocket Computer", author: "uDeck Field Editions", format: "TXT", page: 1, pages: 24, chapter: "01 · 从这里开始" },
];
export const readingPages = [
  ["A place to begin", "The path was never meant to be the shortest way home. It followed the edge of the river, turned beneath the old bridge, and carried on wherever the trees left room.", "I brought a notebook, a little radio, and the kind of map that still has blank spaces. There was no particular destination. The morning was enough.", "A small journey asks you to notice what a faster one would leave behind: the colour of a door, the sound of water, a light in a window. There is always somewhere to begin."],
  ["The long afternoon", "By the afternoon the road had grown quiet. The houses stood a little further apart, and the river had become a narrow line of light between the fields.", "At the station a wooden bench faced the tracks. Someone had left a book open on it. I sat down beside the book and watched the sun move across the opposite wall.", "Nothing needed to happen next. For once, that felt like a useful thing to learn."],
  ["What we carry", "The best things in the bag were the things I had nearly left at home. A pencil. A spare pair of socks. A photograph folded at the corners.", "We make room for objects, but a journey is mostly made of spaces: the space between two towns, between one conversation and another, between a question and its answer.", "On the way back I took the same path. It was different in the evening."],
];
export const games = [
  { id: "pocket-orchard", title: "Pocket Orchard", system: "GB", year: "2025", genre: "Life simulation", description: ["A little farm, a wide world. Grow your orchard and get to know the people of Willow Village.", "一座小农场，一片新天地。照料果园，与柳树村的居民相识。"], time: "3 h 24 min", core: "Gambatte", saved: true },
  { id: "orbital", title: "Orbital Courier", system: "GBA", year: "2024", genre: "Adventure", description: ["Deliver a little hope to the far side of the solar system.", "向太阳系的远方送去一点希望。"], time: "42 min", core: "mGBA", saved: false },
  { id: "tiny-valley", title: "Tiny Valley", system: "SNES", year: "2025", genre: "Adventure", description: ["Find your own path through a valley full of small surprises.", "在充满惊喜的山谷中，找到自己的道路。"], time: "1 h 12 min", core: "Snes9x", saved: false },
  { id: "startrail", title: "Star Trail", system: "PS1", year: "2023", genre: "Role-playing", description: ["A journey between the stars, told one station at a time.", "一站又一站，踏上星际旅途。"], time: "6 h 08 min", core: "PCSX ReARMed", saved: true, missingBios: true },
  { id: "rally-day", title: "Rally Day", system: "GBA", year: "2024", genre: "Racing", description: ["A weekend on the road. Every corner tells a different story.", "公路上的周末，每个弯道都有新故事。"], time: "28 min", core: "mGBA", saved: false },
  { id: "harbor", title: "Harbor Light", system: "GB", year: "2026", genre: "Puzzle", description: ["Keep the light on. Guide the boats home.", "点亮灯塔，引领小船归航。"], time: "12 min", core: "Gambatte", saved: false },
  { id: "meadow", title: "Meadow Quest", system: "SNES", year: "2024", genre: "Adventure", description: ["A pocket-sized adventure across the meadow.", "穿越草甸的随身小冒险。"], time: "54 min", core: "Snes9x", saved: false },
  { id: "moon-base", title: "Moon Base", system: "PS1", year: "2025", genre: "Strategy", description: ["Build a place to call home, a little further from Earth.", "远离地球，建造一个可以称为家的地方。"], time: "2 h 16 min", core: "PCSX ReARMed", saved: false, missingCore: true },
];
export const sites = [
  { id: "journal", title: "Pocket Journal", host: "journal.example", letter: "P", url: "https://journal.example/" },
  { id: "wiki", title: "Field Wiki", host: "wiki.example", letter: "W", url: "https://wiki.example/" },
  { id: "manual", title: "uDeck Handbook", host: "handbook.example", letter: "u", url: "https://handbook.example/" },
  { id: "radio", title: "Local Radio", host: "radio.example", letter: "R", url: "https://radio.example/" },
];
