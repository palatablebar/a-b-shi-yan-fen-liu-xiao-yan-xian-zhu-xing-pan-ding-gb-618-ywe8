import { api } from '../api.js';
import { ENUMS, can, srmTone, statusTone, verdictTone } from '../config.js';
import {
  badge,
  drawer,
  errorBox,
  errorMessage,
  esc,
  field,
  filterBar,
  fmtP,
  fmtTime,
  kv,
  num,
  pct,
  signedPct,
  splitBar,
  table,
  toast,
} from '../ui.js';

const state = { q: '', status: '', metric: '', srmAlarm: '' };

function variantRowsHtml(rows, startIndex = 0) {
  return rows
    .map((row, offset) => {
      const index = startIndex + offset;
      return `<div class="variant-row" data-index="${index}" style="display:grid;grid-template-columns:1fr 1.4fr 0.8fr 0.7fr auto;gap:8px;align-items:end">
        ${field({ label: `变体 ${index + 1} 编码`, name: `v_code_${index}`, value: row.code })}
        ${field({ label: '名称', name: `v_name_${index}`, value: row.name })}
        ${field({ label: '计划比例', name: `v_ratio_${index}`, value: row.ratio, type: 'number', attrs: 'step="0.01" min="0.01" max="1"' })}
        ${field({
          label: '角色',
          name: `v_role_${index}`,
          value: row.is_control ? 'control' : 'treat',
          options: [
            { value: 'control', label: '对照' },
            { value: 'treat', label: '实验' },
          ],
        })}
        ${index > 1 ? '<button type="button" class="btn sm ghost" data-remove>移除</button>' : '<span></span>'}
      </div>`;
    })
    .join('');
}

