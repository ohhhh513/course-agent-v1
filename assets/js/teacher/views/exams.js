'use strict';

/* 教师试卷工作区；题目编辑复用题库表单，保存目标为试卷自己的题目快照。 */
const TeacherExams = {
  paper: null,
  courseId: '',
  epoch: 0,
  dirty: false,
  busy: false,
  filter: 'all',
  keyword: '',
  types: { single: '单选题', multi: '多选题', judge: '判断题', blank: '填空题' },
  clone(value) { return JSON.parse(JSON.stringify(value)); },
  highlight(value, keyword) {
    const text = String(value ?? ''), needle = String(keyword ?? '').trim();
    if (!needle) return U.esc(text);
    const pattern = new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    let html = '', cursor = 0, match;
    while ((match = pattern.exec(text))) {
      html += U.esc(text.slice(cursor, match.index));
      html += `<mark class="bank-hit">${U.esc(match[0])}</mark>`;
      cursor = match.index + match[0].length;
      if (!match[0].length) pattern.lastIndex++;
    }
    return html + U.esc(text.slice(cursor));
  },
  questionKpIds(question) {
    const rawIds = question.kpIds || question.kp_ids || (question.tags || []).map(tag => tag.kpId || tag.tagId).filter(Boolean);
    const ids = Array.isArray(rawIds) ? rawIds : String(rawIds || '').split(',').filter(Boolean);
    return [...new Set([...ids, ...(question.kpId ? [question.kpId] : [])].map(String))];
  },
  questionKpNames(question, kpById) {
    const tagNames = new Map((question.tags || []).map(tag => [String(tag.kpId || tag.tagId), tag.name]));
    return this.questionKpIds(question).map(id => kpById.get(id) || tagNames.get(id) || id);
  },
  units(value) {
    const text = String(value ?? '');
    if (!/^\d+(\.\d)?$/.test(text) || Number(text) > 10000) return null;
    return Math.round(Number(text) * 10);
  },
  active(epoch = this.epoch) {
    return epoch === this.epoch && this.courseId === API.config.activeCourseId && Question.tab === 'exam';
  },
  render() {
    window.TeacherExamResults?.close();
    if (this.courseId !== API.config.activeCourseId) {
      this.paper = null;
      this.dirty = false;
      this.filter = 'all';
      this.keyword = '';
    }
    this.courseId = API.config.activeCourseId;
    this.epoch++;
    if (this.paper) this.editor(); else this.list();
  },
  async list() {
    window.TeacherExamResults?.close();
    const epoch = ++this.epoch;
    const box = U.$('#qBody');
    box.innerHTML = '<div class="card"><div class="card__body t-dim">正在加载试卷…</div></div>';
    try {
      const result = await API.question.exams.list();
      if (!this.active(epoch)) return;
      box.innerHTML = `<div class="card exam-workspace">
        <div class="card__head row row--wrap"><h3>试卷测验</h3><span class="spacer"></span>
          <button class="btn btn--primary btn--sm" id="examCreate">${icon('plus')} 新建试卷</button></div>
        <div class="card__body exam-list-body">
          <div class="row row--wrap"><select class="select" id="examFilter" aria-label="试卷状态">
            <option value="all">全部试卷</option><option value="draft">草稿</option><option value="published">已发布</option></select>
            <input class="input" id="examSearch" maxlength="120" placeholder="搜索试卷名称" aria-label="搜索试卷名称" style="max-width:320px"></div>
          <div class="exam-list" id="examList"></div>
        </div></div>`;
      const filter = U.$('#examFilter'), search = U.$('#examSearch');
      filter.value = this.filter;
      search.value = this.keyword;
      const paint = () => {
        this.filter = filter.value;
        this.keyword = search.value;
        const items = result.list.filter(p => (this.filter === 'all' || p.status === this.filter) && (p.title || '未命名试卷').includes(this.keyword.trim()));
        U.$('#examList').innerHTML = items.map(p => `<article class="exam-list-card">
          <div class="row row--wrap"><h4>${U.esc(p.title || '未命名试卷')}</h4><span class="badge ${p.status === 'published' ? 'badge--ok' : 'badge--outline'}">${p.status === 'published' ? '已发布' : '草稿'}</span></div>
          <p class="t-dim fz-12">${p.questionCount} 道题 · 总分 ${p.totalScore} · 已分配 ${p.assignedScore} 分</p>
          <p class="t-dim fz-12">更新于 ${U.esc(new Date(p.updatedAt).toLocaleString('zh-CN', {hour12: false}))}</p>
          ${p.issues.length ? `<div class="exam-validation t-dim fz-12">${U.esc(p.issues.slice(0, 3).join('；'))}</div>` : ''}
          <div class="row"><span class="spacer"></span><button class="btn btn--sm" data-exam-edit="${U.esc(p.paperId)}">编辑试卷</button>
          ${p.status === 'published' ? `<button class="btn btn--primary btn--sm" data-exam-results="${U.esc(p.paperId)}">作答详细</button>` : ''}
          ${p.status === 'draft' ? `<button class="btn btn--primary btn--sm" data-exam-publish="${U.esc(p.paperId)}" ${p.ready ? '' : 'disabled'} title="${p.ready ? '发布试卷' : U.esc(p.issues.join('；'))}">发布</button>` : ''}</div></article>`).join('') || '<div class="empty t-dim" style="padding:40px;text-align:center">暂无符合条件的试卷，点击“新建试卷”开始组卷。</div>';
      };
      paint();
      filter.addEventListener('change', paint);
      search.addEventListener('input', paint);
      U.$('#examCreate').onclick = () => {
        this.paper = { title: '', totalScore: 100, scoreMode: 'auto', status: 'draft', revision: 0, items: [] };
        this.dirty = true;
        this.editor();
      };
      U.$('#examList').onclick = async e => {
        const results = e.target.closest('[data-exam-results]');
        if (results && !this.busy) { TeacherExamResults.open(results.dataset.examResults); return; }
        const edit = e.target.closest('[data-exam-edit]'), publish = e.target.closest('[data-exam-publish]');
        const id = edit?.dataset.examEdit || publish?.dataset.examPublish;
        if (!id || this.busy) return;
        if (publish) {
          const paper = result.list.find(p => p.paperId === id);
          this.busy = true;
          publish.disabled = true;
          try {
            await API.question.exams.publish(paper);
            if (this.active(epoch)) { Toast.ok('试卷已发布'); this.list(); }
          } catch (err) { if (this.active(epoch)) { Toast.warn(err.message); publish.disabled = false; } }
          finally { this.busy = false; }
          return;
        }
        edit.disabled = true;
        this.busy = true;
        try {
          const paper = await API.question.exams.detail(id);
          if (this.active(epoch)) { this.paper = paper; this.dirty = false; this.editor(); }
        } catch (err) { if (this.active(epoch)) { Toast.warn(err.message); edit.disabled = false; } }
        finally { this.busy = false; if (this.paper && this.active()) this.paintValidation(); }
      };
    } catch (err) {
      if (this.active(epoch)) box.innerHTML = `<div class="card"><div class="card__body">${U.esc(err.message || '试卷加载失败')}<button class="btn btn--sm" id="examRetry">重试</button></div></div>`;
      U.$('#examRetry')?.addEventListener('click', () => this.list());
    }
  },
  distribute() {
    const total = this.units(this.paper.totalScore), count = this.paper.items.length;
    if (total === null || total <= 0 || !count || this.paper.scoreMode !== 'auto') return;
    const step = total % 10 === 0 && total >= count * 10 ? 10 : 1;
    const base = Math.floor(total / step / count), remainder = (total / step) % count;
    this.paper.items.forEach((q, i) => { q.score = (base + (i >= count - remainder ? 1 : 0)) * step / 10; });
  },
  issues() {
    const paper = this.paper, errors = [];
    const total = this.units(paper.totalScore);
    if (!paper.title.trim()) errors.push('请填写试卷名称');
    if (total === null || total <= 0) errors.push('总分须大于零，最多一位小数');
    if (!paper.items.length) errors.push('请至少添加一道题目');
    let assigned = 0;
    paper.items.forEach((item, index) => {
      const score = this.units(item.score), q = item.question;
      if (score === null || score <= 0) errors.push(`第 ${index + 1} 题分值须大于零，最多一位小数`);
      else assigned += score;
      if (!q.stem?.trim() || !q.answer?.trim() || !(q.kpIds || q.kp_ids || []).length) errors.push(`第 ${index + 1} 题请补全题干、答案和知识点`);
    });
    if (total !== null && assigned !== total) errors.push(`已分配 ${assigned / 10} 分，${assigned < total ? '还差' : '超出'} ${Math.abs(total - assigned) / 10} 分`);
    return { errors, assigned, total };
  },
  editor() {
    const epoch = ++this.epoch;
    const box = U.$('#qBody'), paper = this.paper;
    box.innerHTML = `<div class="card exam-workspace">
      <div class="card__head row row--wrap"><button class="btn btn--ghost btn--sm" id="examBack">${icon('arrowLeft')} 试卷列表</button>
        <h3>${paper.status === 'published' ? '编辑已发布试卷' : '编辑试卷'}</h3><span class="spacer"></span><span class="badge badge--outline">${paper.status === 'published' ? '已发布' : '草稿'}</span></div>
      <div class="card__body exam-editor-body"><fieldset class="exam-fields" id="examFields">
        <div class="exam-settings">
          <label class="stack"><span class="fz-12 t-dim">试卷名称</span><input class="input" id="examTitle" maxlength="120" placeholder="例如：第三章阶段测验" value="${U.esc(paper.title)}"></label>
          <label class="stack"><span class="fz-12 t-dim">总分</span><input class="input" id="examTotal" type="number" min="0.1" max="10000" step="0.1" value="${U.esc(paper.totalScore)}"></label>
          <label class="stack"><span class="fz-12 t-dim">分值分配</span><select class="select" id="examScoreMode"><option value="auto">自动平均分配</option><option value="manual">手动分配</option></select></label>
        </div>
        <div class="row row--wrap" style="margin:14px 0"><button class="btn btn--sm" id="examPick">${icon('folder')} 从题库选题</button><button class="btn btn--sm" id="examNewQuestion">${icon('pencil')} 自己出题</button><span class="spacer"></span><span class="t-dim fz-12">最多 200 题；试卷内编辑不会修改原题。</span></div>
        <div class="exam-items" id="examItems"></div>
      </fieldset></div>
      <div class="exam-footer"><div id="examValidation" aria-live="polite"></div><span class="spacer"></span>
        <button class="btn" id="examSave">${paper.status === 'published' ? '保存修改' : '保存草稿'}</button>
        ${paper.status !== 'published' ? '<button class="btn btn--primary" id="examPublish">发布试卷</button>' : ''}</div>
    </div>`;
    U.$('#examScoreMode').value = paper.scoreMode;
    U.$('#examTitle').oninput = e => { paper.title = e.target.value; this.dirty = true; this.paintValidation(); };
    U.$('#examTotal').oninput = e => { paper.totalScore = e.target.value; this.dirty = true; this.distribute(); this.paintItems(); };
    U.$('#examScoreMode').onchange = e => { paper.scoreMode = e.target.value; this.dirty = true; this.distribute(); this.paintItems(); };
    U.$('#examBack').onclick = () => this.back();
    U.$('#examSave').onclick = () => this.save(false);
    U.$('#examPublish')?.addEventListener('click', () => this.save(true));
    U.$('#examPick').onclick = () => this.pick();
    U.$('#examNewQuestion').onclick = () => {
      if (paper.items.length >= 200) { Toast.warn('每份试卷最多 200 道题'); return; }
      openNewQuestionModal(null, { title: '试卷 · 新建题目', onSave: q => {
        if (!this.active(epoch) || this.paper !== paper) throw new Error('试卷已切换，请重新打开编辑器');
        paper.items.push({id: crypto.randomUUID(), sourceQId: '', score: 0, question: {...q, kpIds: q.kp_ids, figureJson: q.figure_json || null}});
        this.dirty = true; this.distribute(); this.paintItems();
        Toast.ok('题目已加入当前试卷', '保存试卷后会保留，不会加入题库或单题草稿箱');
      }});
    };
    this.paintItems();
  },
  paintValidation() {
    const { errors, assigned, total } = this.issues();
    U.$('#examValidation').innerHTML = `<b>${this.paper.items.length} 题 · 已分配 ${assigned / 10} / ${total === null ? '—' : total / 10} 分</b><div class="fz-12 ${errors.length ? 't-dim' : ''}">${U.esc(errors.length ? errors.slice(0, 3).join('；') : '分值已分配完成，可以发布')}${this.dirty ? ' · 有未保存的修改' : ''}</div>`;
    if (U.$('#examPublish')) U.$('#examPublish').disabled = this.busy || errors.length > 0;
    U.$('#examSave').disabled = this.busy || (this.paper.status === 'published' && errors.length > 0);
  },
  paintItems() {
    const box = U.$('#examItems'), items = this.paper.items, epoch = this.epoch;
    box.innerHTML = items.map((item, i) => `<article class="exam-question" data-item="${U.esc(item.id)}">
      <div class="row row--wrap"><b>第 ${i + 1} 题</b><span class="badge badge--outline">${U.esc(this.types[item.question.type] || item.question.type)}</span><span class="t-dim fz-12">${item.sourceQId ? '来自题库' : '试卷新题'}</span><span class="spacer"></span>
        <label class="row fz-12">分值 <input class="input exam-score" data-score="${U.esc(item.id)}" aria-label="第 ${i + 1} 题分值" type="number" min="0.1" max="10000" step="0.1" value="${U.esc(item.score)}" ${this.paper.scoreMode === 'auto' ? 'readonly' : ''}> 分</label></div>
      <div class="exam-stem">${U.esc(item.question.stem)}</div>
      <details><summary class="t-dim fz-12">查看选项、答案与解析</summary><div class="exam-question-detail">
        <div data-exam-figure></div>
        ${item.question.type === 'blank' ? '' : (item.question.options || []).map(o => `<div>${U.esc(o.key)}. ${U.esc(o.text)}</div>`).join('')}
        <div><b>答案：</b>${U.esc(item.question.answer)}</div><div class="exam-stem"><b>解析：</b>${U.esc(item.question.analysis || '暂无解析')}</div></div></details>
      <div class="row" style="margin-top:10px"><button class="btn btn--xs" data-item-action="edit">编辑</button><button class="btn btn--xs" data-item-action="up" ${i === 0 ? 'disabled' : ''}>上移</button><button class="btn btn--xs" data-item-action="down" ${i === items.length - 1 ? 'disabled' : ''}>下移</button><span class="spacer"></span><button class="btn btn--ghost btn--xs" data-item-action="remove">移除</button></div>
    </article>`).join('') || '<div class="empty t-dim" style="padding:36px;text-align:center">先从题库选择题目，或点击“自己出题”。</div>';
    box.oninput = e => {
      if (!e.target.matches('[data-score]')) return;
      const item = items.find(q => q.id === e.target.dataset.score);
      item.score = e.target.value;
      this.dirty = true; this.paintValidation();
    };
    box.onclick = e => {
      const button = e.target.closest('[data-item-action]');
      if (!button || this.busy) return;
      const id = button.closest('[data-item]').dataset.item, index = items.findIndex(i => i.id === id), item = items[index];
      if (button.dataset.itemAction === 'edit') {
        const paper = this.paper;
        openNewQuestionModal(null, { title: '试卷 · 编辑题目', initial: this.clone(item.question), onSave: q => {
          if (!this.active(epoch) || paper !== this.paper) throw new Error('试卷已切换，请重新打开编辑器');
          item.question = {...q, kpIds: q.kp_ids, figureJson: q.figure_json || null};
          this.dirty = true; this.paintItems();
        }});
        return;
      }
      if (button.dataset.itemAction === 'remove') items.splice(index, 1);
      else {
        const target = index + (button.dataset.itemAction === 'up' ? -1 : 1);
        if (target < 0 || target >= items.length) return;
        [items[index], items[target]] = [items[target], items[index]];
      }
      this.dirty = true; this.distribute(); this.paintItems();
    };
    box.querySelectorAll('[data-item]').forEach(card => {
      const item = items.find(q => q.id === card.dataset.item), figure = item.question.figureJson;
      if (!figure) return;
      const figureBox = card.querySelector('[data-exam-figure]');
      if (figure.imageUrl || figure.image_url) U.mountQuestionImage(figureBox, figure.imageUrl || figure.image_url);
      else if (window.DsFigure) {
        if (figure.graph) {
          const mainFigure = document.createElement('div');
          figureBox.appendChild(mainFigure);
          DsFigure.mount(mainFigure, figure.graph);
        }
        if (figure.options_graph) {
          const optionsFigure = document.createElement('div');
          figureBox.appendChild(optionsFigure);
          DsFigure.mountOptions(optionsFigure, figure.options_graph);
        }
      }
    });
    this.paintValidation();
  },
  async save(publish, returnToList = false) {
    if (this.busy) return false;
    const epoch = this.epoch, paper = this.paper;
    const total = this.units(paper.totalScore);
    if (total === null || total <= 0 || paper.items.some(i => this.units(i.score) === null)) {
      Toast.warn('请填写有效分值，最多保留一位小数'); return false;
    }
    const {errors} = this.issues();
    if ((publish || paper.status === 'published') && errors.length) { Toast.warn(errors[0]); return false; }
    this.busy = true;
    U.$('#examFields').disabled = true;
    U.$('#examBack').disabled = true;
    this.paintValidation();
    try {
      const saved = await API.question.exams.save({...paper, totalScore: total / 10, publish});
      if (!this.active(epoch)) return false;
      this.paper = saved;
      this.dirty = false;
      Toast.ok(saved.status === 'published' ? '试卷已发布并保存' : '草稿已保存');
      if (returnToList) { this.paper = null; this.list(); } else this.editor();
      return true;
    } catch (err) { if (this.active(epoch)) Toast.warn(err.message || '保存失败'); return false; }
    finally {
      this.busy = false;
      if (this.paper && this.active()) {
        U.$('#examFields').disabled = false;
        U.$('#examBack').disabled = false;
        this.paintValidation();
      }
    }
  },
  back() {
    if (this.busy) return;
    if (!this.dirty) { this.paper = null; this.list(); return; }
    Modal.open({title: '有未保存的修改', closeOnBackdrop: false, body: '<p>保存草稿后返回列表，或放弃本次尚未保存的修改。</p>',
      footer: '<button class="btn" data-close>继续编辑</button><button class="btn" id="examDiscard">放弃修改</button><button class="btn btn--primary" id="examSaveBack">保存并返回</button>',
      onMount: (ov, close) => {
        ov.querySelector('#examDiscard').onclick = () => { close(); this.paper = null; this.dirty = false; this.list(); };
        ov.querySelector('#examSaveBack').onclick = async () => { if (await this.save(false, true)) close(); };
      }});
  },
  openPickDetail(question, structureData) {
    const typeName = this.types[question.type] || question.type || '题目';
    const kpById = new Map((structureData?.kpOptions || []).map(kp => [String(kp.id), kp.name]));
    const kpNames = this.questionKpNames(question, kpById);
    const chapterName = question.chapter || (structureData?.chapterOptions || []).find(ch => ch.id === question.chapterId)?.name || '未分章';
    const blank = question.type === 'blank';
    const options = Array.isArray(question.options) ? question.options : [];
    const optionHtml = blank
      ? `<div class="callout" style="white-space:pre-wrap">${U.esc(question.answer || '未填写')}</div>`
      : `<div class="opts opts--readonly">${options.map(option => `<div class="opt${option.right ? ' is-right' : ''}">
          <span class="opt__key">${U.esc(option.key || '')}</span><span style="flex:1;white-space:pre-wrap">${U.esc(option.text || '')}</span>
          ${option.right ? '<span class="opt__flag badge badge--ok">正确答案</span>' : ''}</div>`).join('') || '<div class="t-dim fz-13">没有选项</div>'}</div>`;
    Modal.open({title: `题目详情 · ${U.esc(question.qId || '')}`, size: 'wide',
      body: `<div class="stack" style="gap:14px">
        <div class="row row--wrap fz-12 t-dim"><span class="badge badge--outline mono">${U.esc(question.qId || '')}</span><span class="badge badge--brand">${U.esc(typeName)}</span><span class="badge badge--outline">${U.esc(chapterName)}</span>${question.difficulty ? `<span class="badge badge--outline">难度 ${U.stars(question.difficulty)}</span>` : ''}</div>
        <div><div class="fz-12 t-dim" style="margin-bottom:6px">考查知识点</div><div class="row row--wrap">${kpNames.map(name => `<span class="badge badge--outline">${U.esc(name)}</span>`).join('') || '<span class="t-dim">未标注</span>'}</div></div>
        <div><div class="fz-12 t-dim" style="margin-bottom:6px">题干</div><div class="callout" style="white-space:pre-wrap">${U.esc(question.stem || '')}</div></div>
        <div id="examPickDetailFigure"></div>
        <div><div class="fz-12 t-dim" style="margin-bottom:6px">${blank ? '答案' : '选项'}</div>${optionHtml}</div>
        ${blank ? '' : `<div><div class="fz-12 t-dim" style="margin-bottom:6px">答案</div><div class="callout" style="white-space:pre-wrap">${U.esc(question.answer || '未填写')}</div></div>`}
        <div><div class="fz-12 t-dim" style="margin-bottom:6px">解析</div><div class="callout" style="white-space:pre-wrap">${U.esc(question.analysis || '暂无解析')}</div></div>
      </div>`,
      footer: '<button class="btn" data-close>关闭</button>',
      onMount: ov => {
        const figure = question.figureJson || question.figure_json;
        const figureBox = ov.querySelector('#examPickDetailFigure');
        if (!figure || !figureBox) return;
        if (figure.imageUrl || figure.image_url) U.mountQuestionImage(figureBox, figure.imageUrl || figure.image_url);
        else if (window.DsFigure) {
          if (figure.graph) DsFigure.mount(figureBox, figure.graph);
          if (figure.options_graph) DsFigure.mountOptions(figureBox, figure.options_graph);
        }
      }});
  },
  pick() {
    const epoch = this.epoch, paper = this.paper;
    let page = 1, generation = 0, structureData = null;
    const selectedKps = new Set();
    const existing = new Set(paper.items.map(i => i.sourceQId).filter(Boolean));
    Modal.open({title: '从当前课程题库选题', closeOnBackdrop: false, size: 'wide',
      body: `<form class="row row--wrap" id="examBankSearch">
        <input class="input" id="examBankKeyword" placeholder="搜索题干、章节或知识点" aria-label="搜索题库" style="flex:1;min-width:200px">
        <select class="select select--visible-arrow" id="examBankChapter" aria-label="筛选章节"><option value="">全部章节</option></select>
        <details class="exam-kp-picker" id="examBankKp">
          <summary class="select exam-kp-picker__toggle" aria-label="筛选知识点（可多选）"><span data-exam-kp-label>全部知识点</span>${icon('chevronDown')}</summary>
          <div class="exam-kp-picker__panel">
            <div class="row fz-12"><b>知识点（可多选）</b><span class="spacer"></span><button class="btn btn--ghost btn--xs" type="button" data-exam-kp-clear disabled>清空</button></div>
            <div class="exam-kp-picker__options" data-exam-kp-options>正在加载知识点…</div>
          </div>
        </details>
        <select class="select select--visible-arrow" id="examBankType" aria-label="筛选题型"><option value="">全部题型</option>${Object.entries(this.types).map(([key, text]) => `<option value="${key}">${text}</option>`).join('')}</select>
        <button class="btn" type="submit">搜索</button></form>
        <div class="exam-bank-list" id="examBankList"></div><div class="row" id="examBankPages"></div>`,
      footer: '<span class="t-dim fz-12" id="examPickCount">点击题目查看详情，使用右侧按钮加入试卷。</span><button class="btn" data-close>完成</button>',
      onMount: ov => {
        const chapterSelect = ov.querySelector('#examBankChapter'), kpPicker = ov.querySelector('#examBankKp');
        const syncKpLabel = () => {
          kpPicker.querySelector('[data-exam-kp-label]').textContent = selectedKps.size ? `已选 ${selectedKps.size} 个知识点` : '全部知识点';
          kpPicker.querySelector('[data-exam-kp-clear]').disabled = selectedKps.size === 0;
        };
        const renderKpOptions = () => {
          if (!structureData) return;
          const chapter = (structureData.chapterOptions || []).find(ch => ch.id === chapterSelect.value);
          const options = (structureData.kpOptions || []).filter(kp => !chapter || kp.chapter === chapter.name);
          const allowedIds = new Set(options.map(kp => String(kp.id)));
          for (const id of selectedKps) if (!allowedIds.has(id)) selectedKps.delete(id);
          kpPicker.querySelector('[data-exam-kp-options]').innerHTML = options.map(kp => `<label><input type="checkbox" data-exam-kp value="${U.esc(kp.id)}" ${selectedKps.has(String(kp.id)) ? 'checked' : ''}><span>${U.esc(kp.name)}</span></label>`).join('') || '<span class="t-dim fz-12">当前章节暂无知识点</span>';
          syncKpLabel();
        };
        API.teacher.structure().then(data => {
          if (!ov.isConnected || !this.active(epoch)) return;
          structureData = data;
          chapterSelect.innerHTML = '<option value="">全部章节</option>' + (data.chapterOptions || []).map(ch => `<option value="${U.esc(ch.id)}">${U.esc(ch.name)}</option>`).join('');
          renderKpOptions();
        }).catch(err => {
          if (ov.isConnected) {
            kpPicker.querySelector('[data-exam-kp-options]').textContent = '知识点加载失败，请重新打开选题';
            Toast.warn(err.message || '章节与知识点加载失败');
          }
        });
        const addQuestion = (question, button) => {
          if (!this.active(epoch) || this.paper !== paper) { Toast.warn('试卷已切换，请重新打开选题'); return; }
          if (existing.has(question.qId)) return;
          if (paper.items.length >= 200) { Toast.warn('每份试卷最多 200 道题'); return; }
          paper.items.push({id: crypto.randomUUID(), sourceQId: question.qId, score: 0, question: this.clone(question)});
          existing.add(question.qId);
          this.dirty = true; this.distribute(); this.paintItems();
          if (button) { button.disabled = true; button.textContent = '已添加'; }
          ov.querySelector('#examPickCount').textContent = `当前试卷 ${paper.items.length} / 200 题`;
          if (paper.items.length >= 200) ov.querySelectorAll('[data-bank-add]').forEach(item => { item.disabled = true; });
          Toast.ok('题目已加入试卷');
        };
        const load = async () => {
          const request = ++generation;
          ov.querySelector('#examBankList').textContent = '正在加载题库…';
          try {
            const keyword = ov.querySelector('#examBankKeyword').value.trim();
            const result = await API.question.bank({page, size: 10, status: 'published', type: ov.querySelector('#examBankType').value, keyword,
              chapterId: chapterSelect.value, knowledgeIds: [...selectedKps].join(',')});
            if (!ov.isConnected || request !== generation || !this.active(epoch)) return;
            const allowed = result.list.filter(q => this.types[q.type]);
            const kpById = new Map((structureData?.kpOptions || []).map(kp => [String(kp.id), kp.name]));
            const detailMap = new Map(allowed.map(q => [String(q.qId), q]));
            ov.querySelector('#examBankList').innerHTML = allowed.map(q => {
              const kps = this.questionKpNames(q, kpById);
              return `<article class="exam-bank-item"><button type="button" class="exam-bank-question" data-bank-detail="${U.esc(q.qId)}" aria-label="查看 ${U.esc(q.qId)} 题目详情">
                <span class="row row--wrap"><span class="badge badge--outline">${U.esc(this.types[q.type])}</span><span class="mono fz-12 t-dim">${U.esc(q.qId)}</span></span>
                <span class="exam-bank-stem">${this.highlight(q.stem, keyword)}</span>
                <span class="fz-12 t-dim">章节：${this.highlight(q.chapter || '未分章', keyword)}</span>
                <span class="row row--wrap fz-12 t-dim">知识点：${kps.map(name => `<span class="badge badge--outline">${this.highlight(name, keyword)}</span>`).join('') || '未标注'}</span>
              </button><button type="button" class="btn btn--sm ${existing.has(q.qId) ? '' : 'btn--primary'}" data-bank-add="${U.esc(q.qId)}" ${existing.has(q.qId) ? 'disabled' : paper.items.length >= 200 ? 'disabled' : ''}>${existing.has(q.qId) ? '已添加' : '添加到试卷'}</button></article>`;
            }).join('') || '<div class="t-dim" style="padding:24px">当前条件没有可选题目。</div>';
            ov.querySelector('#examBankList').onclick = e => {
              const detailButton = e.target.closest('[data-bank-detail]');
              if (detailButton) {
                const question = detailMap.get(detailButton.dataset.bankDetail);
                if (question) this.openPickDetail(question, structureData);
                return;
              }
              const addButton = e.target.closest('[data-bank-add]');
              if (addButton) {
                const question = detailMap.get(addButton.dataset.bankAdd);
                if (question) addQuestion(question, addButton);
              }
            };
            const pages = Math.max(1, Math.ceil(result.total / 10));
            ov.querySelector('#examBankPages').innerHTML = `<span class="t-dim fz-12">第 ${page} / ${pages} 页 · 共 ${result.total} 题</span><span class="spacer"></span><button class="btn btn--sm" id="examBankPrev" ${page <= 1 ? 'disabled' : ''}>上一页</button><button class="btn btn--sm" id="examBankNext" ${page >= pages ? 'disabled' : ''}>下一页</button>`;
            ov.querySelector('#examBankPrev').onclick = () => { page--; load(); };
            ov.querySelector('#examBankNext').onclick = () => { page++; load(); };
          } catch (err) { if (ov.isConnected && request === generation) ov.querySelector('#examBankList').textContent = err.message || '题库加载失败，请重新搜索'; }
        };
        ov.querySelector('#examBankSearch').onsubmit = e => { e.preventDefault(); page = 1; load(); };
        chapterSelect.onchange = () => { renderKpOptions(); page = 1; load(); };
        kpPicker.addEventListener('change', e => {
          if (!e.target.matches('[data-exam-kp]')) return;
          if (e.target.checked) selectedKps.add(e.target.value);
          else selectedKps.delete(e.target.value);
          syncKpLabel(); page = 1; load();
        });
        kpPicker.querySelector('[data-exam-kp-clear]').onclick = () => {
          selectedKps.clear(); renderKpOptions(); page = 1; load();
        };
        ov.addEventListener('click', e => { if (!kpPicker.contains(e.target)) kpPicker.open = false; });
        ov.querySelector('#examBankType').onchange = () => { page = 1; load(); };
        load();
      }});
  },
};

window.addEventListener('beforeunload', e => {
  if (TeacherExams.dirty && TeacherExams.courseId === API.config.activeCourseId) { e.preventDefault(); e.returnValue = ''; }
});
