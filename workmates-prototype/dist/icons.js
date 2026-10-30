const paths = {
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 4.5 4.5"/>',
  collapse: '<rect x="3" y="3.5" width="18" height="17" rx="3"/><path d="M9 4v16"/>',
  home: '<path d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
  edit: '<path d="M13 4H6a3 3 0 0 0-3 3v11a3 3 0 0 0 3 3h11a3 3 0 0 0 3-3v-7"/><path d="m9 15 1-4L18 3a2.1 2.1 0 0 1 3 3l-8 8zM16 5l3 3"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
  folder: '<path d="M3 8V6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8h18"/>',
  library: '<path d="M4 4v16M8 4v16M12 4v16M16 4l5 15M3 4h2M3 20h2M7 4h2M7 20h2M11 4h2M11 20h2M15 4l2-.5M20 19l2-.5"/>',
  hub: '<path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10M7.5 4.5l9 5"/>',
  settings: '<path d="M3 6h10m4 0h4M3 12h3m4 0h11M3 18h10m4 0h4"/><circle cx="15" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .5c0 1.5-2.5 1.5-2.5 3.5M12 16.5v.1"/>',
  bell: '<path d="M6 9a6 6 0 0 1 12 0v5l2 3H4l2-3zM10 21h4M12 2v1"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  more: '<circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  chat: '<path d="M21 11.5a8.6 8.6 0 0 1-8.8 8.5 12 12 0 0 1-2.9-.4L4 22l.9-5.2a8 8 0 0 1-1.7-5.3A8.6 8.6 0 0 1 12 3a8.6 8.6 0 0 1 9 8.5Z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5zM4 12l8 5 8-5M4 17l8 5 8-5"/>',
  users: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 13a5 5 0 0 1 3 5v3"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  refresh: '<path d="M20 9a8 8 0 1 0 0 6M20 3v6h-6"/>',
  filter: '<path d="M3 4h18l-7 8v6l-4 3v-9z"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
  file: '<path d="M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9zM14 2v7h7M7 13h10M7 17h7"/>',
  book: '<path d="M12 5v16M12 5C9 2 5 2 2 3v16c3-1 7-1 10 2 3-3 7-3 10-2V3c-3-1-7-1-10 2z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  code: '<path d="m7 6-5 6 5 6M17 6l5 6-5 6M14 3l-4 18"/>',
  play: '<path d="m7 3 14 9-14 9z"/>',
  pause: '<path d="M8 4v16M16 4v16"/>',
  external: '<path d="M14 3h7v7M21 3l-11 11M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/>',
  send: '<path d="m22 2-7 20-4-9-9-4zM22 2 11 13"/>',
  star: '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1z"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  attach: '<path d="m9 12 7-7a3.5 3.5 0 0 1 5 5L10 21a5 5 0 0 1-7-7L14 3M6 15l9-9"/>',
  mic: '<rect x="8" y="2" width="8" height="13" rx="4"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 6h14M5 18h14"/>',
  terminal: '<rect x="2" y="3" width="20" height="18" rx="3"/><path d="m6 8 4 4-4 4M13 16h5"/>',
  logout: '<path d="M10 3H4v18h6M9 12h13m-5-5 5 5-5 5"/>',
  moon: '<path d="M20.5 14A9 9 0 0 1 10 3a9 9 0 1 0 10.5 11z"/>',
  keyboard: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M6 15h12"/>',
  sort: '<path d="M8 3v18m-4-4 4 4 4-4M16 21V3m-4 4 4-4 4 4"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  checkcircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  arrowleft: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  robot: '<rect x="5" y="7" width="14" height="13" rx="4"/><path d="M12 3v4M9 12v2M15 12v2M9 17h6M2 11v5M22 11v5"/><circle cx="12" cy="2" r="1"/>',
  expand: '<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/>'
};

export function icon(name, size = 18) {
  return `<svg class="icon icon-${name}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
}

export function avatar(index = 0, size = 36) {
  return `<img class="avatar" src="./assets/avatar-${((Number(index) || 0) % 6 + 6) % 6}.svg" width="${size}" height="${size}" alt="" style="width:${size}px;height:${size}px;flex-shrink:0;border-radius:50%;object-fit:cover" />`;
}

export function logo() {
  return `<svg class="brand-logo" width="30" height="30" viewBox="0 0 40 40" fill="none" aria-hidden="true"><defs><linearGradient id="brandA" x1="8" y1="4" x2="31" y2="37" gradientUnits="userSpaceOnUse"><stop stop-color="#a6d7ff"/><stop offset=".5" stop-color="#638bff"/><stop offset="1" stop-color="#4d48f8"/></linearGradient><linearGradient id="brandB" x1="13" y1="3" x2="24" y2="34" gradientUnits="userSpaceOnUse"><stop stop-color="#eef6ff"/><stop offset="1" stop-color="#66b5ff"/></linearGradient></defs><path d="m20 1 12 6 7 12-6 13-13 7-12-6L1 20 7 7z" fill="url(#brandA)" opacity=".5"/><path d="m20 2 12 5-7 10-10-3z" fill="#7ca7ff"/><path d="m32 7 7 12-12 3-2-5z" fill="#4d82f7"/><path d="m39 19-6 13-11-6 5-4z" fill="#4467ee"/><path d="m33 32-13 7-3-12 5-1z" fill="#5d5ded"/><path d="m20 39-12-6 7-10 2 4z" fill="#8393ff"/><path d="M8 33 1 20l12-3 2 6z" fill="#a1caff"/><path d="M1 20 7 7l10 7-4 3z" fill="url(#brandB)"/><path d="M7 7 20 1l-3 13z" fill="#d2eaff"/><path d="m17 14 8 3 2 5-5 4-7-3-2-6z" fill="#e3efff"/><path d="m17 14 8 3-5 4-7-4z" fill="#f4f8ff"/><path d="m20 21 7 1-5 4-7-3z" fill="#83b1ff"/></svg>`;
}
