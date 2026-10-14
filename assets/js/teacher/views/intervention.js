'use strict';

  /* ================================================================
     视图 5 · 教学干预与策略 —— 前端暂时隐藏（2026-09-24）

     该模块尚未完善，现按要求在前端隐藏，涉及三处（都已同步改完）：
       1) teacher.html 侧栏不再有入口（分组「学情产出」现只含学情分析报告）
       2) teacher/app.js 的 ViewFns 不再映射 intervention
       3) 预警详情弹窗里的「生成干预」按钮已移除（teacher/views/monitor.js）
     后端 /intervention/* 与 /report/* 的真实实现保持不动，随时可重新开放。

     本文件保留同名路由做兜底：直接输 #intervention、旧书签、
     或将来别处误调 Router.go('intervention') 时，提示后回到教学驾驶舱，
     不会再落到空白页或半成品页。

     重新开放步骤：把下面的 mount 换回真实渲染（见 git 历史中本文件的上一版），
     并在 teacher.html 侧栏加回导航项：
       <button class="nav-item" data-view="intervention" data-icon="route">
         <span class="nav-item__text">教学干预与策略</span>
       </button>
     ================================================================ */
  Router.register('intervention', {
    title: '教学干预与策略',
    mount: () => {
      Toast.info('该模块暂未开放', '教学干预与策略仍在完善中，已返回教学驾驶舱');
      Router.go('dashboard');
    },
  });
