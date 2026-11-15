/**
 * 投放段（traffic segment）共享 UI：当前生效内容横幅、段时间线、登记投放内容抽屉。
 * 每套结论都必须能对应到具体投放内容，所以这套组件在样本/指标/决策/详情多处复用。
 */
import { api } from './api.js';
import { ENUMS, can, segmentTone } from './config.js';
import { badge, drawer, errorMessage, esc, field, fmtTime, toast } from './ui.js';

/** 当前生效投放段横幅：明确「这套数据/结论对应哪一次实际投放内容」。 */
export function segmentBanner(experiment, { compact = false } = {}) {
  const seg = experiment && experiment.active_segment;
  if (!seg) {
    return `<section class="panel segment-banner">
      <div class="panel-body segment-empty">
        <b>还没有生效投放段</b>
        <span class="muted">先登记实际投放内容并完成投放段切换，样本与结论才会绑定到具体内容。</span>
      </div>
    </section>`;
  }
  const c = seg.completeness || {};
  return `<section class="panel segment-banner ${seg.stale ? 'is-stale' : ''}">
    <div class="panel-body segment-banner-body">
      <div class="segment-id">
        <span class="eyebrow">当前生效投放段</span>
        <b class="mono">${esc(seg.segment_code)}</b>
        ${badge(segmentTone(seg.status), ENUMS.segmentStatus[seg.status] || seg.status)}
        ${seg.stale ? badge('srm', '内容已更新·结论失效') : ''}
      </div>
      <div class="segment-content">
        <div class="segment-ref mono" title="${esc(seg.content_hash || '')}">${esc(seg.content_ref || seg.content_summary || '—')}</div>
        ${compact ? '' : `<div class="muted">${esc(seg.content_summary || '')}</div>`}
      </div>
      <div class="segment-complete">
        ${completenessDots(c)}
        <span class="tiny muted">激活 ${fmtTime(seg.activated_at) || '—'}</span>
      </div>
    </div>
    ${
      seg.stale
        ? `<div class="panel-foot segment-warn">上游投放内容已变化：本段仍是当前数据依据，但上线结论已失效；请等新投放段完整切换后再决策。</div>`
        : ''
    }
  </section>`;
}

export function completenessDots(c = {}) {
  const items = [
    ['samples_ready', '样本'],
    ['srm_ready', '分流判断'],
    ['metrics_ready', '全部指标'],
  ];
  return `<div class="completeness">${items
    .map(([key, label]) => `<span class="dot ${c[key] ? 'on' : 'off'}">${c[key] ? '✓' : '○'} ${label}</span>`)
    .join('')}</div>`;
}

/** 段时间线：每个投放段一行，标注内容、状态、完整性与是否当前生效。 */
export function segmentTimeline(segments) {
  if (!segments || !segments.length) return '';
  return `<section class="panel">
    <div class="panel-head"><h2>投放段时间线</h2><span class="meta">${segments.length} 段 · 内容与结论绑定</span></div>
    <div class="panel-body" style="padding:0">
      <div class="table-wrap">
        <table class="data segment-table">
          <thead><tr><th>投放段</th><th>实际投放内容</th><th>状态</th><th>完整性</th><th>激活/顶替时间</th></tr></thead>
          <tbody>
            ${segments
              .map((seg) => {
                const c = seg.completeness || {};
                return `<tr class="${seg.is_active ? 'is-active-row' : ''}">
                  <td class="mono nowrap"><b>${esc(seg.segment_code)}</b>${seg.is_active ? ' <span class="badge ok">当前</span>' : ''}</td>
                  <td><b>${esc(seg.content_ref || '—')}</b><div class="mono muted tiny">${esc((seg.content_hash || '').slice(0, 16))}…</div></td>
                  <td>${badge(segmentTone(seg.status), ENUMS.segmentStatus[seg.status] || seg.status)}${seg.stale ? badge('srm', '结论失效') : ''}</td>
                  <td>${completenessDots(c)}${c.ready_reason ? `<div class="tiny muted">${esc(c.ready_reason)}</div>` : ''}</td>
                  <td class="nowrap tiny muted">${fmtTime(seg.activated_at) || '—'}${seg.superseded_at ? `<br>顶替 ${fmtTime(seg.superseded_at)}` : ''}</td>
                </tr>`;
              })
              .join('')}
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel-foot"><span class="note">同一投放段的样本、分流判断、全部指标与上线结论一致后才开放决策；换内容即开新段，旧结论立即失效。</span></div>
  </section>`;
}

/** 登记实际投放内容抽屉（admin）。onDone 在成功后回调刷新页面。 */
export function openRegisterSegment(experimentId, role, onDone) {
  if (!can(role, 'segment:write')) {
    toast('仅实验负责人可登记投放内容', 'err');
    return;
  }
  const { root, close } = drawer({
    title: '登记实际投放内容',
    subtitle: '同一内容重复提交不重复建段；内容变化会立即作废旧上线结论',
    body: `<form id="segment-form" style="display:grid;gap:12px">
      ${field({ label: '内容版本引用（页面版本 / 物料号）', name: 'content_ref', placeholder: 'page-v2 / 结算页立减标签-20260622', attrs: 'minlength="2" required' })}
      ${field({
        label: '内容摘要（人读，选填）',
        name: 'content_summary',
        placeholder: '按钮文案改为「去结算」，主色芥末黄',
      })}
      <label class="eyebrow" for="content_payload">内容指纹载荷（JSON，参与判变化；字段顺序不影响指纹）</label>
      <textarea id="content_payload" name="content_payload" rows="6" class="input"
        placeholder='{"page":"checkout","button":"去结算","color":"mustard","assets":["btn_a.png"]}'>{}</textarea>
      <div class="form-error" id="segment-error"></div>
      <button class="btn accent" type="submit">登记并开新投放段</button>
    </form>
    <div class="note" style="margin-top:10px">新段先进入「构建中」，样本/分流判断/全部指标齐备并切换成功后，才会成为决策依据。</div>`,
  });
  root.querySelector('#segment-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const errorNode = root.querySelector('#segment-error');
    let payload = {};
    const raw = form.content_payload.value.trim() || '{}';
    try {
      payload = JSON.parse(raw);
    } catch {
      errorNode.textContent = '内容指纹载荷必须是合法 JSON';
      return;
    }
    try {
      const seg = await api.post(`/api/experiments/${experimentId}/segments`, {
        content_ref: form.content_ref.value.trim(),
        content_summary: form.content_summary.value.trim() || null,
        content_payload: payload,
      });
      toast(`投放段 ${seg.segment_code} 已${seg.status === 'building' ? '建立（构建中）' : '复用'}`);
      close();
      onDone && onDone(seg);
    } catch (err) {
      errorNode.textContent = errorMessage(err);
    }
  });
}

/** 投放段切换（cutover）按钮逻辑：完整性不足会被服务端拒绝并保留旧版结果。 */
export async function cutoverSegment(experimentId, segmentId) {
  return api.post(`/api/experiments/${experimentId}/segments/cutover`, { segment_id: segmentId || null });
}
