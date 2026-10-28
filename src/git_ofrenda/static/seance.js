(() => {
  const dataEl = document.getElementById('seance-data');
  if (!dataEl) return;
  const history = JSON.parse(dataEl.textContent || '{}');
  const HEADERS = {'Content-Type': 'application/json', 'X-Ofrenda': '1'};

  document.querySelectorAll('.card').forEach(card => {
    const path = card.dataset.path;
    const btn = card.querySelector('.summon');
    if (!btn) return;
    const box = card.querySelector('.chat');
    const log = card.querySelector('.log');
    const input = card.querySelector('input');
    const forget = card.querySelector('.forget');
    let busy = false;

    function add(who, text) {
      const d = document.createElement('div');
      d.className = 'msg ' + who;
      d.textContent = text;
      log.appendChild(d);
      log.scrollTop = log.scrollHeight;
      return d;
    }

    const past = history[path] || [];
    past.forEach(m => add(m.role === 'user' ? 'you' : 'ghost', m.content));
    if (past.length) btn.textContent = btn.textContent.replace('Hold', 'Continue');

    async function ask() {
      const msg = input.value.trim();
      if (!msg || busy) return;
      busy = true; input.value = '';
      add('you', msg);
      const bubble = add('ghost', '');
      try {
        const r = await fetch('/api/chat', {method: 'POST', headers: HEADERS, body: JSON.stringify({path, message: msg})});
        if (!r.ok || !r.body) throw new Error('HTTP ' + r.status);
        const reader = r.body.getReader(), dec = new TextDecoder();
        let buf = '';
        for (;;) {
          const {value, done} = await reader.read();
          if (done) break;
          buf += dec.decode(value, {stream: true});
          let i;
          while ((i = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, i).trim();
            buf = buf.slice(i + 1);
            if (!line) continue;
            const ev = JSON.parse(line);
            if (ev.token) { bubble.textContent += ev.token; log.scrollTop = log.scrollHeight; }
            if (ev.done && ev.voice === 'template') {
              bubble.classList.add('tpl');
              bubble.title = 'Answered from git facts (no model)';
            }
          }
        }
      } catch (e) {
        bubble.textContent = bubble.textContent || 'The spirits are silent. Is the server still running?';
      }
      busy = false;
    }

    btn.onclick = () => { box.hidden = !box.hidden; if (!box.hidden) input.focus(); };
    card.querySelector('.send').onclick = ask;
    input.onkeydown = e => { if (e.key === 'Enter') ask(); };
    forget.onclick = async () => {
      await fetch('/api/reset', {method: 'POST', headers: HEADERS, body: JSON.stringify({path})});
      log.textContent = '';
    };
  });
})();
