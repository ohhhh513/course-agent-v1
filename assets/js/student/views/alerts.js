'use strict';

  /* ================================================================
     视图 7 · 预警与提醒中心（开发中 · 不调用业务接口）
     ================================================================ */
  const Alerts = {
    level: 'all',
    render() {
      const el = U.$('#view-alerts');
      el.innerHTML = `
      <div class="card" style="min-height:calc(100vh - var(--topbar-h) - 44px)">
        <div class="card__head">
          <h3>${icon('bell')} 预警与提醒</h3>
          <span class="badge badge--warn">开发中</span>
        </div>
        <div class="card__body">
          <div class="empty" style="padding:60px 24px;text-align:center">
            <div style="font-size:42px;margin-bottom:12px">🚧</div>
            <b style="font-size:16px;display:block;margin-bottom:8px">预警与提醒 · 正在开发</b>
            <p style="color:var(--text-3);font-size:13px;line-height:1.8;max-width:420px;margin:0 auto">
              该模块将基于真实练习与学习进度生成学情预警。<br>
              当前版本暂不展示预警数据，避免与演示逻辑混淆。
            </p>
            <p class="fz-12 t-dim" style="margin-top:18px">
              已开放的真实能力：学习资源、智能练习、AI 答疑、我的学情、课程图谱
            </p>
          </div>
        </div>
      </div>`;
    },
    load() { /* 开发中：不拉接口 */ },
  };

  // 注册路由：学生端侧栏「预警与提醒」与驾驶舱待办「去处理」都指向 alerts，
  // 未注册会导致 Router.go('alerts') 静默失败（点击无任何反应）。
  Router.register('alerts', { title: '预警与提醒', mount: () => Alerts.render() });
