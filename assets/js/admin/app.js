/* ==========================================================================
   管理员端 · 应用引导（登录守卫 / 主题 / 侧栏图标 / 路由启动）
   必须最后加载：视图模块（views/*.js）先完成 Router.register，这里再启动路由。
   ========================================================================== */
(function () {
  'use strict';
  if (window.Auth && !Auth.requireAuth('admin')) return;

  Theme.init();
  // 侧栏图标注入
  U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', navIcon(n.dataset.icon || 'users')));
  Auth.applyUserBadge();
  if (document.getElementById('tbUid')) {
    document.getElementById('tbUid').textContent = '管理员 · admin';
  }

  initTopbar('index.html?role=admin');

  // 登录后默认打开智能助手；带页面锚点时仍支持直达对应功能。
  Router.init('assistant');
})();
