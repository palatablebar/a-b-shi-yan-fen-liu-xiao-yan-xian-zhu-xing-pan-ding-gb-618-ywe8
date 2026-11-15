import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
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
  splitBar,
  table,
  toast,
} from '../ui.js';

const state = { experimentId: '', metricKey: '', channel: '', variantCode: '' };

async function loadExperiments() {
  const data = await api.get('/api/experiments', { limit: 50 });
  return data.items;
}

function pickExperiment(items, preferred) {
  if (preferred && items.some((item) => String(item.id) === String(preferred))) {
    return items.find((item) => String(item.id) === String(preferred));
  }
  if (state.experimentId && items.some((item) => String(item.id) === String(state.experimentId))) {
    return items.find((item) => String(item.id) === String(state.experimentId));
  }
  return items[0];
}

function srmCard(experiment) {
  const srm = experiment.srm || {};
  const payload = srm.payload || {};
  if (!srm.checked_at) {
    return `<div class="panel"><div class="panel-head"><h2>SRM 与功效校验</h2><span class="meta">未校验</span></div>
      <div class="panel-body"><p class="muted">这个实验还没跑过分流校验。点上方「跑 SRM 校验」，算法会按 χ² 与样本量缺口给出结论。</p></div></div>`;
  }
  return `<div class="panel">
    <div class="panel-head">
      <h2>SRM 与功效校验</h2>
      <span class="meta">${fmtTime(srm.checked_at)}</span>
    </div>
    <div class="panel-body" style="display:grid;gap:12px">
      ${splitBar(payload.cells || [], srm.alarm)}
      <div class="checkline">
        <div class="item"><span class="k">χ² / df</span><span class="v ${srm.alarm ? 'fail' : 'pass'}">${Number(srm.chi2 || 0).toFixed(2)} / ${esc(srm.df)}</span></div>
        <div class="item"><span class="k">p 值（卡方上尾）</span><span class="v ${srm.alarm ? 'fail' : 'pass'}">${fmtP(srm.p_value)}</span></div>
        <div class="item"><span class="k">每变体所需样本</span><span class="v">${num(srm.required_per_variant)}</span></div>
        <div class="item"><span class="k">当前功效</span><span class="v ${Number(srm.power_at_current) >= 0.8 ? 'pass' : 'fail'}">${pct(srm.power_at_current, 1)}</span></div>
        <div class="item"><span class="k">可检测最小效应</span><span class="v">${pct(srm.mde_at_current, 2)}</span></div>
        <div class="item"><span class="k">样本缺口合计</span><span class="v ${Number(payload.gap_total) > 0 ? 'fail' : 'pass'}">${num(payload.gap_total)}</span></div>
      </div>
      <p class="muted" style="margin:0">${esc(payload.note || '')}</p>
      <div class="note">算法 A：χ² = Σ(obs-exp)²/exp，df=k-1；n = 2(z₁₋α/₂+z₁₋β)²p(1-p)/Δ²</div>
    </div>
  </div>`;
}

function openEntry(view, ctx, experiments) {
  const experiment = pickExperiment(experiments);
  const variants = (experiment && experiment.variants) || [];
  const { root, close } = drawer({
    title: '录入分流样本',
    subtitle: `${experiment ? experiment.code : ''} · 变体 × 渠道 × 日期 × 指标 唯一`,
    body: `<form id="entry-form" style="display:grid;gap:12px">
      ${field({
        label: '实验',
        name: 'experiment_id',
        value: experiment ? experiment.id : '',
        options: experiments.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
      })}
      ${field({
        label: '变体',
        name: 'variant_code',
        options: variants.map((item) => ({ value: item.code, label: `${item.code} · ${item.name}` })),
      })}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        ${field({
          label: '渠道',
          name: 'channel',
          options: Object.entries(ENUMS.channel).map(([value, label]) => ({ value, label })),
        })}
        ${field({
          label: '指标口径',
          name: 'metric_key',
          value: experiment ? experiment.primary_metric : 'order_rate',
          options: Object.entries(ENUMS.metric).map(([value, label]) => ({ value, label })),
        })}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        ${field({ label: '统计日期', name: 'stat_date', type: 'date', value: '2026-06-22' })}
        ${field({ label: '样本数', name: 'samples', type: 'number', value: '1200', attrs: 'min="0"' })}
      </div>
      ${field({ label: '转化数', name: 'conversions', type: 'number', value: '121', attrs: 'min="0"' })}
      <div class="form-error" id="entry-error"></div>
      <button class="btn accent" type="submit">写入样本</button>
    </form>`,
  });
  root.querySelector('#entry-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const errorNode = root.querySelector('#entry-error');
    try {
      await api.post(`/api/experiments/${form.experiment_id.value}/assignments`, {
        variant_code: form.variant_code.value,
        channel: form.channel.value,
        metric_key: form.metric_key.value,
        stat_date: form.stat_date.value,
        samples: Number(form.samples.value),
        conversions: Number(form.conversions.value),
      });
      toast('样本已写入');
      close();
      await assignmentsPage.render(view, ctx);
    } catch (err) {
      errorNode.textContent =
        err.code === 'CONFLICT' ? '这个 变体×渠道×日期×指标 的样本已存在（409），请改数值或换日期' : errorMessage(err);
    }
  });
}

