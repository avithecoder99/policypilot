const qEl = document.getElementById('question');
const askBtn = document.getElementById('askBtn');
const answerEl = document.getElementById('answer');
const sourcesEl = document.getElementById('sources');
const loadingEl = document.getElementById('loading');

async function ask() {
  const question = (qEl.value || '').trim();
  if (!question) return;
  answerEl.textContent = '';
  
  loadingEl.classList.remove('hidden');
  askBtn.disabled = true;

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || ('HTTP ' + r.status));
    }
    const data = await r.json();
    answerEl.textContent = data.answer;

    // Render sources
    if (data.sources && data.sources.length) {
      const list = data.sources.map(s => `• Page ${s.page}: ${s.snippet}`).join('\n');
      sourcesEl.textContent = 'Sources:\n' + list;
    } else {
      sourcesEl.textContent = '';
    }
  } catch (err) {
    answerEl.textContent = 'Error: ' + err.message + '\nCheck server logs and your OpenAI key.';
  } finally {
    loadingEl.classList.add('hidden');
    askBtn.disabled = false;
  }
}

askBtn.addEventListener('click', ask);
qEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') ask();
});
