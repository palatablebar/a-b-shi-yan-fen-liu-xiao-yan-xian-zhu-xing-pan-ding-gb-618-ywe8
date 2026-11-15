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
  num,
  pct,
  signedPct,
  table,
  toast,
} from '../ui.js';

const state = { verdict: '', q: '' };

function exportButtons(role) {
  if (!can(role, 'export:read')) {
    return '<span class="mono muted">只读角色不能导出（服务端 403）</span>';
  }
  return `<div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn sm ghost" data-export="experiments">实验台账 CSV</button>
    <button class="btn sm ghost" data-export="assignments">分流样本 CSV</button>
    <button class="btn sm ghost" data-export="metrics">指标检验 CSV</button>
    <button class="btn sm ghost" data-export="decisions">决策清单 CSV</button>
  </div>`;
}

function openDecision(view, ctx, experiments, pending) {
  if (!pending.length) {
    toast('所有实验都已出决策');
    return;
  }
  const first = pending[0];
  const { root, close } = drawer({
    title: '出决策',
    subtitle: `${first.experiment.code} · ${first.primary.metric_name || '主指标'} q=${fmtP(first.primary.q_value)}`,
    body: `<form id="decision-form" style="display:grid;gap:12px">
      ${field({
        label: '实验（仅列未决策）',
        name: 'experiment_id',
        options: pending.map((item) => ({ value: item.experiment.id, label: `${item.experiment.code} · ${item.experiment.name}` })),
      })}
      ${field({
        label: '结论',
        name: 'verdict',
        value: first.suggested,
        options: Object.entries(ENUMS.verdict).map(([value, label]) => ({ value, label })),
      })}
      ${field({
        label: '理由（写进会议纪要）',
        name: 'rationale',
        placeholder: '主指标 lift 10.9%，BH 校正后 q=0.044 < 0.05，样本量已过功效线，上线。',
      })}
      <div class="form-error" id="decision-error"></div>
      <button class="btn accent" type="submit">写入决策</button>
    </form>
    <div class="note" style="margin-top:10px">同一实验只能有一条决策（重复提交返回 409）</div>`,
  });
  const form = root.querySelector('#decision-form');
  const syncSuggestion = () => {
    const picked = pending.find((item) => String(item.experiment.id) === String(form.experiment_id.value));
    if (!picked) return;
    form.verdict.value = picked.suggested;
    form.rationale.value = picked.rationale;
  };
  form.experiment_id.addEventListener('change', syncSuggestion);
  form.rationale.value = first.rationale;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorNode = root.querySelector('#decision-error');
    try {
      await api.post(`/api/experiments/${form.experiment_id.value}/decisions`, {
        verdict: form.verdict.value,
        rationale: form.rationale.value.trim(),
      });
      toast('决策已写入');
      close();
      await decisionsPage.render(view, ctx);
    } catch (err) {
      errorNode.textContent = err.code === 'CONFLICT' ? '这个实验已经有决策了（409）' : errorMessage(err);
    }
  });
}

