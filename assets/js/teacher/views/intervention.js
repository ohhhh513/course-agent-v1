'use strict';

  /* ================================================================
     视图 5 · 教学干预与策略（开发中 · 不调用业务接口）
     ================================================================ */
  const Intervention = {
    tab: 'list',
    render() {
      const el = U.$('#view-intervention');
      el.innerHTML = `
      <div class="card" style="min-height:calc(100vh - var(--topbar-h) - 44px)">
        <div class="card__head">
          <h3>${icon('route')} 教学干预与策略</h3>
          <span class="badge badge--warn">开发中</span>
        </div>
        <div class="card__body">
          <div class="empty" style="padding:60px 24px;text-align:center">
            <div style="font-size:42px;margin-bottom:12px">🚧</div>
            <b style="font-size:16px;display:block;margin-bottom:8px">教学干预与策略 · 正在开发</b>
            <p style="color:var(--text-3);font-size:13px;line-height:1.8;max-width:440px;margin:0 auto">
              该模块将结合学情与预警，推送可执行的干预策略并量化效果。<br>
              当前版本暂不展示干预建议，避免使用演示数据。
            </p>
            <p class="fz-12 t-dim" style="margin-top:18px">
              已开放的真实能力：课程目录与资源、知识图谱编排、题库与 AI 出题、学情分析报告
            </p>
          </div>
        </div>
      </div>`;
    },
  };
