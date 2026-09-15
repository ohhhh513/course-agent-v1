/* ==========================================================================
   教师端 · 应用引导（全局状态 / 路由守卫 / 顶栏 / 课程切换）
   必须最先加载。state / courseSel / ViewFns 为全局，供各视图模块直接引用。

   多课程（Step 6）：
   - 顶栏下拉 = 真实课程切换器，数据源 GET /course/my（user_courses 成员关系）；
   - 切换即 API.setActiveCourse(courseId)，此后所有请求自动携带 X-Course-Id 头，
     已接入课程上下文的模块（资源中心/题库/驾驶舱等）立即按课程隔离；
   - state.classId 为旧学情接口（班级维度演示快照）保留的历史状态，
     与课程切换无关，后续随班级体系一起演进。
   ========================================================================== */
'use strict';

/* —— 全局共享状态（供各视图模块引用） —— */
const courseSel = U.$('#courseSel');
const state = { classId: 'CL2301' };   // 班级维度：旧学情接口暂用，随班级体系后续演进

/* —— 视图重渲染注册表（课程切换时复用） —— */
const ViewFns = {
  dashboard: () => Dash.render(),
  monitor: () => Monitor.render(),
  analysis: () => Analysis.render(),
  question: () => Question.render(),
  intervention: () => Intervention.render(),
  report: () => Report.render(),
  resource: () => TeacherResource.render(),
  structure: () => TeacherStructure.render(),
};

/* —— 路由守卫（需提前返回，独立 IIFE） —— */
(function () {
  if (window.Auth && !Auth.requireAuth('teacher')) return;
  window.__teacherAuthed = true;
  Theme.init();
  U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', icon(n.dataset.icon, 'nav-item__icon')));
  initTopbar();
})();

/* —— 课程切换器：数据源 = 我的课程 —— */
function refreshCourseSel(preferId) {
  API.course.my().then(list => {
    const courses = Array.isArray(list) ? list : [];
    courseSel.innerHTML = '';
    if (!courses.length) {
      const o = document.createElement('option');
      o.value = ''; o.textContent = '暂无课程 · 点 + 新建';
      courseSel.appendChild(o);
      return;
    }
    courses.forEach(c => {
      const o = document.createElement('option');
      o.value = c.courseId;
      o.textContent = c.name + (c.role === 'teacher' ? '（我讲授）' : '');
      courseSel.appendChild(o);
    });
    // 恢复上次选择；上次课程已不在列表（被清理/退出）时回落到第一门
    const cur = API.config.activeCourseId;
    const target = preferId || (courses.some(c => c.courseId === cur) ? cur : courses[0].courseId);
    API.setActiveCourse(target);
    courseSel.value = target;
  }).catch(() => {});
}
refreshCourseSel();

/* —— 新建课程（弹窗：创建后展示邀请码） —— */
(function () {
  const btn = U.$('#newCourseBtn');
  if (!btn) return;
  btn.innerHTML = icon('plus');
  btn.title = '新建课程';
  btn.addEventListener('click', () => {
    Modal.open({
      title: '新建课程',
      body: `
        <div class="stack" style="gap:14px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">课程名称</span><input class="input" id="ncName" placeholder="如：Python 程序设计"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学期（可选）</span><input class="input" id="ncTerm" placeholder="如：2026 秋季"></label>
          <p class="fz-12 t-dim">创建后生成邀请码，学生凭码加入；课程初始为空课，章节、知识点与资源由你逐步搭建。</p>
        </div>`,
      footer: `<button class="btn btn--primary" id="ncGo" type="button">创建</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#ncGo', ov).addEventListener('click', () => {
          const name = U.$('#ncName', ov).value.trim();
          if (!name) { Toast.warn('请输入课程名称'); return; }
          API.teacher.createCourse({ name, term: U.$('#ncTerm', ov).value.trim() }).then(r => {
            close();
            Modal.open({
              title: '课程已创建',
              body: `<div class="stack" style="gap:8px;text-align:center;padding:10px 0">
                <div class="fz-14 fw-6">${U.esc(r.name)}</div>
                <div class="fz-12 t-dim">把邀请码分享给学生，他们凭码加入：</div>
                <div style="font-size:26px;font-weight:700;letter-spacing:4px;color:var(--brand)">${U.esc(r.inviteCode)}</div>
                <div class="fz-11 t-dim">课程 ID：${U.esc(r.courseId)}</div>
              </div>`,
              footer: `<button class="btn btn--primary" data-close>我知道了</button>`,
            });
            refreshCourseSel(r.courseId);
            if (ViewFns[Router.current]) ViewFns[Router.current]();
          }).catch(err => Toast.error('创建失败', err && err.message || ''));
        });
      }
    });
  });
})();

/* —— 切换课程：更新请求上下文并重绘当前视图 —— */
courseSel.addEventListener('change', () => {
  if (!courseSel.value) return;
  API.setActiveCourse(courseSel.value);
  Toast.info('已切换课程', courseSel.options[courseSel.selectedIndex].text);
  if (ViewFns[Router.current]) ViewFns[Router.current]();
});
