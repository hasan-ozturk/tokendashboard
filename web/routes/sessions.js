import { api, fmt } from '/web/app.js';
import { lineChart } from '/web/charts.js';

export default async function (root) {
  const id = decodeURIComponent(location.hash.split('/')[2] || '');
  if (!id) return renderList(root);
  return renderSession(root, id);
}

async function renderList(root) {
  const project = new URLSearchParams(location.hash.split('?')[1] || '').get('project');
  const list = await api('/api/sessions?limit=100' + (project ? '&project=' + encodeURIComponent(project) : ''));
  const projectName = project && list.length ? list[0].project_name || project : project;
  root.innerHTML = `
    <div class="card">
      <h2 style="display:flex;align-items:center">Sessions${project ? `
        <span class="badge" style="margin-left:12px" title="${fmt.htmlSafe(project)}">project: ${fmt.htmlSafe(projectName)}</span>
        <a href="#/sessions" class="muted" style="margin-left:8px;font-size:13px">✕ clear</a>` : ''}
        <span class="spacer"></span>${project ? `<a href="#/projects" class="muted" style="font-size:13px">← projects</a>` : ''}
      </h2>
      <table>
        <thead><tr><th>started</th><th>title</th><th>project</th><th class="num">turns</th><th class="num">tokens</th><th>session</th></tr></thead>
        <tbody>
          ${list.map(s => `
            <tr>
              <td class="mono">${fmt.ts(s.started)}</td>
              <td class="blur-sensitive" title="${fmt.htmlSafe(s.title || '')}"><a href="#/sessions/${encodeURIComponent(s.session_id)}">${fmt.htmlSafe(fmt.short(s.title || '(untitled)', 70))}</a></td>
              <td title="${fmt.htmlSafe(s.project_slug)}">${fmt.htmlSafe(s.project_name || s.project_slug)}</td>
              <td class="num">${fmt.int(s.turns)}</td>
              <td class="num">${fmt.int(s.tokens)}</td>
              <td><a href="#/sessions/${encodeURIComponent(s.session_id)}" class="mono">${fmt.htmlSafe(s.session_id.slice(0,8))}…</a></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

// Returns the KPI row and the tab panels of a session page.
function renderSummary(s, turns) {
  const kpi = (label, value, title, cls = '') => `
    <div class="card kpi ${cls}"><div class="label">${label}</div><div class="value" title="${title}">${value}</div></div>`;
  const sum = (k) => s.models.reduce((a, m) => a + (m[k] || 0), 0);
  const cacheCreate = sum('cache_create_5m_tokens') + sum('cache_create_1h_tokens');
  // total: the <td> cells of a "Total" footer row; the label cell is added here.
  const table = (title, note, head, rows, empty, total) => `
    <div class="card">
      <h3>${title}</h3>${note ? `<div class="muted" style="font-size:12px;margin-bottom:8px">${note}</div>` : ''}
      ${rows.length ? `<table><thead><tr>${head}</tr></thead><tbody>${rows.join('')}</tbody>${total ? `
        <tfoot><tr style="font-weight:600;border-top:2px solid #283040"><td>Total</td>${total}</tr></tfoot>` : ''}</table>`
                    : `<div class="muted">${empty}</div>`}
    </div>`;
  const add = (rows, k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
  const num = n => `<td class="num">${fmt.int(n)}</td>`;
  const tok = n => `<td class="num" title="${fmt.int(n)}">${fmt.compact(n)}</td>`;
  const name = (v, n = 90) => `<td class="mono blur-sensitive" title="${fmt.htmlSafe(v || '')}">${fmt.htmlSafe(fmt.short(v || '—', n))}</td>`;
  const rows = turns.filter(t => t.type !== 'attachment');
  const turnSum = k => rows.reduce((a, t) => a + (t.type === 'assistant' ? t[k] || 0 : 0), 0);

  const kpis = `
    <div class="row cols-7" style="margin-top:16px">
      ${kpi('Est. cost', fmt.usd(s.cost_usd), fmt.usd4(s.cost_usd), 'cost')}
      ${kpi('Input', fmt.compact(sum('input_tokens')), fmt.int(sum('input_tokens')) + ' tokens')}
      ${kpi('Output', fmt.compact(sum('output_tokens')), fmt.int(sum('output_tokens')) + ' tokens')}
      ${kpi('Cache read', fmt.compact(sum('cache_read_tokens')), fmt.int(sum('cache_read_tokens')) + ' tokens')}
      ${kpi('Cache create', fmt.compact(cacheCreate), fmt.int(cacheCreate) + ' tokens')}
      ${kpi('Tool calls', fmt.int(s.tool_calls), s.subagent_calls + ' in subagents')}
      ${kpi('Tool results', fmt.compact(s.result_tokens), '≈ tokens brought into context (chars/4)')}
    </div>`;

  const tabs = [
    { key: 'overview', label: 'Overview', html: `
      <div class="card">
        <h3>Context size per turn</h3>
        <div class="muted" style="font-size:12px;margin-bottom:8px">Tokens the model saw on each main-thread turn (input + cache read + cache write).
          First turn: ${fmt.int(s.context.length ? s.context[0].tokens : 0)} tokens, peak: ${fmt.int(Math.max(0, ...s.context.map(c => c.tokens)))}. A sharp drop is a compaction.</div>
        <div id="ch-context" style="height:220px"></div>
      </div>
      <div style="margin-top:16px">
      ${table('Cost by model', '', '<th>model</th><th class="num">turns</th><th class="num">in</th><th class="num">out</th><th class="num">cache rd</th><th class="num">cache wr</th><th class="num">cost</th>',
        s.models.map(m => `<tr>
          <td><span class="badge ${fmt.modelClass(m.model)}">${fmt.htmlSafe(fmt.modelShort(m.model))}</span></td>
          <td class="num">${fmt.int(m.turns)}</td>${tok(m.input_tokens)}${tok(m.output_tokens)}${tok(m.cache_read_tokens)}
          ${tok(m.cache_create_5m_tokens + m.cache_create_1h_tokens)}
          <td class="num">${fmt.usd(m.cost_usd)}${m.cost_estimated ? ' <span class="muted" title="no exact price, tier estimate">~</span>' : ''}</td></tr>`),
        'No model turns.',
        `${num(add(s.models, 'turns'))}${tok(sum('input_tokens'))}${tok(sum('output_tokens'))}${tok(sum('cache_read_tokens'))}${tok(cacheCreate)}<td class="num">${fmt.usd(s.cost_usd)}</td>`)}
      </div>` },

    { key: 'steps', label: `Steps (${s.steps.length})`, html:
      table('Steps — cost per prompt', 'Newest first. Each prompt you typed, with every reply and subagent turn until the next prompt.',
        '<th>time</th><th>prompt</th><th class="num">turns</th><th>tools</th><th class="num">cost</th>',
        [...s.steps].reverse().map(st => `<tr>
          <td class="mono">${fmt.htmlSafe((st.ts || '').slice(11, 19))}</td>
          <td class="blur-sensitive" title="${fmt.htmlSafe(st.prompt)}">${fmt.htmlSafe(fmt.short(st.prompt, 90))}</td>
          <td class="num">${fmt.int(st.turns)}</td>
          <td class="mono muted">${fmt.htmlSafe(Object.entries(st.tools).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, v]) => `${k} ${v}`).join(' · '))}</td>
          <td class="num">${fmt.usd(st.cost_usd)}</td></tr>`),
        'No prompts.',
        `<td>${s.steps.length} prompts</td>${num(add(s.steps, 'turns'))}<td></td><td class="num">${fmt.usd(add(s.steps, 'cost_usd'))}</td>`) },

    { key: 'loaded', label: `Auto-loaded (${s.loaded.length})`, html:
      table('Loaded into context automatically', 'What entered the context without a tool call: CLAUDE.md, rules and memory files, skills, hook output, MCP instructions, tool and skill lists. Tokens ≈ chars/4. The system prompt and tool definitions are only partly in the transcript, so the first-turn context on Overview is the full baseline.',
        '<th>kind</th><th>name</th><th class="num">loads</th><th class="num">tokens each</th><th class="num">tokens total</th>',
        s.loaded.map(r => `<tr><td class="mono">${fmt.htmlSafe(r.kind)}</td>${name(r.name, 80)}<td class="num">${fmt.int(r.loads)}</td>${tok(r.tokens)}${tok(r.total_tokens)}</tr>`),
        'Nothing recorded.',
        `<td></td>${num(add(s.loaded, 'loads'))}<td></td>${tok(add(s.loaded, 'total_tokens'))}`) },

    { key: 'tools', label: `Tools (${s.tools.length})`, html: `
      ${table('Tools', 'Result tokens = what each tool brought into context.', '<th>tool</th><th class="num">calls</th><th class="num" title="Includes non-zero exit codes, e.g. grep with no match or diff with differences">errors / exit≠0</th><th class="num">result tokens</th>',
        s.tools.map(t => `<tr>${name(t.name, 50)}<td class="num">${fmt.int(t.calls)}</td><td class="num">${t.errors || ''}</td>${tok(t.result_tokens)}</tr>`),
        'No tool calls.',
        `${num(add(s.tools, 'calls'))}${num(add(s.tools, 'errors'))}${tok(add(s.tools, 'result_tokens'))}`)}
      <div style="margin-top:16px">
      ${table('Biggest tool results', 'Top 10 tool results by tokens brought into context.', '<th>tool</th><th>target</th><th class="num">tokens</th>',
        s.top_results.map(c => `<tr>${name(c.tool, 40)}${name(c.target, 120)}${tok(c.result_tokens)}</tr>`),
        'No tool results.',
        `<td class="muted">top ${s.top_results.length} of ${fmt.int(s.tool_calls)} calls</td>${tok(add(s.top_results, 'result_tokens'))}`)}
      </div>` },

    { key: 'files', label: `Files (${s.files.length})`, html:
      table('Files read / written', '', '<th>path</th><th class="num">reads</th><th class="num">writes</th><th class="num">tokens</th>',
        s.files.map(f => `<tr>${name(f.path, 140)}<td class="num">${f.reads || ''}</td><td class="num">${f.writes || ''}</td>${tok(f.result_tokens)}</tr>`),
        'No files read or written.',
        `${num(add(s.files, 'reads'))}${num(add(s.files, 'writes'))}${tok(add(s.files, 'result_tokens'))}`) },

    { key: 'web', label: `MCP & web (${s.mcp.length + s.urls.length})`, html:
      table('MCP servers & web', '', '<th>source</th><th class="num">calls</th><th class="num">tokens</th>',
        [...s.mcp.map(m => `<tr><td class="mono" title="${fmt.htmlSafe(m.tools.join(', '))}">MCP ${fmt.htmlSafe(m.server)}</td><td class="num">${fmt.int(m.calls)}</td>${tok(m.result_tokens)}</tr>`),
         ...s.urls.map(u => `<tr>${name(u.url, 140)}<td class="num">${fmt.int(u.calls)}</td>${tok(u.result_tokens)}</tr>`)],
        'No MCP or web calls.',
        `${num(add(s.mcp, 'calls') + add(s.urls, 'calls'))}${tok(add(s.mcp, 'result_tokens') + add(s.urls, 'result_tokens'))}`) },

    { key: 'turns', label: `Turn-by-turn (${rows.length})`, html:
      table('Turn-by-turn', '', '<th>time</th><th>type</th><th>model</th><th class="blur-sensitive">prompt / tools</th><th class="num">in</th><th class="num">out</th><th class="num">cache rd</th>',
        rows.map(t => {
          const tools = t.tool_calls_json ? JSON.parse(t.tool_calls_json) : [];
          const what = t.prompt_text ? fmt.short(t.prompt_text, 110) : tools.map(x => x.name).join(' · ');
          return `<tr>
            <td class="mono">${(t.timestamp || '').slice(11,19)}</td>
            <td>${t.type}${t.is_sidechain ? ' <span class="badge">side</span>' : ''}</td>
            <td>${t.model ? `<span class="badge ${fmt.modelClass(t.model)}">${fmt.htmlSafe(fmt.modelShort(t.model))}</span>` : ''}</td>
            <td class="blur-sensitive">${fmt.htmlSafe(what)}</td>
            <td class="num">${fmt.int(t.input_tokens)}</td>
            <td class="num">${fmt.int(t.output_tokens)}</td>
            <td class="num">${fmt.int(t.cache_read_tokens)}</td>
          </tr>`;
        }),
        'No records.',
        `<td></td><td></td><td></td>${num(turnSum('input_tokens'))}${num(turnSum('output_tokens'))}${num(turnSum('cache_read_tokens'))}`) },
  ];
  return { kpis, tabs };
}

async function renderSession(root, id) {
  const [turns, summary] = await Promise.all([
    api('/api/sessions/' + encodeURIComponent(id)),
    api('/api/sessions/' + encodeURIComponent(id) + '/summary'),
  ]);
  const slug = (turns[0] && turns[0].project_slug) || '';
  const cwd = (turns.find(t => t.cwd) || {}).cwd || '';
  const base = cwd ? cwd.replace(/\\/g, '/').replace(/\/+$/, '').split('/').pop() : '';
  const project = base || slug;
  const started = (turns[0] && turns[0].timestamp) || '';
  const ended = (turns[turns.length-1] && turns[turns.length-1].timestamp) || '';
  const { kpis, tabs } = renderSummary(summary, turns);
  const saved = localStorage.getItem('td.session-tab');
  const active = tabs.some(t => t.key === saved) ? saved : 'overview';

  root.innerHTML = `
    <div class="card">
      <h2 style="display:flex;align-items:center">
        <span class="blur-sensitive" title="${fmt.htmlSafe(id)}">${fmt.htmlSafe(summary.title || 'Session ' + id.slice(0,8) + '…')}</span>
        <span class="spacer"></span>
        <a href="/api/sessions/${encodeURIComponent(id)}/summary.md" class="muted" style="margin-right:16px">⬇ export .md</a>
        <a href="#/sessions" class="muted">← all sessions</a>
      </h2>
      <div class="flex muted" style="font-family:var(--mono);font-size:12px;flex-wrap:wrap;gap:14px">
        <span>${fmt.htmlSafe(project)}</span>
        <span>${fmt.ts(started)} → ${fmt.ts(ended)}</span>
        <span>${turns.length} records</span>
      </div>
    </div>

    ${kpis}

    <div class="range-tabs" id="session-tabs" style="margin-top:16px">
      ${tabs.map(t => `<button data-tab="${t.key}" class="${t.key === active ? 'active' : ''}">${fmt.htmlSafe(t.label)}</button>`).join('')}
    </div>
    ${tabs.map(t => `<div class="session-tab" data-tab="${t.key}" style="margin-top:16px;${t.key === active ? '' : 'display:none'}">${t.html}</div>`).join('')}`;

  let chart = null;
  const drawChart = () => {
    const el = document.getElementById('ch-context');
    if (chart || !el || !summary.context.length || el.offsetParent === null) return;
    chart = lineChart(el, {
      x: summary.context.map(c => (c.ts || '').slice(11, 16)),
      series: [{ name: 'context tokens', data: summary.context.map(c => c.tokens) }],
    });
  };
  // Remember the tab across reloads; draw the chart only once its tab is visible (ECharts needs a size).
  root.querySelector('#session-tabs').addEventListener('click', e => {
    const key = e.target.dataset && e.target.dataset.tab;
    if (!key) return;
    localStorage.setItem('td.session-tab', key);
    root.querySelectorAll('#session-tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === key));
    root.querySelectorAll('.session-tab').forEach(p => { p.style.display = p.dataset.tab === key ? '' : 'none'; });
    drawChart();
  });
  drawChart();
}
