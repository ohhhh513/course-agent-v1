'use strict';

/* 执行仓库登记的界面动作；生成报告是明确请求才允许的业务动作。 */
const AgentUI = (() => {
  const executed = new Set();
  let running = false;
  let catalogue;
  const role = () => String((Auth.currentUser() || {}).role || '');
  const userId = () => String((Auth.currentUser() || {}).userId || '');
  const currentCourse = () => String(API.config.activeCourseId || '');
  const loginId = () => typeof Auth.getSession === 'function' ? String((Auth.getSession() || {}).loginStartedAt || '') : '';
  const load = async () => {
    // 与后端相同的源清单，每次操作读取新版本，部署与源码索引同步。
    const response = await fetch('assets/agent-ui-actions.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('无法加载界面操作入口');
    catalogue = await response.json();
    return catalogue.actions;
  };
  const wait = (test, description, guard = () => true) => new Promise((resolve, reject) => {
    let observer, timer, poll;
    const stop = () => { if (observer) observer.disconnect(); clearTimeout(timer); clearInterval(poll); };
    const check = () => {
      if (!guard()) { stop(); reject(new Error('课程、登录或页面已变化，已取消本次操作')); return; }
      let value;
      try { value = test(); } catch (_) { value = null; }
      if (value) { stop(); resolve(value); }
    };
    observer = new MutationObserver(check);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
    timer = setTimeout(() => { stop(); reject(new Error('未能打开' + description + '，请重试或检查页面加载错误')); }, 15000);
    poll = setInterval(check, 100); // 数据对象赋值不一定产生 DOM mutation。
    check();
  });
  const find = selector => {
    const overlays = Array.from(document.querySelectorAll('.overlay'));
    for (const overlay of overlays.reverse()) {
      const found = overlay.querySelector(selector);
      if (found) return found;
    }
    const root = document.getElementById('view-' + Router.current);
    return (root && root.querySelector(selector)) || document.querySelector(selector);
  };
  const esc = value => CSS.escape(String(value));
  const set = (element, value) => {
    if (element.disabled || element.readOnly) throw new Error('目标字段目前不可编辑');
    if (element.tagName === 'SELECT' && !Array.from(element.options).some(option => option.value === String(value))) {
      throw new Error('目标选项尚未加载或不属于此界面');
    }
    if (element.type === 'checkbox') element.checked = Boolean(value);
    else if ('value' in element) element.value = String(value);
    else throw new Error('此入口需要专用选项处理器');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const click = async (selector, guard) => {
    const element = await wait(() => find(selector), selector, guard);
    if (element.disabled) throw new Error('此入口当前不可用');
    element.click();
    return element;
  };
  const setFile = (input, files) => {
    if (!files.length) return;
    if (!input.multiple && files.length !== 1) throw new Error('此上传入口一次只能使用一个文件');
    const accepted = String(input.accept || '').split(',').filter(Boolean);
    if (accepted.length && files.some(file => !accepted.some(ext => file.name.toLowerCase().endsWith(ext.toLowerCase()) || file.type === ext))) {
      throw new Error('附件格式不适用于此上传入口，请更换文件');
    }
    const transfer = new DataTransfer();
    files.forEach(file => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const tags = async (selector, ids, attribute, guard) => {
    const root = await wait(() => find(selector), '知识点选项', guard);
    await wait(() => root.querySelector(`[${attribute}]`) || root.textContent.includes('暂无知识点'), '知识点加载', guard);
    await wait(() => ids.every(id => root.querySelector(`[${attribute}="${esc(id)}"]`)), '所选知识点', guard);
    root.querySelectorAll(`[${attribute}]`).forEach(button => {
      const selected = button.classList.contains('is-active') || button.classList.contains('on') || button.classList.contains('is-on');
      if (selected !== ids.includes(button.getAttribute(attribute))) button.click();
    });
  };
  const handlers = {
    'course-switch': async (plan, ctx) => {
      const select = await wait(() => find('#courseSel'), '课程选择', ctx.guard);
      ctx.allowCourseChange = true;
      set(select, plan.object.id);
    },
    'student-exam-list': async (plan, ctx) => {
      await click('#pTabs [data-t="exam"]', ctx.guard);
      await wait(() => find('#examPaperList') || find('#examReload'), '试卷列表', ctx.guard);
    },
    'student-exam-latest': async (plan, ctx) => {
      await handlers['student-exam-list'](plan, ctx);
      const data = await API.practice.exams();
      if (!ctx.guard()) return;
      const papers = (data.list || []).filter(paper => paper.lastAttemptId);
      papers.sort((a, b) => String(b.lastAttemptAt || '').localeCompare(String(a.lastAttemptAt || '')));
      if (!papers.length) throw new Error('还没有已完成的试卷，无法打开作答详情');
      await StudentExams.viewResult(papers[0].lastAttemptId);
      await wait(() => find('#examBackList'), '作答详情', ctx.guard);
    },
    'teacher-exam-list': async (plan, ctx) => {
      await click('#qTabs [data-t="exam"]', ctx.guard);
      await wait(() => find('#examCreate') || find('#examRetry'), '试卷列表', ctx.guard);
    },
    'practice-mode': async (plan, ctx) => {
      await wait(() => find('#pTabs [data-t="quiz"]'), '练习页签', ctx.guard);
      if (Practice.tab !== 'quiz') await click('#pTabs [data-t="quiz"]', ctx.guard);
      const mode = plan.values.mode || plan.target.split('.').pop();
      const card = await wait(() => find(`#modeGrid [data-mode="${esc(mode)}"]`), '练习模式', ctx.guard);
      if (Practice.activeMode !== mode) card.click();
      await wait(() => find('#rsContinue') || find('#qBack') || find('#modePanel [data-kp]') || find('#modePanel .callout--warn'), '练习内容', ctx.guard);
      // 继续已有错题进度只打开题目，不选择答案；绝不自动开始一份覆盖存档的新练习。
      if (mode === 'wrong' && plan.target !== 'student.practice.resume' && plan.auto && find('#rsContinue')) await click('#rsContinue', ctx.guard);
    },
    'practice-resume': async (plan, ctx) => {
      plan.values.mode = plan.values.mode || 'order';
      await handlers['practice-mode'](plan, ctx);
      await click('#rsContinue', ctx.guard);
    },
    'practice-chapter': async (plan, ctx) => {
      await handlers['practice-mode']({ ...plan, values: { mode: 'order' } }, ctx);
      if (find('#rsContinue')) throw new Error('有未完成的顺序练习，请先继续或手动选择开始新练习');
      const norm = value => { const m = /第\s*(\d+)\s*章/.exec(value); return m ? '第' + m[1] + '章' : value; };
      const buttons = Array.from(find('#modePanel').querySelectorAll('[data-ch]')).filter(b => norm(b.dataset.ch) === norm(plan.object.name));
      if (buttons.length !== 1) throw new Error('该章节没有唯一的可练习入口，请在页面选择');
      buttons[0].click();
      await wait(() => find('#qBack') || find('#modePanel .callout--warn'), '章节题目', ctx.guard);
    },
    'practice-kp': async (plan, ctx) => {
      await handlers['practice-mode']({ ...plan, values: { mode: 'order' } }, ctx);
      if (find('#rsContinue')) throw new Error('有未完成的顺序练习，请先继续或手动选择开始新练习');
      const button = find(`#modePanel [data-kp="${esc(plan.object.id)}"]`);
      if (!button) throw new Error('该知识点暂无可练习题目');
      button.click();
      await wait(() => find('#qBack') || find('#modePanel .callout--warn'), '知识点题目', ctx.guard);
    },
    'wrong-detail': async (plan, ctx) => { Practice.openWrongDetail(plan.object.id); await wait(() => find('#wdRedo'), '错题详情', ctx.guard); },
    'graph-detail': async (plan, ctx) => {
      const graph = await wait(() => GraphView._graph && GraphView._graph.nodes && GraphView._graph, '课程图谱', ctx.guard);
      const node = graph.nodes.find(node => node.id === plan.object.id);
      if (!node) throw new Error('此知识点当前不在可见图谱中');
      GraphView.openNode(node, graph);
      await wait(() => find('#kpPanel [data-st]'), '知识点详情', ctx.guard);
    },
    'graph-resources': async (plan, ctx) => { await handlers['graph-detail'](plan, ctx); await click('#kpPanel [data-st="resources"]', ctx.guard); },
    'student-resource': async (plan, ctx) => {
      const resource = await wait(() => (ResourceView._resList || []).find(r => r.resId === plan.object.id), '学习资源', ctx.guard);
      ResourceView.openResource(resource);
    },
    'student-report': async plan => MyReport.openDetail(plan.object.id),
    'teacher-report': async plan => Report.openDetail(plan.object.id),
    'student-alert-filter': async (plan, ctx) => click(`#alSeg [data-l="${esc(plan.values.level || 'all')}"]`, ctx.guard),
    'wrong-filter': async (plan, ctx) => click(`#wFilter [data-f="${esc(plan.values.filter || 'false')}"]`, ctx.guard),
    'monitor-student-filter': async (plan, ctx) => click(`#stuSeg [data-l="${esc(plan.values.level || 'all')}"]`, ctx.guard),
    'monitor-alert-filter': async (plan, ctx) => click(`#alSeg [data-l="${esc(plan.values.level || 'all')}"]`, ctx.guard),
    'bank-sort': async (plan, ctx) => {
      if (plan.values.sort) await click(`#bankSeg [data-s="${esc(plan.values.sort)}"]`, ctx.guard);
      if ('descending' in plan.values && (Question.bankDir === 'desc') !== plan.values.descending) await click('#bankDirBtn', ctx.guard);
    },
    'question-config': async (plan, ctx) => { if (plan.values.kpIds) await tags('#genKp', plan.values.kpIds, 'data-kp', ctx.guard); },
    'question-new': async (plan, ctx) => {
      await wait(() => find('#nqStem'), '新建题目', ctx.guard);
      if (plan.values.options) {
        const options = plan.values.options;
        if (options.length < 2 || options.length > 8) throw new Error('新建题目选项应为 2～8 个');
        const box = find('#nqOpts');
        box.innerHTML = options.map((option, index) => `<div class="row" style="gap:6px"><input type="radio" name="nqAns" value="${U.esc(option.key)}" ${option.key === plan.values.answer ? 'checked' : ''}><span>${U.esc(option.key)}</span><input class="input" data-opt="${U.esc(option.key)}" value="${U.esc(option.text)}"><button type="button" class="btn btn--xs btn--ghost" data-agent-remove-option>删除</button></div>`).join('');
        box.querySelectorAll('[data-agent-remove-option]').forEach(button => button.addEventListener('click', () => button.parentElement.remove()));
      }
      if (plan.values.answer) {
        const answer = find(`input[name="nqAns"][value="${esc(plan.values.answer)}"]`);
        if (!answer) throw new Error('答案不对应当前选项');
        answer.checked = true;
      }
    },
    'question-edit': async (plan, ctx) => {
      const response = await API.question.bank({ keyword: plan.object.name, page: 1, size: 100 });
      const question = (response.list || []).find(q => q.qId === plan.object.id);
      if (!question) throw new Error('无法读取当前课程中要编辑的题目');
      _openEditModal(question.qId, question);
      await wait(() => find('#eqStem'), '题目编辑', ctx.guard);
      if (plan.values.options) {
        find('#eqOpts').innerHTML = plan.values.options.map((option, index) => `<div class="eq-opt" data-i="${index}"><select class="select eq-opt-key"><option>${U.esc(option.key)}</option></select><input class="input eq-opt-text" value="${U.esc(option.text)}"><label><input type="checkbox" class="eq-opt-right" ${String(plan.values.answer || question.answer || '').includes(option.key) ? 'checked' : ''}>正确答案</label><button type="button" class="btn btn--xs btn--ghost eq-opt-del">删除</button></div>`).join('');
      }
    },
    'draft-edit': async (plan, ctx) => click(`[data-dedit="${esc(plan.object.id)}"]`, ctx.guard),
    'chapter-edit': async (plan, ctx) => { await wait(() => TeacherStructure.data, '课程目录', ctx.guard); TeacherStructure._chapterDetailModal(plan.object.id); },
    'kp-new': async (plan, ctx) => { await wait(() => TeacherStructure.data, '课程目录', ctx.guard); TeacherStructure._kpModal(plan.object.id); },
    'kp-edit': async (plan, ctx) => { await wait(() => TeacherStructure.data, '课程目录', ctx.guard); TeacherStructure._kpDetailModal(plan.object.id); },
    'resource-edit': async (plan, ctx) => {
      const resource = await wait(() => TeacherStructure.data && TeacherStructure.data.chapters.flatMap(ch => ch.resources || []).find(r => r.resId === plan.object.id), '目录资源', ctx.guard);
      TeacherStructure.openEditResourceModal(resource);
    },
    'resource-upload': async (plan, ctx) => {
      await wait(() => find('#trFile'), '资源上传窗口', ctx.guard);
      if (ctx.files.length) setFile(find('#trFile'), ctx.files);
    },
    'student-profile': async (plan, ctx) => { Monitor.openProfile(plan.object.id); await wait(() => find('#prMsg'), '学生详情', ctx.guard); },
    'student-message': async (plan, ctx) => { await handlers['student-profile'](plan, ctx); await click('#prMsg', ctx.guard); },
    'analysis-student': async (plan, ctx) => handlers['student-profile'](plan, ctx),
    'alert-review': async (plan, ctx) => click(`[data-review="${esc(plan.object.id)}"]`, ctx.guard),
    'graph-node': async (plan, ctx) => { await wait(() => TeacherGraphEdit.data && TeacherGraphEdit.data.nodes, '图谱节点', ctx.guard); TeacherGraphEdit._openDetail(plan.object.id); },
    'report-config': async (plan, ctx) => {
      if (plan.values.chapterIds) {
        const data = await API.teacher.structure();
        if (!ctx.guard()) throw new Error('课程已变化');
        const names = (data.chapterOptions || data.chapters || []).filter(ch => plan.values.chapterIds.includes(ch.id))
          .map(ch => { const match = /第\s*(\d+)\s*章/.exec(ch.name || ''); return match ? '第' + match[1] + '章' : ch.name; });
        if (names.length !== plan.values.chapterIds.length) throw new Error('无法匹配报告章节范围');
        await wait(() => find('#rgScope'), '报告章节范围', ctx.guard);
        find('#rgScope').querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = names.includes(input.value); input.dispatchEvent(new Event('change', { bubbles: true })); });
      }
      if (plan.values.sections) {
        const root = await wait(() => find('#rgSec'), '报告章节', ctx.guard);
        const buttons = Array.from(root.querySelectorAll('.chip'));
        if (plan.values.sections.some(section => !buttons.some(button => button.textContent.trim() === section))) throw new Error('报告章节名称不正确');
        buttons.forEach(button => { if (button.classList.contains('is-active') !== plan.values.sections.includes(button.textContent.trim())) button.click(); });
      }
    },
    'user-edit': async (plan, ctx) => {
      const response = await API.admin.listUsers({ keyword: plan.object.name });
      const account = (response.list || []).find(user => user.userId === plan.object.id);
      if (!account) throw new Error('未找到要编辑的账号');
      AdminUsers.openEdit(account);
    },
    'user-delete': async plan => AdminUsers.confirmDelete(plan.object.id, plan.object.name),
    'account-import': async (plan, ctx) => {
      await wait(() => find('#impRole'), '账号导入', ctx.guard);
      if (plan.values.role) set(find('#impRole'), plan.values.role);
      await click('#next1', ctx.guard);
      await wait(() => find('#impFile'), '账号文件选择', ctx.guard);
      if (plan.values.defaultPassword) set(find('#impPwd'), plan.values.defaultPassword);
      const files = ctx.files.length ? ctx.files : (plan.values.text ? [new File([plan.values.text], 'accounts.csv', { type: 'text/csv' })] : []);
      if (files.length) { setFile(find('#impFile'), files); await click('#parse', ctx.guard); }
    },
    'question-import': async (plan, ctx) => openQuestionImport(plan, ctx),
  };

  const TYPE_LABEL = { single: '单选题', multi: '多选题', blank: '填空题', judge: '判断题' };
  const COUNT_CHOICES = [
    { label: '5 道（课堂小测）', count: 5 },
    { label: '8 道', count: 8 },
    { label: '10 道（综合练习）', count: 10 },
  ];
  const TYPE_CHOICES = [
    { label: '单选题', types: ['single'] },
    { label: '单选 + 填空', types: ['single', 'blank'] },
    { label: '单选 + 多选 + 填空', types: ['single', 'multi', 'blank'] },
  ];
  const AgentPreview = {
    jobs: Object.create(null),
    current: '',
    wrap: null,
    shell: null,
    docked: false,
    closeTimer: 0,
    hasActiveGeneration() {
      return Object.values(this.jobs).some(job => job && ['running', 'stopping'].includes(job.status));
    },
    notifyGenerationState() {
      window.dispatchEvent(new CustomEvent('agent-preview-state', {
        detail: { busy: this.hasActiveGeneration() },
      }));
    },
    newTaskId() {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
      return 'agent-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    },
    stopActiveGeneration() {
      const current = this.jobs[this.current];
      const active = current && ['running', 'stopping'].includes(current.status)
        ? current
        : Object.values(this.jobs).find(job => job && ['running', 'stopping'].includes(job.status));
      return active ? this.stopGeneration(active) : false;
    },
    panelHtml() {
      return `
        <div class="chat__side-head">
          <h3 id="apTitle">${typeof icon === 'function' ? icon('sparkle') : ''} 题目预览</h3>
          <span class="badge badge--brand" id="apBadge">草稿</span>
          <span class="spacer"></span>
          <button type="button" class="btn btn--ghost btn--icon" id="apClose" title="隐藏扩展栏" aria-label="隐藏扩展栏">${typeof icon === 'function' ? icon('panelRightClose') : '×'}</button>
        </div>
        <div class="chat__side-body" id="apBody"></div>
        <div class="chat__side-foot">
          <span class="fz-12 t-dim" id="apHint">可编辑题目，或发布进题库。</span>
          <span class="spacer"></span>
          <button type="button" class="btn btn--primary" id="apPublishAll" disabled>全部发布进题库</button>
        </div>`;
    },
    ensure() {
      if (this.wrap && this.wrap.isConnected) return this.wrap;
      const shell = document.querySelector('#view-chat .chat-shell, #view-ai .chat-shell, #view-assistant .chat-shell');
      this.docked = Boolean(shell);
      this.shell = shell || null;
      const wrap = document.createElement(this.docked ? 'aside' : 'div');
      wrap.hidden = true;
      if (this.docked) {
        wrap.className = 'card chat__side chat__preview';
        wrap.id = 'agentPreviewPanel';
        wrap.setAttribute('aria-label', '题目预览');
        wrap.innerHTML = this.panelHtml();
        shell.appendChild(wrap);
      } else {
        wrap.className = 'drawer-wrap';
        wrap.id = 'agentPreviewWrap';
        wrap.innerHTML = `<div class="drawer agent-preview" role="dialog" aria-modal="true" aria-labelledby="apTitle">${this.panelHtml()}</div>`;
        wrap.addEventListener('click', event => { if (event.target === wrap) this.close(); });
        document.body.appendChild(wrap);
      }
      wrap.querySelector('#apClose').addEventListener('click', () => this.close());
      wrap.querySelector('#apPublishAll').addEventListener('click', () => this.publishAll());
      this.wrap = wrap;
      return wrap;
    },
    open() {
      const wrap = this.ensure();
      clearTimeout(this.closeTimer);
      this.closeTimer = 0;
      if (this.docked && this.shell) {
        const history = this.shell.querySelector('#chatHistory');
        if (history && !history.hidden) {
          // 通过聊天视图自身的关闭逻辑更新状态，再复用同一右侧停靠位。
          this.shell.querySelector('#closeHistoryBtn')?.click();
          history.hidden = true;
        }
        const resizeHandle = this.shell.querySelector('#chatSideResizeHandle');
        if (resizeHandle) resizeHandle.hidden = false;
        wrap.hidden = false;
        wrap.classList.remove('is-open');
        this.shell.classList.add('is-preview-open');
        const viewportWidth = Math.max(320, Math.round(window.innerWidth || document.documentElement.clientWidth || 0));
        const maxWidth = Math.max(260, Math.min(viewportWidth, Math.round(this.shell.getBoundingClientRect().right)));
        const currentWidth = Number.parseFloat(this.shell.style.getPropertyValue('--chat-side-width')) || 360;
        const fullScreen = currentWidth >= Math.min(Math.round(viewportWidth * 0.8), maxWidth);
        this.shell.classList.toggle('is-side-fullscreen', fullScreen);
        resizeHandle?.setAttribute('aria-valuemax', String(viewportWidth));
        resizeHandle?.setAttribute('aria-valuenow', String(fullScreen ? viewportWidth : currentWidth));
        resizeHandle?.setAttribute('aria-valuetext', fullScreen ? '全屏' : `${currentWidth} 像素`);
        requestAnimationFrame(() => {
          if (this.wrap === wrap && this.shell?.classList.contains('is-preview-open')) wrap.classList.add('is-open');
        });
      } else {
        wrap.hidden = false;
      }
    },
    close(options = {}) {
      if (!this.wrap) return;
      const wrap = this.wrap;
      if (!this.docked || !this.shell) {
        wrap.hidden = true;
        return;
      }
      const shell = this.shell;
      const resizeHandle = shell.querySelector('#chatSideResizeHandle');
      const hideAfterTransition = () => {
        if (this.wrap !== wrap || shell.classList.contains('is-preview-open')) return;
        wrap.hidden = true;
        if (!shell.classList.contains('is-history-open') && resizeHandle) resizeHandle.hidden = true;
        this.closeTimer = 0;
      };
      clearTimeout(this.closeTimer);
      this.closeTimer = 0;
      wrap.classList.remove('is-open');
      shell.classList.remove('is-preview-open');
      shell.classList.remove('is-side-fullscreen');
      shell.dispatchEvent(new Event('agent:sidepane-close'));
      if (options.immediate) {
        hideAfterTransition();
      } else {
        this.closeTimer = setTimeout(hideAfterTransition, 320);
      }
    },
    refreshIfVisible(job) {
      if (!job || this.current !== job.id) return;
      const visible = this.docked
        ? Boolean(this.shell && this.shell.classList.contains('is-preview-open'))
        : Boolean(this.wrap && !this.wrap.hidden);
      if (visible) this.render(job);
    },
    missingOf(plan) {
      const values = (plan && plan.values) || {};
      const kpIds = Array.isArray(values.kpIds) ? values.kpIds.filter(Boolean) : [];
      const types = Array.isArray(values.types) ? values.types.filter(Boolean) : [];
      const count = Number(values.count);
      const missing = [];
      if (!kpIds.length) missing.push('scope');
      if (!Number.isInteger(count) || count < 1) missing.push('count');
      if (!types.length) missing.push('types');
      return { kpIds, types, count: (Number.isInteger(count) && count >= 1) ? count : 0, missing };
    },
    storageKey(plan) {
      if (!plan || !plan.id) return '';
      const user = window.Auth && typeof Auth.currentUser === 'function' ? Auth.currentUser() : null;
      const parts = [
        (user && (user.userId || user.user_id || user.id)) || '',
        plan.courseId || currentCourse() || '',
        plan.sessionId || 'new',
        plan.id,
      ];
      return 'course-agent:agent-question-preview:v1:' + parts.map(value => encodeURIComponent(String(value))).join(':');
    },
    persist(job) {
      const key = this.storageKey(job && job.plan);
      if (!key || !job) return;
      try {
        sessionStorage.setItem(key, JSON.stringify({
          version: 1,
          id: job.id,
          status: job.status,
          drafts: job.drafts || [],
          error: job.error || '',
          count: job.count || 0,
          types: job.types || [],
          kpIds: job.kpIds || [],
          difficulty: job.difficulty || 3,
          courseId: job.courseId || '',
        }));
      } catch (_) {
        // 会话存储不可用或已满时，当前页面中的预览仍可正常使用。
      }
    },
    restore(plan) {
      const key = this.storageKey(plan);
      if (!key) return null;
      try {
        const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
        if (!saved || saved.version !== 1 || saved.id !== plan.id || !Array.isArray(saved.drafts)) return null;
        const drafts = saved.drafts.filter(item => item && item.payload && typeof item.payload === 'object');
        let status = saved.status;
        let error = saved.error || '';
        if (status === 'starting' || status === 'running' || status === 'stopping') {
          if (drafts.length) {
            status = 'done';
            const expected = Number(saved.count) || 0;
            if (!error && expected > drafts.length) {
              error = `页面刷新前生成中断，已恢复 ${drafts.length} 道题；如需补充，请重新发起出题请求。`;
            }
          }
          else {
            status = 'error';
            error = error || '页面刷新前生成任务尚未产出题目，已停止自动重试；请重新发起出题请求。';
          }
        }
        if (!['done', 'error', 'stopped'].includes(status)) return null;
        if (status === 'done' && !drafts.length) {
          status = 'error';
          error = error || '没有可恢复的题目结果，请重新发起出题请求。';
        }
        return {
          id: plan.id,
          status,
          drafts,
          error,
          count: Number(saved.count) || drafts.length,
          types: Array.isArray(saved.types) ? saved.types : [],
          kpIds: Array.isArray(saved.kpIds) ? saved.kpIds : [],
          difficulty: Number(saved.difficulty) || 3,
          courseId: saved.courseId || plan.courseId || '',
          plan,
          missing: [],
        };
      } catch (_) {
        return null;
      }
    },
    arm(plan) {
      if (!plan || plan.target !== 'teacher.question.create') return null;
      if (this.jobs[plan.id]) return this.jobs[plan.id];
      const restored = this.restore(plan);
      if (restored) {
        this.jobs[plan.id] = restored;
        return restored;
      }
      const parsed = this.missingOf(plan);
      this.jobs[plan.id] = {
        id: plan.id,
        status: parsed.missing.length ? 'need_input' : 'starting',
        drafts: [], error: '',
        count: parsed.count, types: parsed.types, kpIds: parsed.kpIds,
        difficulty: (plan.values && plan.values.difficulty) || 3,
        courseId: plan.courseId, plan, missing: parsed.missing.slice(),
      };
      return this.jobs[plan.id];
    },
    slotHtml(plan) {
      if (!plan) return '';
      if (plan.target !== 'teacher.question.create') {
        return `<div class="msg__agent-acts"><button type="button" class="btn btn--sm btn--primary" data-agent-ui="${U.esc(JSON.stringify(plan))}">${U.esc(plan.label || '打开操作界面')}</button></div>`;
      }
      let job = this.jobs[plan.id];
      if (!job) {
        job = this.restore(plan);
        if (job) this.jobs[plan.id] = job;
      }
      const inner = job
        ? this.slotInner(job)
        : `<button type="button" class="btn btn--sm btn--primary" data-agent-ui="${U.esc(JSON.stringify(plan))}">${U.esc(plan.label || '预览题目')}</button>`;
      return `<div class="msg__agent-acts msg__preview-slot" data-preview-job="${U.esc(plan.id)}">${inner}</div>`;
    },
    slotInner(job) {
      if (!job) return '';
      if (job.status === 'need_input') return this.choiceHtml(job);
      if (['starting', 'running', 'stopping'].includes(job.status)) return this.progressHtml(job);
      const label = ['error', 'stopped'].includes(job.status) && !job.drafts.length ? '查看生成状态' : '预览题目';
      return `<button type="button" class="btn btn--sm btn--primary" data-ap-open="${U.esc(job.id)}">${label}</button>`;
    },
    progressHtml(job, inPanel = false) {
      const made = (job.drafts || []).length;
      const line = job.status === 'starting'
        ? '\u6b63\u5728\u51c6\u5907\u51fa\u9898\u2026'
        : (job.status === 'stopping' ? '\u6b63\u5728\u505c\u6b62\u751f\u6210\u2026'
          : (made ? '\u5df2\u751f\u6210 ' + made + ' \u9053\u9898\uff0c\u7ee7\u7eed\u751f\u6210\u4e2d\u2026' : '\u6b63\u5728\u751f\u6210\u9898\u76ee\u2026'));
      return '<div class="agent-progress' + (inPanel ? ' agent-progress--panel' : '') + '" role="status" aria-live="polite">' +
        '<span class="agent-progress__spinner" aria-hidden="true"></span>' +
        '<b class="agent-progress__text">' + U.esc(line) + '</b>' +
        (['running', 'stopping'].includes(job.status)
          ? '<button type="button" class="btn btn--sm" data-ap-stop="' + U.esc(job.id) + '"' + (job.status === 'stopping' ? ' disabled' : '') + '>' + (job.status === 'stopping' ? '\u6b63\u5728\u505c\u6b62' : '\u505c\u6b62') + '</button>'
          : '') +
      '</div>';
    },
    choiceHtml(job) {
      const missing = job.missing || [];
      if (missing.includes('scope')) {
        return `<div class="agent-choices"><p class="agent-choices__prompt">还需要确定章节或知识点范围，请直接回复要出哪一章。</p></div>`;
      }
      const askCount = missing.includes('count');
      const prompt = askCount ? '这次出几道题？' : '用哪些题型？';
      const options = askCount ? COUNT_CHOICES : TYPE_CHOICES;
      const buttons = options.map(option => askCount
        ? `<button type="button" class="agent-choice" data-preview-count="${option.count}">${U.esc(option.label)}</button>`
        : `<button type="button" class="agent-choice" data-preview-types="${U.esc(option.types.join(','))}">${U.esc(option.label)}</button>`
      ).join('');
      return `<div class="agent-choices"><p class="agent-choices__prompt">${prompt}</p><div class="agent-choices__list">${buttons}</div></div>`;
    },
    paintSlot(job) {
      if (!job) return;
      document.querySelectorAll(`[data-preview-job="${CSS.escape ? CSS.escape(job.id) : job.id}"]`).forEach(slot => {
        slot.innerHTML = this.slotInner(job);
        this.bindSlot(slot, job);
      });
    },
    bindSlot(slot, job) {
      if (!slot || !job) return;
      slot.querySelectorAll('[data-ap-open]').forEach(btn => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => this.show(job.id));
      });
      slot.querySelectorAll('[data-ap-stop]').forEach(btn => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => this.stopGeneration(job));
      });
      slot.querySelectorAll('[data-preview-count]').forEach(btn => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => this.acceptCount(job, Number(btn.dataset.previewCount), btn));
      });
      slot.querySelectorAll('[data-preview-types]').forEach(btn => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => this.acceptTypes(job, (btn.dataset.previewTypes || '').split(',').filter(Boolean), btn));
      });
    },
    acceptCount(job, count, btn) {
      if (!job || job.status !== 'need_input' || !Number.isInteger(count) || count < 1) return;
      job.count = count;
      job.missing = (job.missing || []).filter(item => item !== 'count');
      if (btn) {
        btn.classList.add('is-picked');
        btn.parentElement && btn.parentElement.querySelectorAll('.agent-choice').forEach(el => { el.disabled = true; });
      }
      if ((job.missing || []).length) { this.paintSlot(job); return; }
      this.beginGenerate(job);
    },
    acceptTypes(job, types, btn) {
      if (!job || job.status !== 'need_input' || !types.length) return;
      job.types = types;
      job.missing = (job.missing || []).filter(item => item !== 'types');
      if (btn) {
        btn.classList.add('is-picked');
        btn.parentElement && btn.parentElement.querySelectorAll('.agent-choice').forEach(el => { el.disabled = true; });
      }
      if ((job.missing || []).length) { this.paintSlot(job); return; }
      this.beginGenerate(job);
    },
    startQuestions(plan, ctx) {
      const job = this.arm(plan);
      if (!job) return false;
      if (job.status === 'running' || job.status === 'starting' || job.status === 'stopping') {
        if (job.status === 'running' || job.status === 'stopping') this.paintSlot(job);
        else if (ctx && ctx.auto) this.beginGenerate(job);
        else {
          job.status = 'error';
          job.error = '没有找到这条出题操作对应的预览记录，为避免重复出题，本次没有重新生成。请到题目草稿箱查看已保存草稿；如需新题，请重新提出出题请求。';
          this.persist(job);
          this.paintSlot(job);
          this.show(job.id);
        }
        return true;
      }
      if (job.status === 'need_input') {
        this.paintSlot(job);
        return true;
      }
      if (job.status === 'stopped') {
        this.show(job.id);
        return true;
      }
      this.show(plan.id);
      return true;
    },
    beginGenerate(job) {
      if (!job || job.status === 'running' || job.status === 'done') return true;
      if (!API.question || typeof API.question.genStream !== 'function') throw new Error('当前页无法生成题目');
      if (!(job.kpIds || []).length) throw new Error('请先确定要出题的知识点');
      if (!job.count) throw new Error('请先选择出题数量');
      if (!(job.types || []).length) job.types = ['single'];
      job.taskId = this.newTaskId();
      job.controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      job.cancelRequested = false;
      const taskId = job.taskId;
      job.status = 'running';
      job.error = '';
      this.persist(job);
      this.paintSlot(job);
      this.notifyGenerationState();
      API.question.genStream({
        kpIds: job.kpIds, types: job.types, difficulty: job.difficulty, count: job.count,
        requirement: '题型：' + job.types.map(t => TYPE_LABEL[t] || t).join('、') + '。',
        taskId,
      }, {
        onDraft: (d) => {
          const payload = (d && d.payload) || {};
          job.drafts.push({
            draftId: (d && (d.draftId || d.draft_id)) || '',
            status: (d && d.status) || (d && d.ok === false ? 'invalid' : 'draft'),
            errors: (d && d.errors) || [],
            payload,
            kpIds: (d && d.kpIds) || payload.kp_ids || [],
            chapterId: (d && d.chapterId) || payload.chapter_id || '',
          });
          this.persist(job);
          this.paintSlot(job);
        },
        onError: (d) => {
          job.error = (d && d.message) || '生成出错';
          this.persist(job);
        },
        onDone: (d) => {
          const stopped = job.cancelRequested || Boolean(d && d.stopped);
          if (stopped) {
            job.status = 'stopped';
            job.error = job.drafts.length
              ? '已停止生成，已生成的题目草稿保留在此处。'
              : '已停止生成，没有未保存的题目写入草稿。';
          } else {
            job.status = job.drafts.length ? 'done' : 'error';
            if (!job.drafts.length && !job.error) job.error = '本次没有产出题目，请调整范围后重试';
          }
          if (d && d.count) job.count = d.count;
          job.controller = null;
          job.taskId = '';
          this.persist(job);
          this.paintSlot(job);
          this.notifyGenerationState();
          if (stopped) {
            this.refreshIfVisible(job);
          } else {
            this.show(job.id);
            if (job.drafts.length) Toast.ok('题目已生成', `${job.drafts.length} 道可在右侧预览中编辑或发布`);
          }
        },
      }, { signal: job.controller && job.controller.signal }).catch(err => {
        const stopped = job.cancelRequested;
        if (stopped) {
          job.status = 'stopped';
          job.error = job.drafts.length
            ? '已停止生成，已生成的题目草稿保留在此处。'
            : '已停止生成，没有未保存的题目写入草稿。';
        } else {
          job.status = job.drafts.length ? 'done' : 'error';
          job.error = (err && err.message) || '生成失败';
        }
        job.controller = null;
        job.taskId = '';
        this.persist(job);
        this.paintSlot(job);
        this.notifyGenerationState();
        if (stopped) this.refreshIfVisible(job);
        else this.show(job.id);
      });
      return true;
    },
    stopGeneration(job) {
      if (!job || !['running', 'stopping'].includes(job.status) || job.cancelRequested) return false;
      job.cancelRequested = true;
      job.status = 'stopping';
      job.error = '';
      this.persist(job);
      this.paintSlot(job);
      if (this.current === job.id) this.render(job);
      this.notifyGenerationState();
      const settleAsFinished = () => {
        job.cancelRequested = false;
        if (job.status === 'stopped') {
          job.status = job.drafts.length ? 'done' : 'error';
          job.error = job.drafts.length ? '' : '生成任务已在停止请求前结束，未产出题目。';
        }
        this.persist(job);
        this.paintSlot(job);
        if (this.current === job.id) this.render(job);
        this.notifyGenerationState();
      };
      const confirmStop = async () => {
        let lastError = null;
        for (let attempt = 0; attempt < 20; attempt += 1) {
          try {
            const result = await API.question.genStop({ taskId: job.taskId });
            if (result && result.stopped === true) {
              try { job.controller && job.controller.abort(); } catch (_) {}
              return;
            }
            lastError = null;
          } catch (error) {
            lastError = error;
          }
          // SSE 若已自然结束，让尾部已保存草稿事件完成展示。
          if (job.status !== 'stopping') {
            settleAsFinished();
            return;
          }
          if (attempt < 19) await new Promise(resolve => setTimeout(resolve, 80));
        }
        if (job.status === 'stopping') {
          job.cancelRequested = false;
          job.status = 'running';
          job.error = '';
          this.persist(job);
          this.paintSlot(job);
          if (this.current === job.id) this.render(job);
          this.notifyGenerationState();
          Toast.warn('停止请求未确认', lastError && lastError.message
            ? lastError.message
            : '出题仍在继续，请稍后重试停止。');
        }
      };
      confirmStop();
      return true;
    },
    show(id) {
      this.current = id;
      this.open();
      this.render(this.jobs[id]);
    },
    render(job) {
      if (!job) return;
      this.ensure();
      const badge = this.wrap.querySelector('#apBadge');
      const body = this.wrap.querySelector('#apBody');
      const publish = this.wrap.querySelector('#apPublishAll');
      const hint = this.wrap.querySelector('#apHint');
      const made = job.drafts.length;
      if (job.status === 'running' || job.status === 'stopping') {
        badge.textContent = job.status === 'stopping' ? '正在停止' : (made ? `已出 ${made} 题` : '生成中');
        badge.className = 'badge badge--brand';
      } else if (job.status === 'error' && !made) {
        badge.textContent = '未完成';
        badge.className = 'badge badge--danger';
      } else if (job.status === 'stopped') {
        badge.textContent = '已停止';
        badge.className = 'badge badge--warn';
      } else {
        badge.textContent = `${made} 题 · 草稿`;
        badge.className = 'badge badge--ok';
      }
      const progress = (job.status === 'running' || job.status === 'starting' || job.status === 'stopping')
        ? this.progressHtml(job, true)
        : (job.error ? `<div class="callout callout--${made ? 'warn' : 'danger'}" style="margin-bottom:12px">${typeof icon === 'function' ? icon('alert') : ''}<div>${U.esc(job.error)}</div></div>` : '');
      body.innerHTML = progress + (made
        ? job.drafts.map((d, i) => this.cardHtml(d, i)).join('')
        : (['running', 'stopping'].includes(job.status) ? '' : '<div class="empty"><b>还没有题目</b><p>生成失败或被中断，请重新在对话里提出出题请求。</p></div>'));
      body.querySelectorAll('[data-ap-stop]').forEach(btn => {
        btn.addEventListener('click', () => this.stopGeneration(job));
      });
      hint.textContent = made ? '可逐题编辑，或发布进题库。' : '草稿尚未进入正式题库。';
      publish.disabled = !job.drafts.some(d => d.status === 'draft');
      body.querySelectorAll('[data-ap-edit]').forEach(btn => btn.addEventListener('click', () => {
        const draft = job.drafts[Number(btn.dataset.apEdit)];
        if (!draft) return;
        if (typeof Question === 'undefined' || !Question.openDraftEdit) {
          Toast.warn('当前页无法打开编辑器', '请到「AI 出题与题库 → 草稿箱」编辑');
          return;
        }
        Question.openDraftEdit(draft, {
          onSaved: (res, payload) => {
            draft.payload = payload || draft.payload;
            if (res && res.status) draft.status = res.status;
            if (res && res.errors) draft.errors = res.errors;
            this.persist(job);
            if (this.current === job.id) this.render(job);
          }
        });
      }));
      body.querySelectorAll('[data-ap-pub]').forEach(btn => btn.addEventListener('click', () => this.publishOne(job, Number(btn.dataset.apPub), btn)));
      job.drafts.forEach((d, i) => {
        const q = d.payload || {};
        if (q.graph && window.DsFigure) {
          const el = this.wrap.querySelector('#apFig' + i);
          if (el) DsFigure.mount(el, q.graph);
        }
      });
    },
    cardHtml(d, i) {
      const q = d.payload || {};
      const typeLabel = TYPE_LABEL[q.type] || (typeof Question !== 'undefined' && Question.GEN_TYPE_LABEL && Question.GEN_TYPE_LABEL[q.type]) || '题目';
      const optHtml = (typeof Question !== 'undefined' && Question._genOptionHtml)
        ? Question._genOptionHtml(q, 'apOptFig' + i)
        : '';
      const status = d.status === 'draft'
        ? '<span class="badge badge--ok">校验通过 · 草稿</span>'
        : (d.status === 'published' ? '<span class="badge badge--brand">已发布</span>' : '<span class="badge badge--danger">待修改</span>');
      const errs = (d.errors || []).length
        ? `<div class="callout callout--danger" style="margin-top:8px;padding:7px 10px">${U.esc(d.errors.join('；'))}</div>` : '';
      return `
        <article class="gen-q" style="margin-bottom:12px">
          <div class="gen-q__head">
            <span class="badge badge--brand">${i + 1}</span>
            <b>${U.esc(typeLabel)}</b>
            ${status}
          </div>
          <div class="gen-q__body">
            <div>${U.esc(q.question || '')}</div>
            <div id="apFig${i}" style="margin:8px 0"></div>
            ${optHtml}
            <div class="callout callout--brand" style="margin-top:10px;padding:9px 11px"><div><b>解析：</b>${U.esc(q.analysis || '暂无')}</div></div>
            ${errs}
          </div>
          <div class="row" style="padding:0 14px 12px;gap:8px">
            ${d.status !== 'published' ? `<button type="button" class="btn btn--sm btn--outline" data-ap-edit="${i}">编辑</button>` : ''}
            ${d.status === 'draft' ? `<button type="button" class="btn btn--sm btn--primary" data-ap-pub="${i}">发布进题库</button>` : ''}
          </div>
        </article>`;
    },
    async publishOne(job, index, button) {
      const draft = job.drafts[index];
      if (!draft || draft.status !== 'draft') return;
      button.disabled = true;
      button.textContent = '发布中…';
      try {
        const res = await API.question.draftPublish({ draftId: draft.draftId });
        draft.status = 'published';
        draft.publishedQId = res && res.qId;
        this.persist(job);
        Toast.ok('已发布进题库', res && res.qId ? ('题号 ' + res.qId) : '');
        if (this.current === job.id) this.render(job);
      } catch (err) {
        button.disabled = false;
        button.textContent = '发布进题库';
        Toast.err('发布失败', err && err.message);
      }
    },
    async publishAll() {
      const job = this.jobs[this.current];
      if (!job) return;
      const pending = job.drafts.filter(d => d.status === 'draft');
      if (!pending.length) return;
      const btn = this.wrap.querySelector('#apPublishAll');
      btn.disabled = true;
      let ok = 0;
      for (const draft of pending) {
        try {
          const res = await API.question.draftPublish({ draftId: draft.draftId });
          draft.status = 'published';
          draft.publishedQId = res && res.qId;
          this.persist(job);
          ok += 1;
        } catch (err) {
          Toast.err('部分题目发布失败', err && err.message);
          break;
        }
      }
      if (ok) Toast.ok('已发布进题库', ok + ' 道题已可供学生练习');
      this.render(job);
    },
  };

  const reportExecutors = {
    'student-report-create': async (plan, ctx) => {
      await wait(() => find('#genMyReport'), '报告生成按钮', ctx.guard);
      if (!ctx.guard()) return false;
      return MyReport.generate();
    },
    'teacher-report-create': async (plan, ctx) => {
      await wait(() => find('#rgTitle') && find('#rgGo'), '报告配置', ctx.guard);
      if (currentCourse() !== plan.courseId) throw new Error('报告课程已变化，请重新提出生成请求');
      for (const key of ['startDate', 'endDate']) {
        if (plan.values[key] && find(key === 'startDate' ? '#rgStart' : '#rgEnd').value !== plan.values[key]) {
          throw new Error('日期范围未能按要求设置，请在弹窗核对后生成');
        }
      }
      await click('#rgGo', ctx.guard);
      return Report._generating ? await Report._generating : false;
    },
    'teacher-question-create': async (plan, ctx) => AgentPreview.startQuestions(plan, ctx),
  };

  async function openQuestionImport(plan, ctx) {
    let preview = null;
    let version = 0;
    const values = plan.values || {};
    let selectedKps = new Set(values.kpIds || []);
    const modal = Modal.open({
      title: '导入题目 · 预览与核对', size: 'wide',
      closeOnBackdrop: false,
      body: `<div class="stack" style="gap:12px"><label>选择题目文件<input class="input" id="qiFile" type="file" accept=".txt,.md,.json,.csv,.xlsx,.docx,.pdf"></label><label>题目文字／JSON（题干、A/B 选项、答案、解析）<textarea class="input" id="qiText" style="min-height:100px"></textarea></label><label>统一归属章节（可选）<select class="select" id="qiChapter"><option value="">保留各题原有归属</option></select></label><div>统一知识点标签（可选，选择后覆盖各题标签）<div class="chips" id="qiKps"></div></div><button class="btn" id="qiParse" type="button">解析预览</button><p id="qiStatus" class="t-dim"></p><div id="qiRows" class="stack"></div></div>`,
      footer: `<button class="btn btn--primary" id="qiCommit" disabled type="button">确认导入题库</button><button class="btn" data-close>取消</button>`,
    });
    const root = modal.el;
    root.querySelector('#qiText').value = values.text || (values.questions ? JSON.stringify(values.questions, null, 2) : '');
    const status = root.querySelector('#qiStatus');
    const commit = root.querySelector('#qiCommit');
    const invalidate = () => { version++; preview = null; commit.disabled = true; };
    root.querySelector('#qiText').addEventListener('input', invalidate);
    root.querySelector('#qiFile').addEventListener('change', invalidate);
    root.querySelector('#qiChapter').addEventListener('change', invalidate);
    const structure = await API.teacher.structure().catch(() => {
      status.textContent = '章节与知识点加载失败，可先核对题目内容，稍后重新打开选择归属。';
      return {};
    });
    if (!root.isConnected || !ctx.guard()) return;
    const chapterSelect = root.querySelector('#qiChapter');
    chapterSelect.innerHTML += (structure.chapterOptions || []).map(ch => `<option value="${U.esc(ch.id)}">${U.esc(ch.name)}</option>`).join('');
    if (values.chapterId) set(chapterSelect, values.chapterId);
    const kpBox = root.querySelector('#qiKps');
    kpBox.innerHTML = (structure.kpOptions || []).map(kp => `<button type="button" class="chip ${selectedKps.has(kp.id) ? 'is-active' : ''}" data-qi-kp="${U.esc(kp.id)}">${U.esc(kp.name)}</button>`).join('');
    kpBox.addEventListener('click', event => {
      const button = event.target.closest('[data-qi-kp]'); if (!button) return;
      const id = button.dataset.qiKp;
      selectedKps.has(id) ? selectedKps.delete(id) : selectedKps.add(id);
      button.classList.toggle('is-active', selectedKps.has(id)); invalidate();
    });
    const parse = async () => {
      const revision = ++version;
      commit.disabled = true; preview = null; status.textContent = '解析与校验中…';
      const button = root.querySelector('#qiParse'); button.disabled = true;
      try {
        const form = new FormData();
        const file = root.querySelector('#qiFile').files[0];
        if (file) form.append('file', file);
        else form.append('text', root.querySelector('#qiText').value);
        form.append('chapterId', chapterSelect.value);
        form.append('kpIds', JSON.stringify(Array.from(selectedKps)));
        const result = await API.teacher.importQuestionPreview(form);
        if (!root.isConnected || revision !== version || !ctx.guard()) return;
        preview = result;
        status.textContent = `共 ${result.total} 题，可导入 ${result.valid} 题。请核对内容后确认导入；不会自动保存。`;
        root.querySelector('#qiRows').innerHTML = result.questions.map((question, index) => {
          const optionText = question.type === 'blank'
            ? (question.options || []).map(option => `第${option.blank}空：${(option.accept || []).join(' | ')}`).join('；')
            : (question.options || []).map(option => (option.key || '') + '. ' + (option.text || '')).join('\n');
          return `<section class="card"><div class="card__body"><b>第 ${index + 1} 题 · ${question.type === 'blank' ? '填空题' : (question.type === 'multi' ? '多选题' : '单选题')}</b><textarea class="input" data-qi-field="stem" data-index="${index}">${U.esc(question.stem || '')}</textarea><p>${U.esc(optionText)}</p><label>答案<input class="input" data-qi-field="answer" data-index="${index}" value="${U.esc(question.answer || '')}"></label><label>解析<textarea class="input" data-qi-field="analysis" data-index="${index}">${U.esc(question.analysis || '')}</textarea></label><p class="t-danger">${U.esc((result.errors.find(error => error.index === index) || { errors: [] }).errors.join('；'))}</p></div></section>`;
        }).join('');
        root.querySelectorAll('[data-qi-field]').forEach(input => input.addEventListener('input', () => {
          const questions = result.questions.map(question => ({ ...question }));
          root.querySelectorAll('[data-qi-field]').forEach(field => { questions[Number(field.dataset.index)][field.dataset.qiField] = field.value; });
          root.querySelector('#qiText').value = JSON.stringify(questions, null, 2);
          // 编辑后重新校验 JSON，不再以原文件覆盖修改。
          root.querySelector('#qiFile').value = ''; invalidate(); status.textContent = '内容已修改，请再次解析预览后导入。';
        }));
        commit.disabled = !result.ready;
      } catch (error) { status.textContent = error.message || '解析失败'; }
      finally { button.disabled = false; }
    };
    root.querySelector('#qiParse').addEventListener('click', parse);
    commit.addEventListener('click', async () => {
      if (!preview || !preview.ready || !ctx.guard()) return;
      commit.disabled = true;
      try {
        const result = await API.teacher.importQuestions({ questions: preview.questions });
        status.textContent = `成功导入 ${result.success} 题，已放入草稿箱。请在草稿箱核对后再发布，学生才能练习。${(result.errors || []).join('；')}`;
        preview = null;
        if (Question.showDrafts) Question.showDrafts();
      } catch (error) { status.textContent = error.message || '导入失败'; commit.disabled = false; }
    });
    if (ctx.files.length && !values.questions) setFile(root.querySelector('#qiFile'), ctx.files);
    if (ctx.files.length || values.questions || values.text) await parse();
  }

  async function apply(plan, options = {}) {
    if (!plan || !plan.id || !plan.target) return false;
    if (running || (options.auto && executed.has(plan.id))) return false;
    const snapshot = { role: role(), userId: userId(), course: currentCourse(), view: Router.current, login: loginId() };
    if (plan.role !== snapshot.role || plan.userId !== snapshot.userId || (plan.role !== 'admin' && plan.courseId !== snapshot.course)) {
      Toast.warn('操作属于其他账号或课程，请在当前上下文重新提问'); return false;
    }
    if (options.auto && Router.current !== options.fromView) return false;
    if (document.querySelector('.overlay [data-agent-dirty="1"], .view.is-active form [data-agent-dirty="1"], .view.is-active .ge-detail.open [data-agent-dirty="1"]')) {
      Toast.warn('当前有未保存内容，请先保存或关闭，再点击操作入口'); return false;
    }
    running = true;
    const ctx = { files: options.files || [], allowCourseChange: false, targetView: snapshot.view, auto: options.auto === true };
    ctx.guard = () => role() === snapshot.role && userId() === snapshot.userId && loginId() === snapshot.login &&
      (ctx.allowCourseChange || currentCourse() === snapshot.course) && Router.current === ctx.targetView;
    try {
      const spec = (await load()).find(item => item.id === plan.target && item.role === snapshot.role);
      if (!spec || Object.keys(plan.values || {}).some(key => !spec.fields[key])) throw new Error('此操作入口或字段不受支持');
      if (spec.entity && (!plan.object || !plan.object.id)) throw new Error('尚未确定目标对象');
      if (spec.execute && (!reportExecutors[spec.execute] || plan.auto !== true)) throw new Error('生成内容需要明确的操作请求');
      const isReport = spec.execute === 'student-report-create' || spec.execute === 'teacher-report-create';
      const reportKey = isReport ? 'agent-report:' + snapshot.login + ':' + snapshot.userId + ':' + plan.id : '';
      if (reportKey && (executed.has(plan.id) || sessionStorage.getItem(reportKey))) {
        Router.go('report');
        Toast.warn('这条生成请求已执行过', '可在历史归档查看报告；需要新报告请重新提出请求或点击页面生成按钮');
        return false;
      }
      if (!ctx.guard()) return false;
      if (spec.view) { ctx.targetView = spec.view; Router.go(spec.view); }
      for (const step of spec.steps) await click(step.selector.replaceAll('{object_id}', esc(plan.object && plan.object.id || '')), ctx.guard);
      if (spec.handler) {
        if (!handlers[spec.handler]) throw new Error('此入口尚未接通');
        await handlers[spec.handler](plan, ctx);
      }
      // 章节先回填并触发 change，待知识点选项加载后再回填依赖字段。
      for (const [key, value] of Object.entries(plan.values || {})) {
        const field = spec.fields[key];
        if (!field.selector) continue;
        const element = await wait(() => find(field.selector) && (!find(field.selector).options || Array.from(find(field.selector).options).some(o => o.value === String(value))) && find(field.selector), '回填字段', ctx.guard);
        set(element, value);
        if (element.closest('.overlay, form, .ge-detail')) element.dataset.agentDirty = '1';
      }
      if (plan.values && plan.values.kpIds) {
        const tagSelector = { 'question-new': '#nqKpTags', 'question-edit': '#eqKpTags', 'resource-edit': '#erKpTags', 'resource-upload': '#trKpTags' }[spec.handler];
        if (tagSelector) await tags(tagSelector, plan.values.kpIds, 'data-kp', ctx.guard);
      }
      if (spec.file_input && ctx.files.length && spec.handler !== 'resource-upload') setFile(await wait(() => find(spec.file_input), '附件选择', ctx.guard), ctx.files);
      if (spec.focus) {
        const element = await wait(() => find(spec.focus), '目标面板', ctx.guard);
        element.scrollIntoView({ block: 'center', behavior: 'smooth' });
        if (element.focus) element.focus();
      }
      if (spec.execute) {
        // 浏览器刷新后同一个计划也不能再次写入。失败/中断后保留页面上的手动生成按钮。
        if (!ctx.guard()) return false;
        if (reportKey) sessionStorage.setItem(reportKey, 'started');
        executed.add(plan.id);
        const success = await reportExecutors[spec.execute](plan, ctx);
        if (reportKey) sessionStorage.setItem(reportKey, success ? 'done' : 'failed');
        return Boolean(success);
      }
      executed.add(plan.id);
      return true;
    } catch (error) { Toast.warn('未能完成界面操作', error.message || '请重试'); return false; }
    finally { running = false; }
  }
  document.addEventListener('input', event => {
    if (event.isTrusted && event.target.matches('input, textarea, select') && event.target.closest('.overlay, form, .ge-detail')) event.target.dataset.agentDirty = '1';
  });
  function openImport() {
    const snapshot = { role: role(), user: userId(), course: currentCourse(), view: Router.current, login: loginId() };
    if (snapshot.role !== 'teacher') return;
    const ctx = { files: [], guard: () => role() === snapshot.role && userId() === snapshot.user && loginId() === snapshot.login && currentCourse() === snapshot.course && Router.current === snapshot.view };
    return openQuestionImport({ values: {} }, ctx);
  }
  return { apply, load, wait, handlers, openImport, setFile, preview: AgentPreview };
})();
