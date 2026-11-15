import { api } from '../api.js';
import { ENUMS, srmTone, statusTone, verdictTone } from '../config.js';
import {
  barList,
  badge,
  emptyState,
  errorBox,
  errorMessage,
  esc,
  fmtP,
  forestChart,
  num,
  pct,
  signedPct,
  splitBar,
  statStrip,
  table,
  trendChart,
} from '../ui.js';

function alarmPanel(alarm) {
  const payload = alarm.cells || [];
  return `<div class="panel">
    <div class="panel-head">
      <h2>分流告警 · ${esc(alarm.code)}</h2>
      ${badge('srm', 'SRM')}
    </div>
    <div class="panel-body" style="display:grid;gap:10px">
      <div>${splitBar(
        payload.map((cell) => ({ ...cell, share_pct: cell.share_pct })),
        true,
      )}</div>
      <div class="checkline">
        <div class="item"><span class="k">χ²</span><span class="v fail">${Number(alarm.chi2 || 0).toFixed(2)}</span></div>
        <div class="item"><span class="k">df</span><span class="v">${esc(alarm.df)}</span></div>
        <div class="item"><span class="k">p 值</span><span class="v fail">${fmtP(alarm.p_value)}</span></div>
      </div>
      <p class="muted" style="margin:0">${
        payload.length
          ? `计划 ${pct(payload[0].ratio)}/${pct(payload[1].ratio)}，实测 ${pct(payload[0].share_pct / 100, 1)} / ${pct(
              payload[1].share_pct / 100,
              1,
            )}；p < 0.001，分流显著不均。`
          : '计划 50/50，实测偏离超阈值。'
      }</p>
      <div class="note">先修分流，再看指标 —— 这实验的 lift 现在不可信</div>
    </div>
  </div>`;
}

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">读取实验台账…</div></div>';
    let data;
    let experiments;
    try {
      [data, experiments] = await Promise.all([
        api.get('/api/overview'),
        api.get('/api/experiments', { limit: 12 }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
      return;
    }

    const alarms = data.srm_alarms || [];
    const significant = data.significant || [];
    view.innerHTML = `
      ${statStrip([
        { label: '实验台账', value: data.experiments_total, unit: '个', hint: `运行中 ${data.running_total} 个`, raw: true },
        { label: 'SRM 告警', value: data.srm_alarm_total, unit: '个', tone: data.srm_alarm_total ? 'alarm' : '', hint: 'p < 0.001 判为分流不均' },
        { label: '显著指标', value: data.significant_total, unit: '条', hint: `共检验 ${data.metric_total} 条（校正后）` },
        { label: '待决策', value: data.pending_total, unit: '个', tone: 'mustard', hint: `已出决策 ${data.decided_total} 个` },
      ])}

      <div class="grid-3-1">
        <section class="panel">
          <div class="panel-head">
            <h2>实验台账</h2>
            <span class="meta">${data.experiments_total} 个 · 锚点 ${esc(data.anchor_date || '—')}</span>
          </div>
          ${table({
            rows: experiments.items,
            rowId: (row) => `exp-${row.code}`,
            columns: [
              { key: 'code', label: '编号', className: 'mono nowrap' },
              { key: 'name', label: '实验', render: (row) => `<b>${esc(row.name)}</b><div class="mono muted">${esc(row.primary_metric_label)} · ${row.variants.length} 变体</div>` },
              {
                key: 'status',
                label: '状态',
                render: (row) => badge(statusTone(row.status), ENUMS.experimentStatus[row.status] || row.status),
              },
              {
                key: 'srm',
                label: 'SRM',
                render: (row) =>
                  `${badge(srmTone(row.srm.status), ENUMS.srm[row.srm.status] || row.srm.status)}${
                    row.srm.p_value !== null && row.srm.p_value !== undefined
                      ? `<div class="mono muted">p=${fmtP(row.srm.p_value)}</div>`
                      : ''
                  }`,
              },
              {
                key: 'samples',
                label: '样本',
                className: 'num',
                render: (row) => num(row.srm.payload && row.srm.payload.total ? row.srm.payload.total : 0),
              },
            ],
            empty: { title: '还没有登记实验', hint: '去「实验登记」建第一个实验。' },
          })}
        </section>

        <div style="display:grid;gap:16px;align-content:start">
          ${alarms.length ? alarmPanel(alarms[0]) : `<div class="panel"><div class="panel-head"><h2>分流告警</h2><span class="meta">none</span></div><div class="panel-body">${emptyState({ title: '没有 SRM 告警', hint: '所有实验的分流都没有显著偏差。' })}</div></div>`}
          <div class="panel">
            <div class="panel-head"><h2>校正后显著</h2><span class="meta">q &lt; 0.05</span></div>
            <div class="panel-body" style="display:grid;gap:8px">
              ${
                significant.length
                  ? significant
                      .slice(0, 4)
                      .map(
                        (item) => `<div style="display:grid;grid-template-columns:1fr auto;gap:4px;border-bottom:1px dashed var(--rule);padding-bottom:6px">
                          <div><b>${esc(item.metric_name)}</b> <span class="mono muted">${esc(item.experiment_code)} · ${esc(item.variant_code)}</span></div>
                          <div style="text-align:right">${badge(verdictTone(item.verdict), item.verdict_label)}<div class="mono">${signedPct(item.lift, 1)} · q=${fmtP(item.q_value)}</div></div>
                        </div>`,
                      )
                      .join('')
                  : emptyState({ title: '还没有显著指标', hint: '去「指标检验」跑一次。' })
              }
            </div>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>近 7 天分流样本</h2><span class="meta">samples / day</span></div>
          <div class="panel-body">
            ${trendChart(data.trend.length ? data.trend : [])}
            <p class="muted" style="margin:8px 0 0">本周合计 ${num(data.sample_total)} 份样本，落在 ${num(data.assignment_rows)} 个 变体×渠道×日期×指标 格子里。</p>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>决策与分流分布</h2><span class="meta">verdict / srm</span></div>
          <div class="panel-body" style="display:grid;gap:12px">
            ${barList(
              data.verdict_breakdown.map((item) => ({ ...item, tone: item.key === 'stop' ? 'danger' : item.key === 'ship' ? 'ok' : '' })),
            )}
            ${barList(data.srm_breakdown.map((item) => ({ ...item, tone: item.key === 'srm' ? 'danger' : 'ok' })))}
            <div class="note">决策只认 BH 校正后的 q 值，不认裸 p 值</div>
          </div>
        </section>
      </div>
    `;

    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = experiments.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) location.hash = `#/experiments?focus=${item.id}`;
      });
    });
  },
};

export default overviewPage;
