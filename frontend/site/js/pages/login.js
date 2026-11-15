import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-brief">
          <div class="eyebrow">${esc(BRAND.edition)} · 内部</div>
          <h1>分流没验，<br /><em>结论先别写</em></h1>
          <p class="tagline">${esc(BRAND.loginLead)}</p>
          <div class="brief-points">
            ${BRAND.loginPoints.map(([no, text]) => `<div class="brief-point"><i>${esc(no)}</i><span>${esc(text)}</span></div>`).join('')}
          </div>
          <div class="login-meta">
            <span>记录本编号 ${esc(BRAND.sheetNo)} · 受控文档</span>
            <span>每周 8 个实验 · 1 App × 4 渠道 · 6 个指标口径</span>
          </div>
        </section>

        <section class="login-form-wrap">
          <form class="login-sheet" id="login-form" novalidate>
            <div class="sheet-head">
              <div>
                <h2>实验登记页</h2>
                <div class="sub">Lab Sheet ${esc(BRAND.sheetNo)} · ${esc(BRAND.org)}</div>
              </div>
              <span class="stamp">受控 · CONTROLLED</span>
            </div>
            <div class="login-card">
              <div class="sub">登记人账号与口令。三个演示账号权限不同：实验负责人可建实验/跑检验/出决策，数据分析师可看与导出，只读账号只看。</div>
              <div class="field">
                <label for="email">登记人邮箱</label>
                <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
              </div>
              <div class="field">
                <label for="password">口令</label>
                <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
              </div>
              <div class="form-error" id="login-error" role="alert"></div>
              <button class="btn accent" id="login-submit" type="submit">翻开记录本</button>
              <div class="login-hint">
                演示口令统一 <code>Demo@2026</code>：<br />
                <code>admin@${esc(BRAND.short)}.io</code> 实验负责人 · <code>analyst@${esc(BRAND.short)}.io</code> 数据分析师 ·
                <code>viewer@${esc(BRAND.short)}.io</code> 只读
              </div>
              <div class="note">分流校验从 exp-2603 那条 χ²=12.7 的记录开始看</div>
            </div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '正在核对…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`登记人：${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或口令不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '翻开记录本';
      }
    });
  },
};

export default loginPage;
