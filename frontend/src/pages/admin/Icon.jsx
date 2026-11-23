const PATHS = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  users: "M16 20v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM21 20v-1a4 4 0 00-3-3.9M16 4.2a3.5 3.5 0 010 6.6",
  card: "M3 6h18v12H3zM3 10h18M7 15h3",
  video: "M12 21a9 9 0 100-18 9 9 0 000 18zM10 8.5v7l6-3.5z",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  chat: "M21 12a8 8 0 01-11.6 7.1L4 20l1.1-4.4A8 8 0 1121 12z",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM4.6 9a1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1 1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1A1.7 1.7 0 004.6 9z",
  help: "M4 14v-2a8 8 0 0116 0v2M4 14a2 2 0 012-2h1v5H6a2 2 0 01-2-2zM20 14a2 2 0 00-2-2h-1v5h1a2 2 0 002-2zM17 19a4 4 0 01-4 2h-1",
  logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  plus: "M12 5v14M5 12h14",
  arrow: "M5 12h14M13 6l6 6-6 6",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a3.5 3.5 0 100-7 3.5 3.5 0 000 7z",
  chart: "M5 20V10M12 20V4M19 20v-7",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
  menu: "M4 6h16M4 12h16M4 18h16",
};

export default function Icon({ name, size = 20 }) {
  return <svg className="ad-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]} /></svg>;
}
