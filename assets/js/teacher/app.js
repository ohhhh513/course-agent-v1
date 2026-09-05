/* ==========================================================================
   教师端 · 应用引导（全局状态 / 路由守卫 / 顶栏 / 班级切换）
   必须最先加载。state / classSel / ViewFns 为全局，供各视图模块直接引用。
   ========================================================================== */
'use strict';

/* —— 全局共享状态（供各视图模块引用） —— */
const classSel = U.$('#classSel');
const state = { classId: classSel.value || 'CL2301' };

/* —— 视图重渲染注册表（班级切换时复用） —— */
const ViewFns = {
  dashboard: () => Dash.render(),
  monitor: () => Monitor.render(),
  analysis: () => Analysis.render(),
  question: () => Question.render(),
  intervention: () => Intervention.render(),
  report: () => Report.render(),
  resource: () => TeacherResource.render(),
};

/* —— 路由守卫（需提前返回，独立 IIFE） —— */
(function () {
  if (window.Auth && !Auth.requireAuth('teacher')) return;
  window.__teacherAuthed = true;
  Theme.init();
  U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', icon(n.dataset.icon, 'nav-item__icon')));
  initTopbar();
})();

/* —— 班级切换 / 顶栏更新 —— */
  // 班级下拉：从真实后端拉取当前教师所带班级（不再使用 MOCK，确保数据来自数据库）
  API.teacher.classes().then(r => {
    const list = Array.isArray(r) ? r : ((r && r.list) || []);
    classSel.innerHTML = '';
    list.forEach(c => {
      const o = document.createElement('option');
      o.value = c.classId; o.textContent = c.name || c.classId; classSel.appendChild(o);
    });
    if (!list.length) {
      const o = document.createElement('option');
      o.value = ''; o.textContent = '暂无班级'; classSel.appendChild(o);
      return;
    }
    state.classId = list[0].classId;
    classSel.value = state.classId;
    API.teacher.dashboard({ classId: state.classId }).then(d => {
      const t = U.$('#updateTag');
      if (t && d.classOverview) t.textContent = '学情更新于 ' + d.classOverview.updatedAt;
    });
    API.intervention.list({ classId: state.classId }).then(rr => {
      const pending = (rr.list || []).filter(i => i.status === 'pending').length;
      const b = U.$('#navIvBadge');
      if (!b) return;
      if (pending) { b.textContent = pending; b.style.display = ''; }
      else { b.style.display = 'none'; }
    });
  }).catch(() => {});

  classSel.addEventListener('change', () => {
    state.classId = classSel.value;
    Toast.info('已切换班级', classSel.options[classSel.selectedIndex].text);
    if (ViewFns[Router.current]) ViewFns[Router.current]();
  });
