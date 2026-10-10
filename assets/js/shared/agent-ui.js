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

  const reportExecutors = {
    'student-report-create': async (plan, ctx) => {
      await wait(() => find('#genMyReport'), '报告生成按钮', ctx.guard);
      if (!ctx.guard()) return false;
      return MyReport.generate();
    },
    'teacher-report-create': async (plan, ctx) => {
      const course = await wait(() => find('#rgCourse'), '报告配置', ctx.guard);
      if (course.value !== plan.courseId) throw new Error('报告课程已变化，请重新提出生成请求');
      for (const key of ['startDate', 'endDate']) {
        if (plan.values[key] && find(key === 'startDate' ? '#rgStart' : '#rgEnd').value !== plan.values[key]) {
          throw new Error('日期范围未能按要求设置，请在弹窗核对后生成');
        }
      }
      await click('#rgGo', ctx.guard);
      return Report._generating ? await Report._generating : false;
    },
  };

  async function openQuestionImport(plan, ctx) {
    let preview = null;
    let version = 0;
    const values = plan.values || {};
    let selectedKps = new Set(values.kpIds || []);
    const modal = Modal.open({
      title: '导入题目 · 预览与核对', size: 'wide',
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
        root.querySelector('#qiRows').innerHTML = result.questions.map((question, index) => `<section class="card"><div class="card__body"><b>第 ${index + 1} 题</b><textarea class="input" data-qi-field="stem" data-index="${index}">${U.esc(question.stem || '')}</textarea><p>${(question.options || []).map(o => U.esc(o.key + '. ' + o.text)).join('<br>')}</p><label>答案<input class="input" data-qi-field="answer" data-index="${index}" value="${U.esc(question.answer || '')}"></label><label>解析<textarea class="input" data-qi-field="analysis" data-index="${index}">${U.esc(question.analysis || '')}</textarea></label><p class="t-danger">${U.esc((result.errors.find(error => error.index === index) || { errors: [] }).errors.join('；'))}</p></div></section>`).join('');
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
        status.textContent = `成功导入 ${result.success} 题，失败 ${result.failed} 题。${(result.errors || []).join('；')}`;
        preview = null;
        Question.loadBank();
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
    const ctx = { files: options.files || [], allowCourseChange: false, targetView: snapshot.view };
    ctx.guard = () => role() === snapshot.role && userId() === snapshot.userId && loginId() === snapshot.login &&
      (ctx.allowCourseChange || currentCourse() === snapshot.course) && Router.current === ctx.targetView;
    try {
      const spec = (await load()).find(item => item.id === plan.target && item.role === snapshot.role);
      if (!spec || Object.keys(plan.values || {}).some(key => !spec.fields[key])) throw new Error('此操作入口或字段不受支持');
      if (spec.entity && (!plan.object || !plan.object.id)) throw new Error('尚未确定目标对象');
      if (spec.execute && (!reportExecutors[spec.execute] || plan.auto !== true)) throw new Error('生成报告需要明确的操作请求');
      const reportKey = spec.execute ? 'agent-report:' + snapshot.login + ':' + snapshot.userId + ':' + plan.id : '';
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
        sessionStorage.setItem(reportKey, 'started');
        executed.add(plan.id);
        const success = await reportExecutors[spec.execute](plan, ctx);
        sessionStorage.setItem(reportKey, success ? 'done' : 'failed');
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
  return { apply, load, wait, handlers, openImport, setFile };
})();