function detailBody(item) {
  const srm = item.srm || {};
  const payload = srm.payload || {};
  const metrics = item.metrics || [];
  return `${kv([
    ['编号', `<span class="mono">${esc(item.code)}</span>`],
    ['负责人', esc(item.owner)],
    ['状态', badge(statusTone(item.status), item.status_label)],
    ['主指标', `${esc(item.primary_metric_label)} <span class="mono muted">${esc(item.primary_metric)}</span>`],
    ['基准转化率', pct(item.baseline_rate, 2)],
    ['目标最小效应', pct(item.planned_mde, 2)],
    ['α / 目标功效', `${item.alpha} / ${pct(item.power_target, 0)}`],
    ['样本合计', `${num(item.sample_total)} 份 · ${num(item.assignment_rows)} 行（主指标口径）`],
    ['分流说明', esc(item.traffic_note || '—')],
    ['日期', `${esc(item.started_on || '—')} ~ ${esc(item.ended_on || '进行中')}`],
  ])}
  <div style="margin-top:10px">
    <div class="eyebrow">假设</div>
    <p style="margin:4px 0 0">${esc(item.hypothesis || '—')}</p>
  </div>
  <h3 style="margin:14px 0 6px;font-size:0.95rem">变体与计划比例</h3>
  ${table({
    rows: item.variants.map((variant) => ({ ...variant, id: variant.id })),
    columns: [
      { key: 'code', label: '编码', className: 'mono' },
      { key: 'name', label: '名称' },
      { key: 'ratio', label: '计划比例', className: 'num', render: (row) => pct(row.ratio, 2) },
      { key: 'is_control', label: '角色', render: (row) => (row.is_control ? badge('info', '对照') : badge('medium', '实验')) },
    ],
  })}
  <h3 style="margin:14px 0 6px;font-size:0.95rem">SRM 与功效快照</h3>
  ${
    srm.checked_at
      ? `<div class="checkline">
          <div class="item"><span class="k">χ²</span><span class="v ${srm.alarm ? 'fail' : 'pass'}">${Number(srm.chi2 || 0).toFixed(3)}</span></div>
          <div class="item"><span class="k">p 值</span><span class="v ${srm.alarm ? 'fail' : 'pass'}">${fmtP(srm.p_value)}</span></div>
          <div class="item"><span class="k">每变体所需样本</span><span class="v">${num(srm.required_per_variant)}</span></div>
        </div>
        <div style="margin-top:8px">${splitBar(payload.cells || [], srm.alarm)}</div>
        <p class="muted" style="margin:6px 0">${esc(payload.note || '')}</p>
        <div class="note">当前功效 ${pct(srm.power_at_current, 1)} · 能检测的最小效应 ${pct(srm.mde_at_current, 2)}</div>`
      : '<p class="muted">还没跑过 SRM 校验，去「样本与分流」跑一次。</p>'
  }
  <h3 style="margin:14px 0 6px;font-size:0.95rem">指标检验（最近一次）</h3>
  ${
    metrics.length
      ? table({
          rows: metrics.map((metric, index) => ({ ...metric, id: `${metric.variant_code}-${metric.metric_key}-${index}` })),
          columns: [
            { key: 'metric_name', label: '指标', render: (row) => `${esc(row.metric_name)}${row.is_primary ? ' <span class="badge medium">主</span>' : ''}` },
            { key: 'variant_code', label: '变体', className: 'mono' },
            { key: 'lift', label: 'lift', className: 'num', render: (row) => signedPct(row.lift, 1) },
            { key: 'p_value', label: 'p', className: 'num', render: (row) => fmtP(row.p_value) },
            { key: 'q_value', label: 'q', className: 'num', render: (row) => fmtP(row.q_value) },
            { key: 'verdict', label: '结论', render: (row) => badge(verdictTone(row.verdict), row.verdict_label) },
          ],
        })
      : '<p class="muted">还没有检验结果。</p>'
  }
  <h3 style="margin:14px 0 6px;font-size:0.95rem">决策</h3>
  ${
    item.decision
      ? `<div class="verdict-card ${esc(item.decision.verdict)}">
          <span class="verdict">${esc(item.decision.verdict_label)}</span>
          <span class="muted">${esc(item.decision.decided_by)} · ${fmtTime(item.decision.decided_at)}</span>
          <p style="margin:0">${esc(item.decision.rationale)}</p>
        </div>`
      : '<p class="muted">还没有出决策。</p>'
  }`;
}

function openDetail(view, ctx, item) {
  const { root, close } = drawer({
    title: item.name,
    subtitle: `${item.code} · ${item.primary_metric_label}`,
    body: detailBody(item),
    footer: `<div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn sm ghost" data-samples>看分流样本</button>
      <button class="btn sm ghost" data-metrics>看指标检验</button>
      <button class="btn sm ghost" data-close>关闭</button>
    </div>`,
  });
  root.querySelector('[data-samples]')?.addEventListener('click', () => {
    close();
    location.hash = `#/assignments?experiment=${item.id}`;
  });
  root.querySelector('[data-metrics]')?.addEventListener('click', () => {
    close();
    location.hash = `#/metrics?experiment=${item.id}`;
  });
}

