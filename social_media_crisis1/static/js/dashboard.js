// Loads chart data from /api/data and draws Chart.js charts (works on dashboard + analytics)
const C = {}, col = {Positive: '#198754', Neutral: '#6c757d', Negative: '#dc3545'}, SENT = ['Positive', 'Neutral', 'Negative'];
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function draw(id, type, data, opts) {
  const el = $(id); if (!el) return;
  if (C[id]) C[id].destroy();
  C[id] = new Chart(el, {type, data, options: Object.assign({responsive: true, maintainAspectRatio: false}, opts || {})});
}
function fill(id, rows) {
  const t = document.querySelector('#' + id + ' tbody'); if (!t) return;
  t.innerHTML = rows.map(r => '<tr>' + r.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('') || '<tr><td colspan="5" class="text-muted">No data for this range</td></tr>';
}
async function load() {
  const r = $('range'), q = new URLSearchParams({days: r ? r.value : '7'});
  if (r && r.value === 'custom') { q.set('start', $('start').value); q.set('end', $('end').value); }
  const d = await (await fetch('/api/data?' + q)).json();
  draw('sentTrend', 'line', {labels: d.labels, datasets: SENT.map(s => ({label: s, data: d.sent[s], borderColor: col[s], backgroundColor: col[s], tension: .3}))});
  draw('volume', 'bar', {labels: d.labels, datasets: [{label: 'Posts', data: d.volume, backgroundColor: '#0f8b8d'}]});
  draw('crisis', 'line', {labels: d.labels, datasets: [{label: 'Avg crisis score', data: d.crisis, borderColor: '#fd7e14', backgroundColor: 'rgba(253,126,20,.15)', fill: true, tension: .3}]});
  const tk = Object.keys(d.totals);
  draw('sentPie', 'doughnut', {labels: tk, datasets: [{data: Object.values(d.totals), backgroundColor: tk.map(k => col[k])}]});
  draw('kw', 'bar', {labels: d.keywords.map(k => k.keyword), datasets: [{label: 'Posts containing keyword', data: d.keywords.map(k => k.freq), backgroundColor: '#dc3545'}]}, {indexAxis: 'y'});
  draw('platform', 'bar', {labels: d.platforms.map(p => p.platform), datasets: SENT.map(s => ({label: s, data: d.platforms.map(p => p[s]), backgroundColor: col[s]}))}, {scales: {x: {stacked: true}, y: {stacked: true}}});
  draw('engagement', 'bar', {labels: Object.keys(d.engagement), datasets: [{label: 'Total engagement', data: Object.values(d.engagement), backgroundColor: '#6f42c1'}]});
  fill('platTable', d.platforms.map(p => [p.platform, p.Posts, p.Positive, p.Neutral, p.Negative]));
  fill('topNeg', d.top_negative.map(p => [p.platform, p.username, p.text, p.eng, p.score]));
  if ($('totEng')) { $('totEng').textContent = d.total_eng; $('avgEng').textContent = d.avg_eng; }
}
document.addEventListener('DOMContentLoaded', () => {
  const r = $('range');
  if (r) document.querySelectorAll('#range,#start,#end').forEach(e => e.addEventListener('change', () => {
    $('custom').classList.toggle('d-none', r.value !== 'custom'); load(); }));
  load();
  if (window.REFRESH) setInterval(load, window.REFRESH * 1000);
});
