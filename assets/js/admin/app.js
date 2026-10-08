/* ==========================================================================
   管理员端 · 应用引导（登录守卫 / 主题 / 侧栏图标 / 路由启动）
   必须最后加载：视图模块（views/*.js）先完成 Router.register，这里再启动路由。
   ========================================================================== */
(function () {
  'use strict';
  if (window.Auth && !Auth.requireAuth('admin')) return;

  Theme.init();
  // 侧栏图标注入
  U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', icon(n.dataset.icon || 'users', 'nav-item__icon')));
  Auth.applyUserBadge();
  if (document.getElementById('tbUid')) {
    document.getElementById('tbUid').textContent = '管理员 · admin';
  }

  initTopbar('index.html?role=admin');

  // 默认落「账号管理」；支持 #assistant 直达智能助手
  Router.init('users');
})();