function openCreate(view, ctx) {
  const rows = [
    { code: 'control', name: '对照：线上原样', ratio: '0.5', is_control: true },
    { code: 'treat_a', name: '实验：新方案', ratio: '0.5', is_control: false },
  ];
  const { root, close } = drawer({
    title: '登记实验',
    subtitle: '把假设、基准转化率与目标最小效应一次写清',
    body: `<form id="experiment-form" style="display:grid;gap:12px">
      <div style="display:grid;grid-template-columns:1fr 1.6fr;gap:10px">
        ${field({ label: '实验编号', name: 'code', placeholder: 'EXP-2615-NEWCARD' })}
        ${field({ label: '实验名称', name: 'name', placeholder: '商品卡图片比例 1:1 → 4:3' })}
      </div>
      ${field({ label: '假设', name: 'hypothesis', placeholder: '大图能提升点击率 0.5pp' })}
      <div style="display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:10px">
        ${field({
          label: '主指标',
          name: 'primary_metric',
          value: 'order_rate',
          options: Object.entries(ENUMS.metric).map(([value, label]) => ({ value, label })),
        })}
        ${field({ label: '基准转化率', name: 'baseline_rate', type: 'number', value: '0.101', attrs: 'step="0.001" min="0.001" max="0.999"' })}
        ${field({ label: '目标最小效应', name: 'planned_mde', type: 'number', value: '0.012', attrs: 'step="0.001" min="0.001"' })}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        ${field({ label: 'α（显著性水平）', name: 'alpha', type: 'number', value: '0.05', attrs: 'step="0.01" min="0.01" max="0.2"' })}
        ${field({ label: '目标功效', name: 'power_target', type: 'number', value: '0.8', attrs: 'step="0.05" min="0.5" max="0.95"' })}
      </div>
      ${field({ label: '分流说明', name: 'traffic_note', placeholder: '50/50，按 device_id 哈希' })}
      <div>
        <div class="eyebrow" style="margin-bottom:6px">变体（比例合计约等于 1）</div>
        <div id="variant-rows" style="display:grid;gap:8px">${variantRowsHtml(rows)}</div>
        <button type="button" class="btn sm ghost" id="add-variant" style="margin-top:8px">添加变体</button>
      </div>
      <div class="form-error" id="experiment-error"></div>
      <button class="btn accent" type="submit">登记并进入样本录入</button>
    </form>`,
  });

  const container = root.querySelector('#variant-rows');
  const bind = () => {
    container.querySelectorAll('[data-remove]').forEach((button) => {
      button.onclick = () => {
        button.closest('.variant-row').remove();
      };
    });
  };
  bind();
  root.querySelector('#add-variant').addEventListener('click', () => {
    const index = container.querySelectorAll('.variant-row').length;
    if (index >= 4) {
      toast('最多 4 个变体', 'err');
      return;
    }
    container.insertAdjacentHTML(
      'beforeend',
      variantRowsHtml([{ code: `treat_${String.fromCharCode(97 + index)}`, name: `实验组 ${index}`, ratio: '0.33', is_control: false }], index),
    );
    bind();
  });

  root.querySelector('#experiment-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const errorNode = root.querySelector('#experiment-error');
    const variants = [...container.querySelectorAll('.variant-row')].map((row) => {
      const inputs = row.querySelectorAll('input, select');
      return {
        code: (inputs[0]?.value || '').trim(),
        name: (inputs[1]?.value || '').trim(),
        ratio: Number(inputs[2]?.value || 0),
        is_control: inputs[3]?.value === 'control',
      };
    });
    const filtered = variants.filter((item) => item.code && item.name);
    const controlCount = filtered.filter((item) => item.is_control).length;
    if (controlCount !== 1) {
      errorNode.textContent = '必须有且只有一个对照组';
      return;
    }
    const ratioSum = filtered.reduce((sum, item) => sum + item.ratio, 0);
    if (Math.abs(ratioSum - 1) > 0.02) {
      errorNode.textContent = `计划比例合计应为 1，当前 ${ratioSum.toFixed(2)}`;
      return;
    }
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    button.textContent = '登记中…';
    try {
      const created = await api.post('/api/experiments', {
        code: form.code.value.trim(),
        name: form.name.value.trim(),
        hypothesis: form.hypothesis.value.trim(),
        primary_metric: form.primary_metric.value,
        baseline_rate: Number(form.baseline_rate.value),
        planned_mde: Number(form.planned_mde.value),
        alpha: Number(form.alpha.value),
        power_target: Number(form.power_target.value),
        traffic_note: form.traffic_note.value.trim() || null,
        variants: filtered,
      });
      toast(`实验 ${created.code} 已登记`);
      close();
      await experimentsPage.render(view, ctx);
    } catch (err) {
      errorNode.textContent =
        err.code === 'CONFLICT' ? '实验编号已存在，换一个' : err.code === 'VALIDATION' ? errorMessage(err) : errorMessage(err);
      button.disabled = false;
      button.textContent = '登记并进入样本录入';
    }
  });
}

