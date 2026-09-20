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

<<<<<<< Updated upstream
/* —— 班级切换 / 顶栏更新 —— */
  // 班级下拉：从真实后端拉取当前教师所带班级（不再使用 MOCK，确保数据来自数据库）
  API.teacher.classes().then(r => {
    const list = Array.isArray(r) ? r : ((r && r.list) || []);
    classSel.innerHTML = '';
    list.forEach(c => {
=======
/* —— 课程切换器：数据源 = 我的课程 —— */
function refreshCourseSel(preferId) {
  return API.course.my().then(list => {
    const courses = Array.isArray(list) ? list : [];
    courseSel.innerHTML = '';
    if (!courses.length) {
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
=======
}

/* —— 首屏课程上下文 ——
   历史 bug：首次登录时 localStorage 里还没有 activeCourseId，而课程列表是异步取的。
   视图（驾驶舱/学情监测等）先挂载 → 读到空的课程上下文 → 直接渲染「尚未创建或选择课程」，
   且因为 Router 的 mount 只执行一次，刷新前不会自愈；整页刷新后（activeCourseId 已在
   localStorage 中同步可读）又一切正常。这里把课程列表做成 Promise：
     1) start.js 等它 resolve 后再 Router.init（首屏不再抢跑）；
     2) 若视图已经挂载过（例如别的入口先渲染了），课程就绪后补渲染一次当前视图。 */
window.__courseReady = refreshCourseSel();
window.__courseReady.then(() => {
  const key = Router.current;
  if (key && Router.views[key] && Router.views[key]._mounted && ViewFns[key]) ViewFns[key]();
}).catch(() => {});
>>>>>>> Stashed changes

  classSel.addEventListener('change', () => {
    state.classId = classSel.value;
    Toast.info('已切换班级', classSel.options[classSel.selectedIndex].text);
    if (ViewFns[Router.current]) ViewFns[Router.current]();
  });
