/**
 * 品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README 列出全部出现位置。
 * 视觉方向：实验室记录本 —— 石墨灰 + 芥末黄 + 网格纸 + 手写批注。
 */
export const BRAND = {
  short: 'abcheck',
  title: 'A/B 实验分流校验与显著性判定',
  org: '橙野 App · 增长实验组',
  edition: 'LAB NOTEBOOK · 2026 Q2',
  sheetNo: 'A-2607',
  subtitle: '分流先验证，指标再检验，结论才敢写进决策会纪要',
  loginLead: '每周 8 个实验，别再拿 SQL 和 Excel 各算一遍。分流是否均衡、功效够不够、多指标校正后还剩什么，本子上一次写清。',
  loginPoints: [
    ['01', '登记实验时就把基准转化率与目标最小效应写下来，样本量按公式倒推。'],
    ['02', '分流样本按 变体 × 渠道 × 日期 落库，χ² 与 p 值当场出，SRM 告警进总览。'],
    ['03', '每个指标都给 lift、Wald 置信区间、Bonferroni 与 BH 两套 q 值，结论只认校正后的。'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/experiments', no: '02', label: '实验登记', permission: 'experiment:read' },
  { to: '#/assignments', no: '03', label: '样本与分流', permission: 'assignment:read' },
  { to: '#/metrics', no: '04', label: '指标检验', permission: 'metric:read' },
  { to: '#/decisions', no: '05', label: '决策与导出', permission: 'decision:read' },
];

export const ROLE_LABELS = {
  admin: '实验负责人',
  analyst: '数据分析师',
  viewer: '业务只读',
};

export const PERMISSIONS = {
  admin: [
    'overview:read',
    'experiment:read', 'experiment:write',
    'assignment:read', 'assignment:write',
    'srm:read', 'srm:run',
    'metric:read', 'metric:run',
    'decision:read', 'decision:write',
    'export:read', 'audit:read',
  ],
  analyst: ['overview:read', 'experiment:read', 'assignment:read', 'srm:read', 'metric:read', 'decision:read', 'export:read'],
  viewer: ['overview:read', 'experiment:read', 'assignment:read', 'srm:read', 'metric:read', 'decision:read'],
};

export const ENUMS = {
  experimentStatus: {
    draft: '草稿',
    running: '运行中',
    paused: '已暂停',
    finished: '已结束',
    archived: '已归档',
  },
  verdict: {
    ship: '上线',
    continue: '继续观察',
    stop: '停止',
  },
  srm: {
    balanced: '分流均衡',
    srm: 'SRM 告警',
    unknown: '未校验',
  },
  correction: {
    bh: 'BH-FDR',
    bonferroni: 'Bonferroni',
  },
  metric: {
    cart_rate: '加购转化率',
    order_rate: '下单转化率',
    retention_d1: '次日留存',
    click_rate: '点击率',
    search_success: '搜索成功率',
  },
  channel: {
    feed: '信息流',
    push: '推送',
    search: '搜索',
    mp: '小程序',
  },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function statusTone(status) {
  return (
    { running: 'ok', paused: 'warn', draft: 'pending', finished: 'info', archived: '' }[status] || ''
  );
}

export function verdictTone(verdict) {
  return { ship: 'ship', continue: 'continue', stop: 'stop' }[verdict] || 'info';
}

export function srmTone(status) {
  return { srm: 'srm', balanced: 'ok', unknown: 'pending' }[status] || 'info';
}
