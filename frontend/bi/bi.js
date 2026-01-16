async function loadPowerBi() {
  const frame = document.getElementById('biFrame');
  const missing = document.getElementById('biMissing');

  if (!frame || !missing) return;

  function showMissing() {
    missing.classList.remove('d-none');
    frame.removeAttribute('src');
  }

  try {
    const res = await fetch('/api/config/powerbi');
    if (!res.ok) return showMissing();
    const cfg = await res.json();
    const url = cfg && cfg.embed_url ? String(cfg.embed_url).trim() : '';

    if (!url) return showMissing();
    if (!/^https?:\/\//i.test(url)) return showMissing();

    missing.classList.add('d-none');
    frame.src = url;
  } catch {
    showMissing();
  }
}

loadPowerBi();