export const decisionsPage = {
  async render(view, ctx) {
    let decisions;
    let experiments;
    let audit = null;
    try {
      const tasks = [
        api.get('/api/decisions', { limit: 50 }),
        api.get('/api/experiments', { limit: 50 }),
      ];
      if (can(ctx.user.role, 'audit:read')) tasks.push(api.get('/api/audit', { limit: 20 }));
      const [decisionData, experimentData, auditData] = await Promise.all(tasks);
      decisions = decisionData;
      experiments = experimentData;
      audit = auditData || null;
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => decisionsPage.render(view, ctx));
      return;
    }

    const decidedIds = new Set(decisions.items.map((item) => String(item.experiment_id)));
    const pendingExperiments = experiments.items.filter((item) => !decidedIds.has(String(item.id)));
    const details = await Promise.all(
      pendingExperiments.map((item) => api.get(`/api/experiments/${item.id}`).catch(() => item)),
    );
    const pending = details
      .map((experiment) => {
        const primary = (experiment.metrics || []).find((metric) => metric.is_primary) || {};
        const suggested = primary.significant ? (primary.lift >= 0 ? 'ship' : 'stop') : 'continue';
        const rationale = primary.metric_name
          ? `${primary.metric_name}：lift ${signedPct(primary.lift, 1)}，p=${fmtP(primary.p_value)}，q=${fmtP(primary.q_value)}；${
              primary.significant ? '校正后显著' : '校正后不显著，样本或效应不足'
            }，建议${ENUMS.verdict[suggested]}。`
          : '还没有检验结果，建议继续观察。';
        return { experiment, primary, suggested, rationale };
      });

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>决策与导出</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">已决策 ${decisions.total} / ${experiments.total}</span>
            ${can(ctx.user.role, 'decision:write') ? '<button class="btn sm accent" id="new-decision">出决策</button>' : '<span class="mono muted">决策需实验负责人</span>'}
          </div>
        </div>
        <div class="panel-body">
          ${filterBar({
            id: 'decision-filters',
            fields: [
              field({
                label: '结论',
                name: 'verdict',
                value: state.verdict,
                options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.verdict).map(([value, label]) => ({ value, label }))],
              }),
              field({ label: '搜索理由', name: 'q', value: state.q, placeholder: '理由 / 决策人', grow: true }),
            ],
          })}
        </div>
        <div class="panel-body" style="padding-top:0">${exportButtons(ctx.user.role)}</div>
        ${table({
          rows: decisions.items.filter(
            (row) =>
              (!state.verdict || row.verdict === state.verdict) &&
              (!state.q || `${row.rationale}${row.decided_by}${row.experiment_code}`.includes(state.q)),
          ),
          columns: [
            { key: 'experiment_code', label: '实验', className: 'mono nowrap' },
            { key: 'experiment_name', label: '名称' },
            { key: 'verdict', label: '结论', render: (row) => badge(verdictTone(row.verdict), row.verdict_label) },
            { key: 'rationale', label: '理由', render: (row) => `<span>${esc(row.rationale)}</span>` },
            { key: 'decided_by', label: '决策人', className: 'mono nowrap' },
            { key: 'decided_at', label: '时间', render: (row) => fmtTime(row.decided_at) },
          ],
          empty: { title: '还没有决策', hint: '选一个已跑完检验的实验出结论。' },
        })}
      </section>

      ${
        pending.length
          ? `<div class="grid-2">
              ${pending
                .slice(0, 2)
                .map(
                  (item) => `<section class="panel">
                    <div class="panel-head">
                      <h2>${esc(item.experiment.code)} 待决策</h2>
                      ${badge(verdictTone(item.suggested), `建议 ${ENUMS.verdict[item.suggested]}`)}
                    </div>
                    <div class="panel-body" style="display:grid;gap:6px">
                      <div><b>${esc(item.experiment.name)}</b></div>
                      <div class="mono muted">${esc(item.experiment.primary_metric_label)} · SRM ${esc(item.experiment.srm.status_label)} · p=${fmtP(
                        item.experiment.srm.p_value,
                      )}</div>
                      ${item.primary.metric_name
                        ? `<div class="checkline">
                            <div class="item"><span class="k">lift</span><span class="v">${signedPct(item.primary.lift, 1)}</span></div>
                            <div class="item"><span class="k">p</span><span class="v">${fmtP(item.primary.p_value)}</span></div>
                            <div class="item"><span class="k">q</span><span class="v ${item.primary.significant ? 'pass' : 'fail'}">${fmtP(item.primary.q_value)}</span></div>
                          </div>`
                        : '<p class="muted">还没有检验结果。</p>'}
                      <p class="muted" style="margin:0">${esc(item.rationale)}</p>
                    </div>
                  </section>`,
                )
                .join('')}
            </div>`
          : ''
      }

      ${
        audit
          ? `<section class="panel">
              <div class="panel-head"><h2>审计日志</h2><span class="meta">${audit.total} 条 · 最近 ${audit.items.length} 条</span></div>
              ${table({
                rows: audit.items,
                columns: [
                  { key: 'created_at', label: '时间', render: (row) => fmtTime(row.created_at) },
                  { key: 'actor_email', label: '操作人', className: 'mono' },
                  { key: 'actor_role', label: '角色' },
                  { key: 'action_label', label: '动作' },
                  { key: 'entity', label: '对象' },
                  { key: 'layer', label: '层', render: (row) => badge('', row.layer) },
                  { key: 'detail', label: '详情', render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>` },
                ],
                empty: { title: '没有审计记录', hint: '登录、登记、校验、导出都会留痕。' },
              })}
            </section>`
          : ''
      }
    `;

    const filters = view.querySelector('#decision-filters');
    filters?.addEventListener('change', () => {
      state.verdict = filters.querySelector('[name=verdict]').value;
      state.q = filters.querySelector('[name=q]').value.trim();
      decisionsPage.render(view, ctx);
    });
    view.querySelector('#new-decision')?.addEventListener('click', () => openDecision(view, ctx, experiments.items, pending));
    view.querySelectorAll('[data-export]').forEach((button) => {
      button.addEventListener('click', async () => {
        const kind = button.dataset.export;
        button.disabled = true;
        try {
          await api.download(`/api/exports/${kind}.csv`, `${kind}.csv`);
          toast(`已下载 ${kind}.csv`);
        } catch (err) {
          toast(errorMessage(err), 'err');
        } finally {
          button.disabled = false;
        }
      });
    });
  },
};

export default decisionsPage;
