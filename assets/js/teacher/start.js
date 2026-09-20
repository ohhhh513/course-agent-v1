'use strict';
/* 教师端 · 路由启动：仅在校验通过后才初始化默认视图 */
if (window.__teacherAuthed) {
  // 等课程上下文（GET /course/my）就绪再挂载首屏：
  // 首次登录时 localStorage 里还没有 activeCourseId，若先挂载视图，
  // 驾驶舱等视图会误显示「尚未创建或选择课程」，刷新前不会自愈。
  const ready = window.__courseReady;
  if (ready && typeof ready.then === 'function') {
    ready.catch(() => {}).then(() => Router.init('dashboard'));
  } else {
    Router.init('dashboard');
  }
}
