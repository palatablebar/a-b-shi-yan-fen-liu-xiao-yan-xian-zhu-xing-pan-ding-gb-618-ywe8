/** 无框架 UI 组件：表格 / 抽屉 / 过滤条 / 分流条 / 森林图 / 空态 / toast。 */

export function esc(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]),
  );
}

export function fmtTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return esc(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function pct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function signedPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const num = Number(value) * 100;
  return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
}

export function fmtP(value) {
  if (value === null || value === undefined) return '—';
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  if (num === 0) return '<1e-12';
  if (num < 0.0001) return num.toExponential(2).replace('e', 'e');
  return num.toFixed(4);
}

export function num(value, digits = 0) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function badge(tone, text) {
  return `<span class="badge ${esc(tone)}">${esc(text)}</span>`;
}

export function statStrip(items) {
  return `<div class="stat-strip">${items
    .map(
      (item) => `<div class="stat ${esc(item.tone || '')}">
        <span class="k">${esc(item.label)}</span>
        <span class="v">${item.raw ? item.value : esc(item.value)}${item.unit ? `<small>${esc(item.unit)}</small>` : ''}</span>
        <span class="hint">${item.hint || ''}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function emptyState({ title, hint, actionText, actionId }) {
  return `<div class="empty" data-testid="empty-state">
    <div class="mark">${esc(title)}</div>
    <p>${esc(hint || '')}</p>
    ${actionText ? `<button class="btn ghost" id="${esc(actionId || 'empty-action')}">${esc(actionText)}</button>` : ''}
  </div>`;
}

export function errorBox(message, retryId = 'retry-btn') {
  return `<div class="error-box"><span>${esc(message)}</span><button class="btn sm ghost" id="${esc(retryId)}">重试</button></div>`;
}

export function table({ columns, rows, rowId, empty, rowClass }) {
  if (!rows || rows.length === 0) {
    return emptyState(empty || { title: '暂无记录', hint: '调整筛选条件，或先登记一个实验。' });
  }
  const head = columns.map((col) => `<th>${esc(col.label)}</th>`).join('');
  const body = rows
    .map(
      (row) => `<tr data-id="${esc(row.id)}" ${rowId ? `id="${esc(rowId(row))}"` : ''} class="${rowClass ? esc(rowClass(row)) : ''}">
        ${columns
          .map((col) => `<td class="${esc(col.className || '')}">${col.render ? col.render(row) : esc(row[col.key])}</td>`)
          .join('')}
      </tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function drawer({ title, subtitle, body, footer }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true" data-testid="drawer">
    <div class="drawer-head">
      <div>
        <h2>${esc(title)}</h2>
        <div class="mono muted" style="margin-top:3px">${esc(subtitle || '')}</div>
      </div>
      <button class="btn sm ghost" data-close>关闭</button>
    </div>
    <div class="drawer-body">${body}</div>
    ${footer ? `<div class="drawer-foot">${footer}</div>` : ''}
  </aside>`;
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop || event.target.closest('[data-close]')) close();
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(backdrop);
  return { root: backdrop, close };
}

export function kv(items) {
  return `<dl class="kv">${items
    .map(
      ([key, value]) =>
        `<dt>${esc(key)}</dt><dd>${value === undefined || value === null || value === '' ? '—' : value}</dd>`,
    )
    .join('')}</dl>`;
}

export function field({ label, name, type = 'text', value = '', placeholder = '', options = null, attrs = '', hint = '', grow = false }) {
  const control = options
    ? `<select name="${esc(name)}" id="${esc(name)}" ${attrs}>${options
        .map(
          (opt) =>
            `<option value="${esc(opt.value)}" ${String(opt.value) === String(value) ? 'selected' : ''}>${esc(opt.label)}</option>`,
        )
        .join('')}</select>`
    : `<input name="${esc(name)}" id="${esc(name)}" type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs} />`;
  return `<div class="field ${grow ? 'grow' : ''}"><label for="${esc(name)}">${esc(label)}</label>${control}${
    hint ? `<span class="hint">${esc(hint)}</span>` : ''
  }</div>`;
}

/** 共享过滤条：实验登记 / 样本与分流 / 指标检验 三页复用。 */
export function filterBar({ id, fields, actions = '' }) {
  return `<div class="filter-bar" id="${esc(id)}">
    ${fields.join('')}
    <div class="spacer"></div>
    ${actions}
  </div>`;
}

/** 分流条：按变体占比画一条横向比例尺，SRM 告警时整条转红。 */
export function splitBar(cells, alarm = false) {
  if (!cells || !cells.length) return '';
  const total = cells.reduce((sum, cell) => sum + Number(cell.observed || 0), 0) || 1;
  const body = cells
    .map((cell) => {
      const width = (Number(cell.observed || 0) / total) * 100;
      const tone = alarm ? 'alarm' : cell.is_control ? 'control' : 'treat';
      return `<div class="cell ${tone}" style="width:${width.toFixed(2)}%" title="${esc(cell.name)} · ${cell.observed}（计划 ${pct(cell.ratio)}）">${esc(cell.code)} ${pct(cell.share_pct / 100, 1)}</div>`;
    })
    .join('');
  return `<div class="split">${body}</div>
    <div class="split-legend">
      ${cells
        .map(
          (cell) =>
            `<span>${cell.is_control ? '◇' : '◆'} ${esc(cell.code)} 计划 ${pct(cell.ratio)} / 实测 ${pct(
              (cell.share_pct || 0) / 100,
              2,
            )} · ${num(cell.observed)} 份</span>`,
        )
        .join('')}
    </div>`;
}

/**
 * 森林图（纯 CSS）：以 0 为中心，画 lift 点与 95% CI 须。
 * items: [{label, sublabel, lift, low, high, significant, verdict}]
 */
export function forestChart(items) {
  if (!items || !items.length) return '';
  const bound = Math.max(
    0.02,
    ...items.map((item) => Math.max(Math.abs(Number(item.low) || 0), Math.abs(Number(item.high) || 0), Math.abs(Number(item.lift) || 0))),
  );
  const pos = (value) => Math.max(0, Math.min(100, ((Number(value) + bound) / (2 * bound)) * 100));
  const rows = items
    .map((item) => {
      const left = pos(Math.min(item.low, item.lift));
      const right = pos(Math.max(item.high, item.lift));
      const tone = item.significant ? (item.lift >= 0 ? 'sig' : 'neg') : '';
      return `<div class="forest-row">
        <span class="label">${esc(item.label)}${item.sublabel ? `<small>${esc(item.sublabel)}</small>` : ''}</span>
        <div class="forest-track">
          <span class="zero"></span>
          <span class="whisker" style="left:${left.toFixed(2)}%;width:${Math.max(0.6, right - left).toFixed(2)}%"></span>
          <span class="dot ${tone}" style="left:${pos(item.lift).toFixed(2)}%"></span>
        </div>
        <span class="val">${signedPct(item.lift, 1)}<br /><span class="muted">${signedPct(item.low, 1)}~${signedPct(item.high, 1)}</span></span>
      </div>`;
    })
    .join('');
  return `<div class="forest">${rows}</div>
    <div class="axis"><span></span><span class="ticks"><span>${signedPct(-bound, 0)}</span><span>0</span><span>${signedPct(bound, 0)}</span></span><span>lift · CI</span></div>`;
}

export function barList(items, tone = '') {
  const max = Math.max(1, ...items.map((item) => item.count));
  return `<div class="bars">${items
    .map(
      (item) => `<div class="bar-row">
        <span>${esc(item.label)}</span>
        <div class="bar-track"><div class="bar-fill ${esc(item.tone || tone)}" style="width:${Math.round((item.count / max) * 100)}%"></div></div>
        <span class="mono">${esc(item.count)}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function trendChart(points) {
  const max = Math.max(1, ...points.map((point) => point.samples));
  return `<div class="trend">${points
    .map(
      (point) => `<div class="col" title="${esc(point.date)} · 样本 ${num(point.samples)} · 转化率 ${pct(point.rate, 2)}">
        <span class="val">${num(point.samples)}</span>
        <div class="stem" style="height:${Math.max(2, Math.round((point.samples / max) * 52))}px"></div>
        <span class="lbl">${esc(String(point.date || '').slice(5))}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function toast(message, tone = '') {
  const stack = document.getElementById('toast-stack');
  const node = document.createElement('div');
  node.className = `toast ${tone}`;
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

export function errorMessage(err) {
  if (!err) return '未知错误';
  if (err.code === 'FORBIDDEN') return '当前角色没有这个操作的权限';
  if (err.code === 'NO_SAMPLES') return err.message || '还没有分流样本，先录入样本';
  return err.message || '请求失败';
}
