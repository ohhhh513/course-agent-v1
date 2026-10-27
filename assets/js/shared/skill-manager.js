'use strict';

/* 教师课程技能编辑与管理员停用入口；权限和发布状态由服务端校验。 */
const CourseSkillManager = (() => {
  const fields = ['name', 'baseSkillId', 'purpose', 'steps', 'outputFormat', 'example'];
  const statusText = item => item.blocked ? '管理员已停用' : item.enabled ? '已发布' : item.publishedVersion ? '已停用' : '草稿';
  const errorText = error => error.status === 404 ? '技能管理接口暂不可用，请更新并重启服务。' : error.message || '操作失败，请稍后重试';

  function messageHtml(message) {
    const isUser = message.role === 'user';
    const body = isUser ? U.esc(message.content) : AgentChatView.mdToHtml(message.content, { escapeHtml: true });
    return `<div class="skill-trial__message ${isUser ? 'is-user' : ''}"><b>${isUser ? '我' : '技能'}</b><div class="skill-trial__body ${isUser ? 'is-plain' : ''}">${body}</div></div>`;
  }

  function open(role, onChanged) {
    if (role === 'admin') return openAdmin(onChanged);
    if (role !== 'teacher') return;
    const courseId = API.config.activeCourseId;
    if (!courseId) return Toast.info('请先选择课程');
    const state = { list: [], templates: [], item: null, snapshot: '', busy: false, history: [], trialRevision: null, closed: false };
    const modal = Modal.open({
      title: '本课程的定制技能', closeOnBackdrop: false, footer: null,
      body: `<div class="skill-workbench">
        <aside class="skill-workbench__sidebar"><button class="btn btn--primary btn--sm" id="skillNew" disabled>${icon('plus')} 创建技能</button><div id="skillRecords" class="skill-records"><p class="t-dim">正在加载…</p></div></aside>
        <section class="skill-editor" id="skillEditor"><p class="t-dim">正在加载…</p></section>
        <section class="skill-trial"><header class="skill-trial__header"><h4>试用对话</h4><p class="skill-trial__name">当前技能：<strong id="skillTrialName">新建技能</strong></p></header><p class="fz-12 t-dim">使用当前编辑的草稿，发送时自动保存。仅查询本课资料和题目，不读取学生个人学情或执行页面操作。</p><div class="skill-trial__messages" id="skillTrialMessages" aria-live="polite"><p class="t-dim">完成配置后，在这里试用效果。</p></div><label><span class="fz-12">测试问题</span><textarea class="input" id="skillTrialQuestion" rows="3" maxlength="2000" aria-describedby="skillTrialKeyboard" placeholder="例如：请用生活中的例子解释栈和队列"></textarea></label><div class="skill-trial__send"><span class="fz-12 t-dim" id="skillTrialKeyboard">Enter 发送，Shift+Enter 换行</span><button class="btn btn--primary" id="skillTrialSend" disabled>发送</button></div><p id="skillNotice" class="skill-notice" role="status"></p></section>
      </div>`,
      beforeClose: () => !state.busy && (!dirty() || window.confirm('草稿尚未保存，确定关闭并放弃这些修改吗？')),
      onClose: () => { state.closed = true; },
    });
    const root = modal.el;
    const $ = selector => root.querySelector(selector);
    function currentCourse() {
      if (API.config.activeCourseId !== courseId) throw new Error('当前课程已切换，请关闭后在新课程重新打开技能管理。');
    }
    function readForm() {
      if (state.designer) return state.designer.readDraft();
      return Object.fromEntries(fields.map(key => [key, $(`[name="${key}"]`)?.value.trim() || '']));
    }
    function dirty() { return Boolean(state.snapshot && JSON.stringify(readForm()) !== state.snapshot); }
    function notice(text, failed = false) {
      $('#skillNotice').textContent = text;
      $('#skillNotice').classList.toggle('t-danger', failed);
    }
    function busy(value) {
      state.busy = value;
      root.querySelectorAll('button, input, select, textarea').forEach(el => { el.disabled = value; });
      if (!value) root.querySelectorAll('[data-designer-disabled]').forEach(el => { el.disabled = true; });
      if (!value && state.item?.blocked) $('#skillPublish').disabled = true;
      if (!value && !state.item?.enabled && $('#skillDisable')) $('#skillDisable').disabled = true;
    }
    function list() {
      $('#skillRecords').innerHTML = state.list.length ? state.list.map(item => `<button type="button" class="skill-record ${state.item?.id === item.id ? 'is-active' : ''}" data-skill-record="${U.esc(item.id)}"><b>${U.esc(item.draft.name)}</b><span>${statusText(item)}${item.publishedVersion ? ' · v' + item.publishedVersion : ''}</span></button>`).join('') : '<p class="fz-12 t-dim">还没有技能，点击上方按钮创建。</p>';
    }
    function editor(item, viewState) {
      state.item = item;
      state.history = [];
      state.trialRevision = null;
      const draft = item?.draft || { name: '', baseSkillId: 'course_qa', purpose: '', steps: '', outputFormat: '', example: '' };
      $('#skillEditor').innerHTML = `<form id="skillForm" class="skill-editor__form" novalidate>
          <div class="skill-editor__content"><div class="row"><h4>${item ? '编辑技能' : '创建技能'}</h4><span class="spacer"></span><span class="badge">${item ? statusText(item) : '新草稿'}</span></div>
            <p class="fz-12 t-dim">发布后，本课程学生可在智能体加号菜单中选择。修改草稿不会覆盖已发布版本。</p>
            <div id="skillDesigner"></div>
          </div>
          <div class="skill-editor__actions"><div id="skillGuideNavigation" class="skill-guide-navigation"></div><div class="skill-editor__save-actions"><button class="btn btn--outline" type="submit" id="skillSave">保存草稿</button><button class="btn btn--primary" type="button" id="skillPublish" ${item?.blocked ? 'disabled' : ''}>发布</button>${item?.enabled ? '<button class="btn btn--ghost" type="button" id="skillDisable">停用</button>' : ''}</div></div>
        </form>`;
      state.designer = SkillDesigner.mount($('#skillDesigner'), {
        draft, availableTemplates: state.templates, viewState, navigationHost: $('#skillGuideNavigation'),
        onChange: value => {
          $('#skillTrialName').textContent = value.name.trim() || '新建技能';
        },
      });
      state.snapshot = JSON.stringify(readForm());
      $('#skillTrialMessages').innerHTML = '<p class="t-dim">可以连续提问；切换技能或保存修改后重新开始试用。</p>';
      $('#skillTrialSend').disabled = false;
      $('#skillForm').addEventListener('submit', event => { event.preventDefault(); operate(() => save()); });
      $('#skillPublish').addEventListener('click', () => {
        operate(async () => {
          await save();
          const result = await API.skills.teacher.publish(state.item.id, state.item.revision, courseId);
          accept(result);
          notice(`已发布 v${result.publishedVersion}，学生重新打开加号菜单即可看到。`);
          onChanged?.();
        });
      });
      $('#skillDisable')?.addEventListener('click', () => {
        if (!window.confirm('停用后，学生不能再使用这个技能；草稿和已发布版本会保留。确定停用吗？')) return;
        operate(async () => {
          if (dirty()) throw new Error('请先保存草稿，或重新选择当前技能放弃修改，再停用。');
          accept(await API.skills.teacher.disable(state.item.id, state.item.revision, courseId));
          notice('技能已停用。');
          onChanged?.();
        });
      });
      list();
      if (state.busy) busy(true);
    }
    function accept(item) {
      const viewState = state.designer?.viewState();
      const sameDraft = JSON.stringify(state.item?.draft) === JSON.stringify(item.draft);
      const index = state.list.findIndex(value => value.id === item.id);
      if (index < 0) state.list.unshift(item); else state.list[index] = item;
      // 保留试用对话；只有草稿内容变化时才开启新的试用。
      const previousHistory = state.history;
      const previousMessages = $('#skillTrialMessages').innerHTML;
      editor(item, viewState);
      if (sameDraft && previousHistory.length) {
        state.history = previousHistory;
        state.trialRevision = item.revision;
        $('#skillTrialMessages').innerHTML = previousMessages;
      }
    }
    async function save() {
      currentCourse();
      const invalid = state.designer?.validate();
      if (invalid) throw new Error(invalid);
      const values = readForm();
      if (!values.name || !values.purpose || !values.steps) throw new Error('请填写技能名称、用途和处理步骤。');
      if (state.item && !dirty()) return state.item;
      const draft = readForm();
      const result = state.item
        ? await API.skills.teacher.save(state.item.id, { ...draft, revision: state.item.revision }, courseId)
        : await API.skills.teacher.create(draft, courseId);
      accept(result);
      notice('草稿已保存，发布后学生才能使用。');
      return result;
    }
    async function operate(task) {
      if (state.busy || state.closed) return;
      try { currentCourse(); busy(true); notice(''); await task(); }
      catch (error) {
        notice(errorText(error) + (error.status === 409 ? ' 当前输入已保留，请关闭后重新打开以查看最新版本。' : ''), true);
      } finally { if (!state.closed) busy(false); }
    }
    $('#skillNew').addEventListener('click', () => {
      if (!dirty() || window.confirm('当前草稿尚未保存，确定放弃修改并创建新技能吗？')) { editor(null); notice(''); }
    });
    $('#skillRecords').addEventListener('click', event => {
      const button = event.target.closest('[data-skill-record]');
      if (button && (!dirty() || window.confirm('当前草稿尚未保存，确定切换技能吗？'))) {
        editor(state.list.find(item => item.id === button.dataset.skillRecord)); notice('');
      }
    });
    function sendTrial() { return operate(async () => {
      const question = $('#skillTrialQuestion').value.trim();
      if (!question) throw new Error('请先输入测试问题。');
      await save();
      notice('正在发送…');
      const result = await API.skills.teacher.trial(state.item.id, { revision: state.item.revision, question, history: state.history.slice(-10) }, courseId);
      state.history.push({ role: 'user', content: question }, { role: 'assistant', content: result.text });
      state.trialRevision = state.item.revision;
      $('#skillTrialMessages').innerHTML = state.history.map(messageHtml).join('');
      $('#skillTrialMessages').scrollTop = $('#skillTrialMessages').scrollHeight;
      $('#skillTrialQuestion').value = '';
      notice('试用完成；确认效果后再发布给学生。');
    }); }
    $('#skillTrialSend').addEventListener('click', sendTrial);
    $('#skillTrialQuestion').addEventListener('keydown', event => {
      if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      sendTrial();
    });
    API.skills.teacher.list(courseId).then(result => {
      if (state.closed) return;
      currentCourse();
      state.list = result.list || [];
      state.templates = result.templates || [];
      if (!state.templates.length) throw new Error('当前没有可用的基础技能。');
      $('#skillNew').disabled = false;
      editor(null);
    }).catch(error => {
      if (!state.closed) { $('#skillRecords').textContent = '加载失败'; $('#skillEditor').innerHTML = '<p class="t-dim">暂时无法加载技能管理。</p>'; notice(errorText(error), true); }
    });
    return modal;
  }

  function openAdmin(onChanged) {
    let list = [], busy = false, closed = false;
    const modal = Modal.open({ title: '课程定制技能管理', size: 'lg', closeOnBackdrop: false, footer: null,
      body: '<div class="skill-admin"><input class="input" id="skillAdminSearch" placeholder="搜索技能、课程或教师"><div id="skillAdminList" class="skill-admin__list">正在加载…</div><p id="skillAdminNotice" class="skill-notice" role="status"></p></div>',
      beforeClose: () => !busy, onClose: () => { closed = true; },
    });
    const root = modal.el, $ = selector => root.querySelector(selector);
    function paint() {
      const keyword = $('#skillAdminSearch').value.trim().toLowerCase();
      const selected = list.filter(item => [item.draft.name, item.courseName, item.ownerName].join(' ').toLowerCase().includes(keyword));
      $('#skillAdminList').innerHTML = selected.length ? selected.map(item => `<article class="skill-admin__item"><div><b>${U.esc(item.draft.name)}</b><p class="fz-12 t-dim">${U.esc(item.courseName)} · ${U.esc(item.ownerName)} · ${statusText(item)}</p><p class="fz-12">${U.esc(item.draft.purpose)}</p></div><button class="btn btn--outline btn--sm" data-disable-skill="${U.esc(item.id)}" ${item.blocked || busy ? 'disabled' : ''}>${item.blocked ? '已停用' : '管理员停用'}</button></article>`).join('') : '<p class="t-dim">没有匹配的定制技能。</p>';
    }
    $('#skillAdminSearch').addEventListener('input', paint);
    $('#skillAdminList').addEventListener('click', async event => {
      const button = event.target.closest('[data-disable-skill]');
      if (!button || busy) return;
      const item = list.find(value => value.id === button.dataset.disableSkill);
      if (!item || !window.confirm(`停用「${item.draft.name}」后，学生将不能使用，教师也不能直接重新发布。确定停用吗？`)) return;
      busy = true; paint();
      try {
        const result = await API.skills.admin.disable(item.id, item.revision);
        list = list.map(value => value.id === result.id ? result : value);
        $('#skillAdminNotice').textContent = '已停用。'; onChanged?.();
      } catch (error) { $('#skillAdminNotice').textContent = errorText(error); }
      finally { busy = false; if (!closed) paint(); }
    });
    API.skills.admin.list().then(result => { if (!closed) { list = result.list || []; paint(); } })
      .catch(error => { if (!closed) $('#skillAdminList').textContent = errorText(error); });
    return modal;
  }

  return { open, messageHtml };
})();
