import { api } from '../api.js';
import { ENUMS, can, verdictTone } from '../config.js';
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
  forestChart,
  kv,
  num,
  pct,
  signedPct,
  table,
  toast,
} from '../ui.js';

const state = { experimentId: '', variantCode: 'all', method: 'bh', q: '' };

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

function openMetric(view, ctx, item) {
  const { root } = drawer({
    title: item.metric_name,
    subtitle: `${item.experiment_code || ''} · ${item.variant_code} · ${item.method_label}`,
    body: `${kv([
      ['对照样本', `${num(item.control_n)}（转化 ${num(item.control_conversions)}，${pct(item.control_rate, 3)}）`],
      ['实验样本', `${num(item.variant_n)}（转化 ${num(item.variant_conversions)}，${pct(item.variant_rate, 3)}）`],
      ['绝对差', signedPct(item.diff, 3)],
      ['相对 lift', signedPct(item.lift, 2)],
      ['95% CI（绝对差）', `${signedPct(item.ci_low, 3)} ~ ${signedPct(item.ci_high, 3)}`],
      ['95% CI（lift）', `${signedPct(item.lift_ci_low, 2)} ~ ${signedPct(item.lift_ci_high, 2)}`],
      ['z 值', `<span class="mono">${Number(item.z).toFixed(4)}</span>`],
      ['p 值', `<span class="mono">${fmtP(item.p_value)}</span>`],
      ['q 值（BH）', `<span class="mono">${fmtP(item.q_bh)}</span>`],
      ['q 值（Bonferroni）', `<span class="mono">${fmtP(item.q_bonferroni)}</span>`],
      ['是否显著', item.significant ? badge('ok', '是') : badge('pending', '否')],
      ['结论', badge(verdictTone(item.verdict), item.verdict_label)],
      ['所需样本', num(item.required_n)],
      ['当前功效', pct(item.power_at_current, 1)],
      ['计算时间', fmtTime(item.computed_at)],
    ])}
    <div class="note">q ≥ 0.05 时 lift 再大也只能写「继续观察」</div>`,
  });
  root.querySelector('[data-close]')?.addEventListener('click', () => {});
}