export const experimentsPage = {
  async render(view, ctx) {
    const query = { limit: 50, q: state.q, status: state.status, primary_metric: state.metric, srm_alarm: state.srmAlarm };
    let data;
    try {
      data = await api.get('/api/experiments', query);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => experimentsPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>实验登记</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${data.total} 个</span>
            ${can(ctx.user.role, 'experiment:write') ? '<button class="btn sm accent" id="new-experiment">登记实验</button>' : '<span class="mono muted">只读角色可查看</span>'}
          </div>
        </div>
        <div class="panel-body">
          ${filterBar({
            id: 'experiment-filters',
            fields: [
              field({ label: '搜索', name: 'q', value: state.q, placeholder: '编号 / 名称 / 假设', grow: true }),
              field({
                label: '状态',
                name: 'status',
                value: state.status,
                options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.experimentStatus).map(([value, label]) => ({ value, label }))],
              }),
              field({
                label: '主指标',
                name: 'primary_metric',
                value: state.metric,
                options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.metric).map(([value, label]) => ({ value, label }))],
              }),
              field({
                label: 'SRM',
                name: 'srm_alarm',
                value: state.srmAlarm,
                options: [
                  { value: '', label: '全部' },
                  { value: 'true', label: '仅告警' },
                  { value: 'false', label: '均衡' },
                ],
              }),
            ],
          })}
        </div>
        ${table({
          rows: data.items,
          rowId: (row) => `exp-row-${row.code}`,
          columns: [
            { key: 'code', label: '编号', className: 'mono nowrap' },
            {
              key: 'name',
              label: '实验',
              render: (row) => `<b>${esc(row.name)}</b><div class="mono muted">${esc(row.hypothesis || '').slice(0, 34)}</div>`,
            },
            { key: 'primary_metric_label', label: '主指标', className: 'nowrap' },
            {
              key: 'variants',
              label: '变体',
              render: (row) => row.variants.map((variant) => `<span class="mono">${esc(variant.code)}</span> ${pct(variant.ratio, 0)}`).join(' · '),
            },
            { key: 'status', label: '状态', render: (row) => badge(statusTone(row.status), row.status_label) },
            {
              key: 'srm',
              label: 'SRM',
              render: (row) =>
                `${badge(srmTone(row.srm.status), row.srm.status_label)}${
                  row.srm.p_value !== null && row.srm.p_value !== undefined ? `<div class="mono muted">p=${fmtP(row.srm.p_value)}</div>` : ''
                }`,
            },
            { key: 'started_on', label: '开始', className: 'mono nowrap' },
          ],
          empty: { title: '还没有实验', hint: '登记一个实验，再录入分流样本。' },
        })}
      </section>`;

    const filters = view.querySelector('#experiment-filters');
    const applyFilters = () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.status = filters.querySelector('[name=status]').value;
      state.metric = filters.querySelector('[name=primary_metric]').value;
      state.srmAlarm = filters.querySelector('[name=srm_alarm]').value;
      experimentsPage.render(view, ctx);
    };
    filters?.addEventListener('change', applyFilters);
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') applyFilters();
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', async () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (!item) return;
        try {
          const detail = await api.get(`/api/experiments/${item.id}`);
          openDetail(view, ctx, detail);
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    });
    view.querySelector('#new-experiment')?.addEventListener('click', () => openCreate(view, ctx));

    if (ctx.query.focus) {
      const target = data.items.find((entry) => String(entry.id) === String(ctx.query.focus));
      if (target) {
        try {
          const detail = await api.get(`/api/experiments/${target.id}`);
          openDetail(view, ctx, detail);
        } catch {
          /* 忽略：focus 只是快捷入口 */
        }
      }
    }
  },
};

export default experimentsPage;
