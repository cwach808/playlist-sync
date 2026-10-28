// playlist-sync Amazon Music exporter (runs as a bookmarklet on music.amazon.com).
//
// Reads the playlist you're looking at and downloads it as a CSV. It only reads what
// the page shows you: no logins, no hidden APIs, nothing sent anywhere.
//
// Amazon renders only the ~10 rows near the screen ("virtualized" list) and uses
// auto-generated CSS class names, so we find rows by content instead: every track row
// has /artists/ links and a duration like "03:47". (The album column is hidden in
// narrower windows, so it's optional.)
(() => {
  // Clicking again always starts fresh (e.g. after moving to another playlist).
  if (window.__plsyncExporter) window.__plsyncExporter.close();

  const DURATION = /^\d{1,2}:\d{2}(:\d{2})?$/;
  let tracks = new Map();  // key -> {order, title, artists, album, duration}
  let firstSeen = 0;
  // Amazon is a single-page app: going to another playlist doesn't reload the page,
  // so we notice the URL change and start over instead of mixing playlists together.
  let page = location.pathname;

  // ---- reading rows -------------------------------------------------------

  const linesOf = el => el.innerText.split('\n').map(s => s.trim()).filter(Boolean);

  // A row is the smallest element around an artist link that includes a duration.
  function rowFor(artistLink) {
    for (let n = artistLink; n && n !== document.body; n = n.parentElement) {
      if (linesOf(n).some(l => DURATION.test(l))) return n;
    }
    return null;
  }

  function parseRow(row) {
    const lines = linesOf(row);
    // The last-played song shows a "resume" icon instead of its number.
    const num = /^\d+$/.test(lines[0]) ? Number(lines[0]) : null;
    const rest = num === null ? lines : lines.slice(1);
    const albumLink = row.querySelector('a[href*="/albums/"]');
    let artists = [...row.querySelectorAll('a[href*="/artists/"]')]
      .map(a => a.innerText.trim()).filter(Boolean);
    artists = [...new Set(artists)];
    if (!artists.length && rest[1]) artists = [rest[1]];
    return {
      num,
      title: rest[0] || '',
      artists,
      album: albumLink ? albumLink.innerText.trim() : '',
      duration: lines.filter(l => DURATION.test(l)).pop() || '',
    };
  }

  // The "now playing" bar also has artist links; it's pinned to the screen.
  function inPinnedBar(el) {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (getComputedStyle(n).position === 'fixed') return true;
    }
    return false;
  }

  function rows() {
    const out = [];
    for (const link of document.querySelectorAll('a[href*="/artists/"]')) {
      if (inPinnedBar(link)) continue;
      const row = rowFor(link);
      if (row && !out.includes(row)) out.push(row);  // multi-artist rows have several links
    }
    return out;
  }

  function collect() {
    if (location.pathname !== page) {
      page = location.pathname;
      tracks = new Map();
      firstSeen = 0;
      restart();
    }
    const total = expectedTotal();
    const parsed = rows().map(parseRow).filter(t => t.title);
    const numbered = parsed.some(t => t.num !== null);
    let added = 0;
    parsed.forEach((t, i) => {
      if (t.num === null && numbered) {
        // Only the playlist's own last-played song lacks a number (it shows a "resume"
        // icon). Accept an un-numbered row only if it fills a gap in the numbering;
        // anything else is e.g. a "recommended songs" row, not part of the playlist.
        const prev = parsed.slice(0, i).reverse().find(x => x.num !== null);
        const next = parsed.slice(i + 1).find(x => x.num !== null);
        const slot = prev ? prev.num + 1 : next ? next.num - 1 : null;
        const fits = slot >= 1 && (!next || next.num === slot + 1) &&
          (!prev || prev.num === slot - 1) && (!total || slot <= total);
        if (!fits) return;
        t.num = slot;
      }
      if (t.num !== null && total && t.num > total) return;
      const key = t.num !== null ? `#${t.num}` : `${t.title}|${t.artists.join(';')}`;
      if (tracks.has(key)) return;
      t.order = t.num !== null ? t.num : 100000 + firstSeen++;
      tracks.set(key, t);
      added++;
    });
    return added;
  }

  function expectedTotal() {
    const m = document.body.innerText.match(/(\d[\d,]*)\s+SONGS?\b/i);
    return m ? Number(m[1].replace(/,/g, '')) : null;
  }

  function playlistName() {
    const h = document.querySelector('h1, [role="heading"]');
    return (h && h.innerText.trim()) || 'Amazon Music playlist';
  }

  // ---- CSV ----------------------------------------------------------------

  function toCsv() {
    const esc = v => `"${String(v).replace(/"/g, '""')}"`;
    const sorted = [...tracks.values()].sort((a, b) => a.order - b.order);
    const lines = ['Title,Artist,Album,Duration'];
    for (const t of sorted) {
      lines.push([t.title, t.artists.join('; '), t.album, t.duration].map(esc).join(','));
    }
    return lines.join('\n') + '\n';
  }

  function download() {
    const blob = new Blob([toCsv()], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = playlistName().replace(/[\\/:*?"<>|]+/g, '-').trim() + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  // ---- on-page panel ------------------------------------------------------

  const panel = document.createElement('div');
  panel.style.cssText = [
    'position:fixed', 'top:16px', 'right:16px', 'z-index:2147483647', 'width:300px',
    'padding:14px 16px', 'border-radius:12px', 'background:#111', 'color:#fff',
    'font:14px/1.4 -apple-system,system-ui,sans-serif', 'box-shadow:0 6px 24px rgba(0,0,0,.5)',
  ].join(';');
  const heading = document.createElement('div');
  heading.style.cssText = 'font-weight:600;margin-bottom:6px';
  heading.textContent = 'playlist-sync exporter';
  const status = document.createElement('div');
  const buttons = document.createElement('div');
  buttons.style.cssText = 'display:flex;gap:8px;margin-top:10px';
  const button = (label, onClick, primary) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'flex:1;padding:6px 10px;border-radius:999px;cursor:pointer;border:0;' +
      (primary ? 'background:#1ed760;color:#000;font-weight:600' : 'background:#333;color:#fff');
    b.onclick = onClick;
    return b;
  };
  const downloadBtn = button('Download CSV', download, true);
  buttons.append(downloadBtn, button('Close', close, false));
  panel.append(heading, status, buttons);
  document.body.appendChild(panel);

  function render(note) {
    const total = expectedTotal();
    status.textContent = `${playlistName()}: collected ${tracks.size}` +
      (total ? ` of ${total}` : '') + ' songs.' + (note ? ' ' + note : '');
    downloadBtn.disabled = tracks.size === 0;
  }

  // ---- scrolling ----------------------------------------------------------

  const observer = new MutationObserver(() => { if (collect()) render(); });
  observer.observe(document.body, { childList: true, subtree: true });

  let stale = 0;
  let timer = null;
  function tick() {
    const total = expectedTotal();
    const progressed = collect() > 0;
    stale = progressed ? 0 : stale + 1;
    if (total && tracks.size >= total) {
      stop('Done! Click Download CSV.');
    } else if (stale >= 12) {
      stop(total
        ? 'Stopped early: scroll to the bottom yourself (songs are still collected), ' +
          'then click Download CSV.'
        : 'Reached the end. Click Download CSV.');
    } else {
      const rs = rows();
      if (rs.length) rs[rs.length - 1].scrollIntoView({ block: 'end' });
      render('Scrolling...');
    }
  }
  function restart() {
    clearInterval(timer);
    stale = 0;
    timer = setInterval(tick, 600);
  }
  restart();

  function stop(note) { clearInterval(timer); render(note); }

  function close() {
    clearInterval(timer);
    observer.disconnect();
    panel.remove();
    delete window.__plsyncExporter;
  }

  window.__plsyncExporter = { close };
  collect();
  render('Scrolling...');
})();