export const assignmentsPage = {
  async render(view, ctx) {
    let experiments;
    try {
      experiments = await loadExperiments();
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => assignmentsPage.render(view, ctx));
      return;
    }
    if (!experiments.length) {
      view.innerHTML = `<section class="panel"><div class="panel-body">${errorBox('还没有实验')}</div></section>`;
      return;
    }
    const experiment = pickExperiment(experiments, ctx.query.experiment);
    state.experimentId = String(experiment.id);
    state.metricKey = ctx.query.metric || state.metricKey || experiment.primary_metric;

    let samples;
    let rows;
    try {
      [samples, rows] = await Promise.all([
        api.get(`/api/experiments/${experiment.id}/samples`, { metric_key: state.metricKey }),
        api.get(`/api/experiments/${experiment.id}/assignments`, {
          limit: 40,
          channel: state.channel,
          metric_key: state.metricKey,
          variant_code: state.variantCode,
        }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => assignmentsPage.render(view, ctx));
      return;
    }

    const totals = samples.totals || [];
    const matrix = samples.matrix || { variants: [], channels: [] };
    const totalSamples = totals.reduce((sum, item) => sum + item.samples, 0);
    const planned = totals.map((item) => item.ratio).reduce((sum, value) => sum + value, 0) || 1;

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>样本与分流</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${num(totalSamples)} 份样本 · ${num(samples.metric_keys.length)} 个指标口径</span>
            ${
              can(ctx.user.role, 'srm:run')
                ? '<button class="btn sm accent" id="run-srm">跑 SRM 校验</button>'
                : '<span class="mono muted">只读角色仅可查看</span>'
            }
          </div>
        </div>
        <div class="panel-body">
          ${filterBar({
            id: 'assignment-filters',
            fields: [
              field({
                label: '实验',
                name: 'experiment',
                value: experiment.id,
                options: experiments.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
              }),
              field({
                label: '指标口径',
                name: 'metric_key',
                value: state.metricKey,
                options: samples.metric_keys.map((key) => ({ value: key, label: ENUMS.metric[key] || key })),
              }),
              field({
                label: '渠道路由',
                name: 'channel',
                value: state.channel,
                options: [{ value: '', label: '全部渠道' }, ...Object.entries(ENUMS.channel).map(([value, label]) => ({ value, label }))],
              }),
              field({
                label: '变体',
                name: 'variant_code',
                value: state.variantCode,
                options: [{ value: '', label: '全部变体' }, ...(experiment.variants || []).map((item) => ({ value: item.code, label: item.code }))],
              }),
            ],
            actions: can(ctx.user.role, 'assignment:write') ? '<button class="btn sm ghost" id="entry-sample">录入样本</button>' : '',
          })}
        </div>
      </section>

      ${srmCard(experiment)}

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>各变体样本对照</h2><span class="meta">plan vs observed</span></div>
          ${table({
            rows: totals.map((item) => ({ ...item, id: item.code })),
            columns: [
              { key: 'code', label: '变体', className: 'mono' },
              { key: 'name', label: '名称' },
              { key: 'ratio', label: '计划', className: 'num', render: (row) => pct(row.ratio / planned, 1) },
              { key: 'samples', label: '实测样本', className: 'num', render: (row) => num(row.samples) },
              { key: 'share', label: '实测占比', className: 'num', render: (row) => pct((row.share_pct || 0) / 100, 2) },
              { key: 'rate', label: '转化率', className: 'num', render: (row) => pct(row.rate, 2) },
            ],
            rowClass: (row) => (row.is_control ? '' : ''),
            empty: { title: '还没有分流样本', hint: '点「录入样本」写入第一格。' },
          })}
          <div class="panel-foot">
            <span class="mono muted">对照组样本 ${num((totals.find((item) => item.is_control) || {}).samples || 0)} 份</span>
            <span class="note">样本不均是 SRM 的唯一来源，先看这一列</span>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2>渠道 × 变体明细</h2><span class="meta">4 个入口</span></div>
          <div class="panel-body" style="padding:0">
            <div class="table-wrap">
              <table class="data matrix-table">
                <thead><tr><th>渠道</th>${matrix.variants
                  .map((variant) => `<th>${esc(variant.code)}${variant.is_control ? ' ◇' : ' ◆'}</th>`)
                  .join('')}<th>渠道合计</th></tr></thead>
                <tbody>
                  ${matrix.channels
                    .map((channel) => {
                      const cells = Object.values(channel.cells || {});
                      const sum = cells.reduce((acc, cell) => acc + Number(cell.samples || 0), 0);
                      return `<tr><td>${esc(channel.label)}</td>${matrix.variants
                        .map((variant) => {
                          const cell = (channel.cells || {})[variant.code] || { samples: 0, conversions: 0 };
                          const rate = cell.samples ? cell.conversions / cell.samples : 0;
                          return `<td class="cell"><b>${num(cell.samples)}</b><small>${pct(rate, 1)}</small></td>`;
                        })
                        .join('')}<td class="cell"><b>${num(sum)}</b></td></tr>`;
                    })
                    .join('')}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-head"><h2>分流样表明细</h2><span class="meta">${rows.total} 行 · 最近 ${rows.items.length} 行</span></div>
        ${table({
          rows: rows.items,
          columns: [
            { key: 'stat_date', label: '日期', className: 'mono nowrap' },
            { key: 'channel_label', label: '渠道' },
            { key: 'variant_code', label: '变体', className: 'mono' },
            { key: 'metric_label', label: '指标' },
            { key: 'samples', label: '样本', className: 'num', render: (row) => num(row.samples) },
            { key: 'conversions', label: '转化', className: 'num', render: (row) => num(row.conversions) },
            { key: 'rate', label: '转化率', className: 'num', render: (row) => pct(row.rate, 2) },
            { key: 'operator_email', label: '记录人', className: 'mono' },
          ],
          empty: { title: '没有符合条件的样本行', hint: '换渠道或指标再看。' },
        })}
      </section>
    `;

    const filters = view.querySelector('#assignment-filters');
    filters?.addEventListener('change', () => {
      state.experimentId = filters.querySelector('[name=experiment]').value;
      state.metricKey = filters.querySelector('[name=metric_key]').value;
      state.channel = filters.querySelector('[name=channel]').value;
      state.variantCode = filters.querySelector('[name=variant_code]').value;
      location.hash = `#/assignments?experiment=${state.experimentId}&metric=${state.metricKey}`;
      assignmentsPage.render(view, ctx);
    });
    view.querySelector('#entry-sample')?.addEventListener('click', () => openEntry(view, ctx, experiments));
    view.querySelector('#run-srm')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = '校验中…';
      try {
        const result = await api.post(`/api/experiments/${experiment.id}/srm-check`, {});
        toast(
          result.alarm
            ? `SRM 告警：χ²=${Number(result.chi2).toFixed(2)}，p=${fmtP(result.p_value)}`
            : `分流均衡：χ²=${Number(result.chi2).toFixed(2)}，p=${fmtP(result.p_value)}`,
          result.alarm ? 'err' : '',
        );
        await assignmentsPage.render(view, ctx);
      } catch (err) {
        toast(errorMessage(err), 'err');
        button.disabled = false;
        button.textContent = '跑 SRM 校验';
      }
    });
  },
};

export default assignmentsPage;
