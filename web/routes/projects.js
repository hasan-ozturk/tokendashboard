import { api, fmt } from '/web/app.js';

const RANGES = [
  { key: '7d', label: '7d', days: 7 },
  { key: '30d', label: '30d', days: 30 },
  { key: '90d', label: '90d', days: 90 },
  { key: 'all', label: 'All', days: null },
];

export default async function (root) {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  const range = RANGES.find(r => r.key === q.get('range')) || RANGES[1];
  const since = range.days ? new Date(Date.now() - range.days * 864e5).toISOString().slice(0, 19) : '';
  const branchUrl = commits => '/api/branches?commits=' + commits + (since ? '&since=' + since : '');
  const [rows, fast] = await Promise.all([api('/api/projects'), api(branchUrl(0))]);

  root.innerHTML = `
    <div class="card">
      <h2>Projects</h2>
      <p class="muted" style="margin:-8px 0 14px">Sorted by billable token spend. Cache reads are billed cheaper, so high cache-read columns are good. Click a project to see its sessions.</p>
      <table>
        <thead><tr><th>project</th><th class="num">sessions</th><th class="num">turns</th><th class="num">billable tokens</th><th class="num">cache reads</th></tr></thead>
        <tbody>
          ${rows.map(r => `
            <tr>
              <td title="${fmt.htmlSafe(r.project_slug)}"><a href="#/sessions?project=${encodeURIComponent(r.project_slug)}">${fmt.htmlSafe(r.project_name || r.project_slug)}</a></td>
              <td class="num">${fmt.int(r.sessions)}</td>
              <td class="num">${fmt.int(r.turns)}</td>
              <td class="num">${fmt.int(r.billable_tokens)}</td>
              <td class="num">${fmt.int(r.cache_read_tokens)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <div class="card" style="margin-top:16px">
      <h3 style="display:flex;align-items:center">Cost by project &amp; branch
        <span class="spacer"></span>
        <div class="range-tabs">${RANGES.map(r => `<button data-range="${r.key}" class="${r.key === range.key ? 'active' : ''}">${r.label}</button>`).join('')}</div>
      </h3>
      <p class="muted" style="margin:0 0 12px;font-size:12px">Branch = the git branch Claude Code recorded for each turn. Commits = commits by your git user on that branch made during one of its sessions or up to 1 hour after.
        This is matching by time, so a hand-made commit in the same window also counts. A commit reachable from several branches is counted once, for the branch whose session was active when it was made.
        Line counts include generated and vendored files. Click a row to see its commits.</p>
      <div id="branches"></div>
    </div>`;

  root.querySelectorAll('[data-range]').forEach(b => b.addEventListener('click', () => {
    location.hash = '#/projects?range=' + b.dataset.range;
  }));

  const box = root.querySelector('#branches');
  const draw = (list, loading) => {
    const total = k => list.reduce((a, x) => a + (x[k] || 0), 0);
    const hasGit = x => x.git !== undefined && x.git !== null;
    const lines = (a, d) => `<span style="color:#3FB68B">+${fmt.compact(a)}</span> <span style="color:#E5484D">-${fmt.compact(d)}</span>`;
    const gitCell = x => loading ? '<td class="num muted">…</td><td class="num muted">…</td><td class="num muted">…</td>'
      : hasGit(x) ? `<td class="num">${fmt.int(x.commits)}${x.git.approx ? ' <span class="muted" title="Branch no longer exists; searched all branches">~</span>' : ''}</td>
          <td class="num mono">${lines(x.added, x.deleted)}</td>
          <td class="num">${x.usd_per_commit == null ? '—' : fmt.usd(x.usd_per_commit)}</td>`
      : '<td class="num muted" title="Folder is not a git repo, or it was moved">no git</td><td></td><td></td>';
    const commitList = x => hasGit(x) && x.git.commits.length ? `
      <table style="margin:4px 0 8px">${x.git.commits.map(c => `<tr>
        <td class="mono muted">${fmt.htmlSafe(c.hash.slice(0, 8))}</td>
        <td class="mono muted">${fmt.htmlSafe(c.date.slice(0, 16).replace('T', ' '))}</td>
        <td class="blur-sensitive">${fmt.htmlSafe(c.subject)}</td>
        <td class="num mono">${lines(c.added, c.deleted)}</td></tr>`).join('')}
      </table>`
      : `<span class="muted">${loading ? 'Loading commits…' : hasGit(x) ? 'No matching commits.' : 'No git repo found at ' + fmt.htmlSafe(x.cwd || '?')}</span>`;
    box.innerHTML = list.length ? `
      <table>
        <thead><tr><th>project</th><th>branch</th><th class="num">sessions</th><th class="num">turns</th><th class="num">cost</th>
          <th class="num">commits</th><th class="num">lines</th><th class="num">$ / commit</th><th>last active</th></tr></thead>
        <tbody>${list.map((x, i) => `
          <tr data-i="${i}" style="cursor:pointer">
            <td><a href="#/sessions?project=${encodeURIComponent(x.project_slug)}" onclick="event.stopPropagation()">${fmt.htmlSafe(x.project_name)}</a></td>
            <td class="mono" title="${fmt.htmlSafe(x.cwd || '')}">${fmt.htmlSafe(x.branch || '(none)')}</td>
            <td class="num">${fmt.int(x.session_count)}</td>
            <td class="num">${fmt.int(x.turns)}</td>
            <td class="num">${fmt.usd(x.cost_usd)}</td>
            ${gitCell(x)}
            <td class="mono muted">${fmt.htmlSafe((x.last || '').slice(0, 10))}</td>
          </tr>
          <tr data-for="${i}" style="display:none"><td colspan="9">${commitList(x)}</td></tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:600;border-top:2px solid #283040">
          <td>Total</td><td class="muted">${list.length} branches</td><td></td><td class="num">${fmt.int(total('turns'))}</td>
          <td class="num">${fmt.usd(total('cost_usd'))}</td>
          <td class="num">${loading ? '…' : fmt.int(total('commits'))}</td>
          <td class="num mono">${loading ? '…' : lines(total('added'), total('deleted'))}</td>
          <td></td><td></td></tr></tfoot>
      </table>` : '<div class="muted">No turns in this range.</div>';
    box.querySelectorAll('tr[data-i]').forEach(tr => tr.addEventListener('click', () => {
      const row = box.querySelector(`tr[data-for="${tr.dataset.i}"]`);
      row.style.display = row.style.display === 'none' ? '' : 'none';
    }));
  };
  draw(fast, true);
  // The commit lookup runs git per branch and can take a few seconds the first time.
  const full = await api(branchUrl(1));
  if (location.hash.startsWith('#/projects')) draw(full, false);
}
