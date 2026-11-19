import { api, fmt } from '/web/app.js';

const RANGES = [
  { key: '7d', label: '7d', days: 7 },
  { key: '30d', label: '30d', days: 30 },
  { key: '90d', label: '90d', days: 90 },
  { key: 'all', label: 'All', days: null },
];
const SORTS = [
  { key: 'cost', label: 'Most cost' },
  { key: 'recent', label: 'Most recent' },
];
const WHY_TITLE = {
  'output': 'Most of the cost is text the model wrote.',
  'cache read': 'Most of the cost is re-reading a large context on many turns. Long session or many tool turns.',
  'cache write': 'Most of the cost is writing context to the cache: big new input, or a cache rebuild.',
  'input': 'Most of the cost is uncached input.',
};

function readState() {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  return {
    range: RANGES.find(r => r.key === q.get('range')) || RANGES[1],
    sort: SORTS.find(s => s.key === q.get('sort')) || SORTS[0],
    project: q.get('project') || '',
    model: q.get('model') || '',
  };
}

function writeState(st) {
  const q = new URLSearchParams({ range: st.range.key, sort: st.sort.key });
  if (st.project) q.set('project', st.project);
  if (st.model) q.set('model', st.model);
  location.hash = '#/prompts?' + q.toString();
}

export default async function (root) {
  const st = readState();
  const q = new URLSearchParams({ sort: st.sort.key, limit: '100' });
  if (st.range.days) q.set('since', new Date(Date.now() - st.range.days * 864e5).toISOString().slice(0, 19));
  if (st.project) q.set('project', st.project);
  if (st.model) q.set('model', st.model);
  const [data, projects] = await Promise.all([api('/api/steps?' + q), api('/api/projects')]);
  const { summary: s, rows } = data;
  const pct = s.total_usd ? Math.round(100 * s.top10_usd / s.total_usd) : 0;
  const tabs = (items, cur, attr) => `<div class="range-tabs">${items.map(i =>
    `<button data-${attr}="${i.key}" class="${i.key === cur.key ? 'active' : ''}">${i.label}</button>`).join('')}</div>`;
  const select = (id, all, opts, cur) => `<select id="${id}" style="max-width:200px">
    <option value="">${all}</option>${opts.map(([v, l]) => `<option value="${fmt.htmlSafe(v)}" ${v === cur ? 'selected' : ''}>${fmt.htmlSafe(l)}</option>`).join('')}</select>`;

  root.innerHTML = `
    <div class="flex" style="margin-bottom:14px;gap:10px;flex-wrap:wrap">
      <h2 style="margin:0;font-size:16px;letter-spacing:-0.01em">Prompts — most expensive steps</h2>
      <div class="spacer"></div>
      ${tabs(RANGES, st.range, 'range')}
      ${select('f-project', 'All projects', projects.map(p => [p.project_slug, p.project_name || p.project_slug]), st.project)}
      ${select('f-model', 'All models', s.models.map(m => [m, fmt.modelShort(m)]), st.model)}
      ${tabs(SORTS, st.sort, 'sort')}
    </div>

    <div class="row cols-4">
      <div class="card kpi cost"><div class="label">Spend in range</div><div class="value">${fmt.usd(s.total_usd)}</div></div>
      <div class="card kpi"><div class="label">Steps</div><div class="value">${fmt.int(s.steps)}</div></div>
      <div class="card kpi"><div class="label">Top 10 steps</div><div class="value" title="${fmt.usd4(s.top10_usd)}">${fmt.usd(s.top10_usd)} <span class="muted" style="font-size:13px">${pct}% of spend</span></div></div>
      <div class="card kpi"><div class="label">Cache rebuilds</div><div class="value" title="Turns that re-wrote ≥100K tokens of context to the cache">${fmt.int(s.rebuilds)} <span class="muted" style="font-size:13px">${fmt.usd(s.rebuild_usd)}</span></div></div>
    </div>

    <div class="card" style="margin-top:16px">
      <p class="muted" style="margin:0 0 14px">A step is one prompt you typed plus every reply and subagent turn until your next prompt.
        System messages (task notifications, agent messages, images) are counted in the step before them. Click a row to open the session.
        ⚠ = cache rebuild: the whole context was written to the cache again, usually after more than 1 hour idle or a model change. Starting a new session or running /compact first is cheaper.</p>
      <table id="steps">
        <thead><tr><th>time</th><th>project</th><th>session</th><th>prompt</th><th class="num">turns</th><th>why</th><th class="num">cost</th></tr></thead>
        <tbody>
          ${rows.map((r, i) => `
            <tr data-i="${i}" style="cursor:pointer">
              <td class="mono">${fmt.htmlSafe((r.ts || '').slice(5, 16).replace('T', ' '))}</td>
              <td>${fmt.htmlSafe(r.project_name)}</td>
              <td class="blur-sensitive" title="${fmt.htmlSafe(r.title || r.session_id)}">${fmt.htmlSafe(fmt.short(r.title || r.session_id.slice(0, 8), 28))}</td>
              <td class="blur-sensitive" title="${fmt.htmlSafe(r.prompt)}">${fmt.htmlSafe(fmt.short(r.prompt, 70))}</td>
              <td class="num">${fmt.int(r.turns)}</td>
              <td class="mono" title="${fmt.htmlSafe(WHY_TITLE[r.why] || '')}">${fmt.htmlSafe(r.why)}${r.rebuild_tokens ? ` <span title="Cache rebuild: ${fmt.int(r.rebuild_tokens)} tokens re-written, ${fmt.usd(r.rebuild_usd)}">⚠ ${fmt.compact(r.rebuild_tokens)}</span>` : ''}</td>
              <td class="num">${fmt.usd(r.cost_usd)}</td>
            </tr>`).join('') || '<tr><td colspan="7" class="muted">No steps in this range.</td></tr>'}
        </tbody>
        ${rows.length ? `<tfoot><tr style="font-weight:600;border-top:2px solid #283040">
          <td>Total</td><td colspan="3" class="muted">${rows.length} of ${fmt.int(s.steps)} steps shown</td>
          <td class="num">${fmt.int(rows.reduce((a, r) => a + r.turns, 0))}</td><td></td>
          <td class="num">${fmt.usd(rows.reduce((a, r) => a + r.cost_usd, 0))}</td></tr></tfoot>` : ''}
      </table>
    </div>`;

  root.querySelectorAll('[data-range]').forEach(b => b.addEventListener('click', () =>
    writeState({ ...st, range: RANGES.find(r => r.key === b.dataset.range) })));
  root.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () =>
    writeState({ ...st, sort: SORTS.find(x => x.key === b.dataset.sort) })));
  root.querySelector('#f-project').addEventListener('change', e => writeState({ ...st, project: e.target.value }));
  root.querySelector('#f-model').addEventListener('change', e => writeState({ ...st, model: e.target.value }));
  root.querySelectorAll('#steps tbody tr[data-i]').forEach(tr => tr.addEventListener('click', () => {
    localStorage.setItem('td.session-tab', 'steps');
    location.hash = '#/sessions/' + encodeURIComponent(rows[Number(tr.dataset.i)].session_id);
  }));
}
