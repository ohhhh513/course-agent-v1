'use strict';
/* 学生端 · 路由启动：仅在校验通过后才初始化默认视图 */
if (window.__studentAuthed) {
  // 等课程上下文（GET /course/my）就绪再挂载首屏：
  // 首次登录时 localStorage 里还没有 activeCourseId，若先挂载视图，
  // 各视图会误显示「未加入课程」，且刷新前不会自愈。
  const ready = window.__courseReady;
  if (ready && typeof ready.then === 'function') {
    ready.catch(() => {}).then(() => Router.init('dashboard'));
  } else {
    Router.init('dashboard');
  }
}