export const metricsPage = {
  async render(view, ctx) {
    let experiments;
    try {
      experiments = await loadExperiments();
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => metricsPage.render(view, ctx));
      return;
    }
    if (!experiments.length) {
      view.innerHTML = `<section class="panel"><div class="panel-body">${errorBox('还没有实验')}</div></section>`;
      return;
    }
    let experiment = pickExperiment(experiments, ctx.query.experiment);
    // 默认落在「有显著指标」的最近实验上，否则第一台实验
    if (!ctx.query.experiment && !state.experimentId) {
      try {
        const sig = await api.get('/api/metrics', { significant: true, limit: 100 });
        const counts = new Map();
        (sig.items || []).forEach((row) => counts.set(row.experiment_id, (counts.get(row.experiment_id) || 0) + 1));
        let best = null;
        let bestCount = 0;
        experiments.forEach((item) => {
          const count = counts.get(item.id) || 0;
          if (count > bestCount) {
            bestCount = count;
            best = item;
          }
        });
        if (best) experiment = best;
      } catch {
        /* 显著筛选失败时退回第一台实验 */
      }
    }
    state.experimentId = String(experiment.id);

    let data;
    try {
      data = await api.get('/api/metrics', { experiment_id: experiment.id, q: state.q, limit: 100 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => metricsPage.render(view, ctx));
      return;
    }

    const variantCodes = [...new Set(data.items.map((item) => item.variant_code))];
    const activeVariant = state.variantCode !== 'all' && variantCodes.includes(state.variantCode) ? state.variantCode : variantCodes[0] || '';
    const items = data.items.filter((item) => item.variant_code === activeVariant);
    const primary = items.find((item) => item.is_primary);
    const significantCount = items.filter((item) => item.significant).length;
    const methodLabel = ENUMS.correction[items[0] ? items[0].method : state.method] || state.method;

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>指标检验</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${items.length} 个指标 · 校正后显著 ${significantCount} 个</span>
            ${
              can(ctx.user.role, 'metric:run')
                ? '<button class="btn sm accent" id="run-metrics">跑指标检验</button>'
                : '<span class="mono muted">只读角色仅可查看</span>'
            }
          </div>
        </div>
        <div class="panel-body">
          ${filterBar({
            id: 'metric-filters',
            fields: [
              field({
                label: '实验',
                name: 'experiment',
                value: experiment.id,
                options: experiments.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
              }),
              field({
                label: '变体（对比对照）',
                name: 'variant',
                value: activeVariant,
                options: variantCodes.map((code) => ({ value: code, label: code })),
              }),
              field({
                label: '校正方法',
                name: 'method',
                value: items[0] ? items[0].method : state.method,
                options: [
                  { value: 'bh', label: 'BH-FDR' },
                  { value: 'bonferroni', label: 'Bonferroni' },
                ],
              }),
              field({ label: '搜索指标', name: 'q', value: state.q, placeholder: '指标名 / 变体', grow: true }),
            ],
          })}
        </div>
      </section>

      ${
        items.length
          ? `<div class="grid-3-1">
              <section class="panel">
                <div class="panel-head">
                  <h2>${esc(activeVariant)} 的检验结果</h2>
                  <span class="meta">${esc(methodLabel)} · 主指标 ${esc(primary ? primary.metric_name : '—')}</span>
                </div>
                ${table({
                  rows: items,
                  rowClass: (row) => (row.is_primary ? 'is-primary' : ''),
                  columns: [
                    {
                      key: 'metric_name',
                      label: '指标',
                      render: (row) =>
                        `<b>${esc(row.metric_name)}</b>${row.is_primary ? ' <span class="badge medium">主</span>' : ''}<div class="mono muted">${esc(row.metric_key)}</div>`,
                    },
                    {
                      key: 'control_rate',
                      label: '对照',
                      className: 'num',
                      render: (row) => `${pct(row.control_rate, 2)}<div class="mono muted">${num(row.control_conversions)}/${num(row.control_n)}</div>`,
                    },
                    {
                      key: 'variant_rate',
                      label: '实验',
                      className: 'num',
                      render: (row) => `${pct(row.variant_rate, 2)}<div class="mono muted">${num(row.variant_conversions)}/${num(row.variant_n)}</div>`,
                    },
                    { key: 'lift', label: 'lift', className: 'num', render: (row) => signedPct(row.lift, 1) },
                    { key: 'p_value', label: 'p', className: 'num', render: (row) => fmtP(row.p_value) },
                    {
                      key: 'q',
                      label: 'q（生效）',
                      className: 'num',
                      render: (row) => `<b>${fmtP(row.q_value)}</b><div class="mono muted">${row.method}</div>`,
                    },
                    { key: 'significant', label: '显著', render: (row) => (row.significant ? badge('ok', 'q<0.05') : badge('pending', '否')) },
                    { key: 'verdict', label: '结论', render: (row) => badge(verdictTone(row.verdict), row.verdict_label) },
                  ],
                })}
                <div class="panel-foot">
                  <span class="mono muted">z = (p₁-p₂)/√(p̄(1-p̄)(1/n₁+1/n₂))；CI 为 Wald 区间</span>
                  ${primary ? `<span class="note">主指标 p=${fmtP(primary.p_value)} → q=${fmtP(primary.q_value)}，${primary.significant ? '校正后仍显著' : '校正后不显著'}</span>` : ''}
                </div>
              </section>

              <section class="panel">
                <div class="panel-head"><h2>森林图</h2><span class="meta">lift · 95% CI</span></div>
                <div class="panel-body">
                  ${forestChart(
                    items.map((item) => ({
                      label: item.metric_name,
                      sublabel: item.is_primary ? '主指标' : '',
                      lift: item.lift,
                      low: item.lift_ci_low,
                      high: item.lift_ci_high,
                      significant: item.significant,
                    })),
                  )}
                  <div class="note" style="margin-top:10px">须横跨 0 = 区间含 0，不能下结论</div>
                </div>
              </section>
            </div>
            <section class="panel">
              <div class="panel-head"><h2>多重比较校正</h2><span class="meta">m=${items.length}</span></div>
              <div class="panel-body" style="display:grid;gap:8px">
                <p class="muted" style="margin:0">
                  同一变体下 ${items.length} 个指标同时检验：Bonferroni 把 α 除以 m（保守），BH-FDR 控制假发现率（当前生效：
                  <b>${esc(methodLabel)}</b>）。两套 q 值都在表里，切换「校正方法」后重新跑检验即可对比。
                </p>
                ${table({
                  rows: items.map((item) => ({ ...item, id: `${item.metric_key}-q` })),
                  columns: [
                    { key: 'metric_name', label: '指标' },
                    { key: 'p_value', label: 'p', className: 'num', render: (row) => fmtP(row.p_value) },
                    { key: 'q_bh', label: 'q（BH）', className: 'num', render: (row) => fmtP(row.q_bh) },
                    { key: 'q_bonferroni', label: 'q（Bonferroni）', className: 'num', render: (row) => fmtP(row.q_bonferroni) },
                    {
                      key: 'changed',
                      label: '差异',
                      render: (row) =>
                        row.q_bh < 0.05 && row.q_bonferroni >= 0.05
                          ? badge('medium', '仅 BH 显著')
                          : row.q_bonferroni < 0.05
                            ? badge('ok', '两法都显著')
                            : badge('pending', '两法都不显著'),
                    },
                  ],
                })}
              </div>
            </section>`
          : `<section class="panel"><div class="panel-body">${errorBox('这个实验还没有检验结果，点「跑指标检验」。')}</div></section>`
      }
    `;

    const filters = view.querySelector('#metric-filters');
    filters?.addEventListener('change', () => {
      state.experimentId = filters.querySelector('[name=experiment]').value;
      state.variantCode = filters.querySelector('[name=variant]').value;
      state.method = filters.querySelector('[name=method]').value;
      state.q = filters.querySelector('[name=q]').value.trim();
      location.hash = `#/metrics?experiment=${state.experimentId}`;
      metricsPage.render(view, ctx);
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openMetric(view, ctx, item);
      });
    });
    view.querySelector('#run-metrics')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = '检验中…';
      try {
        const result = await api.post(`/api/experiments/${experiment.id}/metric-tests`, {
          method: filters.querySelector('[name=method]').value,
          variant_code: activeVariant || null,
        });
        const total = result.total;
        const sig = (result.results || []).reduce((sum, item) => sum + item.significant_count, 0);
        toast(`${result.method_label}：${total} 条检验，${sig} 条校正后显著`, sig ? '' : 'err');
        await metricsPage.render(view, ctx);
      } catch (err) {
        toast(errorMessage(err), 'err');
        button.disabled = false;
        button.textContent = '跑指标检验';
      }
    });
  },
};

export default metricsPage;
