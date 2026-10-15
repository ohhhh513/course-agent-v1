'use strict';

/* 学生端试卷测验。作答通过既有试卷接口保存，结算后复用普通 AnswerRecord。 */
const StudentExams = {
  papers: [], query: '', kpFilters: [], testFilter: 'all',
  attempt: null, result: null, index: 0,
  answers: {}, durations: {},
  saveQueue: Promise.resolve(), saveTimer: null, clockTimer: null,
  itemStartedAt: 0, currentDurationBase: 0, attemptStartedAt: 0,
  finishing: false, startingPaperId: '', pendingTarget: null,

  get running() { return !!(this.attempt && this.attempt.status === 'running'); },

  resetCourseContext() {
    clearInterval(this.clockTimer);
    clearTimeout(this.saveTimer);
    this.papers = [];
    this.query = '';
    this.kpFilters = [];
    this.testFilter = 'all';
    this.attempt = null;
    this.result = null;
    this.index = 0;
    this.answers = {};
    this.durations = {};
    this.saveQueue = Promise.resolve();
    this.itemStartedAt = 0;
    this.currentDurationBase = 0;
    this.attemptStartedAt = 0;
    this.finishing = false;
    this.startingPaperId = '';
    this.pendingTarget = null;
  },

  _activeTab() {
    return window.StudentPractice && StudentPractice.tab === 'exam';
  },

  renderList() {
    const box = U.$('#pBody');
    if (!box || !this._activeTab()) return;
    const courseId = API.config.activeCourseId;
    box.innerHTML = '<div class="card"><div class="card__body t-dim">加载已发布试卷…</div></div>';
    API.practice.exams().then(data => {
      if (U.$('#pBody') !== box || !this._activeTab() || API.config.activeCourseId !== courseId) return;
      this.papers = data.list || [];
      const points = new Map();
      this.papers.forEach(paper => (paper.knowledgePoints || []).forEach(kp => {
        if (kp.kpId) points.set(kp.kpId, kp.name || kp.kpId);
      }));
      this.kpFilters = this.kpFilters.filter(id => points.has(id));
      box.innerHTML = `
        <div class="card exam-filters">
          <div class="card__head"><h3>${icon('file')} 试卷测验</h3><span class="badge badge--outline">${data.total || 0} 份已发布试卷</span></div>
          <div class="card__body row exam-filter-row">
            <label class="exam-search"><span class="exam-search__icon">${icon('search2')}</span>
              <input id="examSearch" type="search" value="${U.esc(this.query)}" placeholder="搜索试卷名称或知识点" aria-label="搜索试卷名称或知识点" autocomplete="off"></label>
            <div class="exam-kp-select"><span class="fz-12 t-dim">按知识点筛选（可多选）</span>
              <details class="exam-kp-picker" id="examKpFilter">
                <summary class="exam-select-wrap exam-kp-toggle" aria-label="筛选试卷知识点（可多选）"><span data-exam-kp-label>${this.kpFilters.length ? `已选 ${this.kpFilters.length} 个知识点` : '全部知识点'}</span>${icon('chevronDown')}</summary>
                <div class="exam-kp-picker__panel">
                  <div class="row fz-12"><b>知识点（可多选）</b><span class="spacer"></span><button class="btn btn--ghost btn--xs" type="button" data-exam-kp-clear ${this.kpFilters.length ? '' : 'disabled'}>清空</button></div>
                  <p class="fz-12 t-dim exam-kp-hint">试卷须同时包含全部已选知识点</p>
                  <div class="exam-kp-picker__options">${[...points.entries()].sort((a, b) => a[1].localeCompare(b[1], 'zh')).map(([id, name]) => `<label><input type="checkbox" data-exam-kp value="${U.esc(id)}" ${this.kpFilters.includes(id) ? 'checked' : ''}><span>${U.esc(name)}</span></label>`).join('') || '<span class="fz-12 t-dim">暂无可选知识点</span>'}</div>
                </div>
              </details>
            </div>
            <label class="exam-state-select"><span class="fz-12 t-dim">测验状态</span><span class="exam-select-wrap"><select id="examStateFilter" aria-label="筛选测验状态">
              <option value="all" ${this.testFilter === 'all' ? 'selected' : ''}>全部状态</option>
              <option value="tested" ${this.testFilter === 'tested' ? 'selected' : ''}>已测验</option>
              <option value="pending" ${this.testFilter === 'pending' ? 'selected' : ''}>待测验</option>
            </select>${icon('chevronDown')}</span></label>
          </div>
        </div>
        <div id="examPaperList" class="exam-paper-list" aria-live="polite"></div>`;
      U.$('#examSearch', box).addEventListener('input', event => {
        this.query = event.target.value.trim();
        this.renderPaperCards();
      });
      const kpPicker = U.$('#examKpFilter', box);
      const syncKpSelection = () => {
        kpPicker.querySelector('[data-exam-kp-label]').textContent = this.kpFilters.length ? `已选 ${this.kpFilters.length} 个知识点` : '全部知识点';
        kpPicker.querySelector('[data-exam-kp-clear]').disabled = this.kpFilters.length === 0;
        this.renderPaperCards();
      };
      kpPicker.addEventListener('change', event => {
        if (!event.target.matches('[data-exam-kp]')) return;
        this.kpFilters = [...kpPicker.querySelectorAll('[data-exam-kp]:checked')].map(input => input.value);
        syncKpSelection();
      });
      kpPicker.querySelector('[data-exam-kp-clear]').addEventListener('click', () => {
        this.kpFilters = [];
        kpPicker.querySelectorAll('[data-exam-kp]').forEach(input => { input.checked = false; });
        syncKpSelection();
      });
      U.$('.exam-filters', box).addEventListener('click', event => { if (!kpPicker.contains(event.target)) kpPicker.open = false; });
      U.$('#examStateFilter', box).addEventListener('change', event => {
        this.testFilter = event.target.value;
        this.renderPaperCards();
      });
      this.renderPaperCards();
    }).catch(error => {
      if (U.$('#pBody') === box && this._activeTab()) {
        box.innerHTML = `<div class="callout callout--warn">试卷加载失败：${U.esc(error.message || '请重试')}</div>
          <button class="btn btn--outline" id="examReload">重新加载</button>`;
        U.$('#examReload', box).addEventListener('click', () => this.renderList());
      }
    });
  },

  renderPaperCards() {
    const list = U.$('#examPaperList');
    if (!list) return;
    const needle = this.query.toLocaleLowerCase();
    const items = this.papers.filter(paper => {
      const kps = paper.knowledgePoints || [];
      const matchesKp = this.kpFilters.every(id => kps.some(kp => kp.kpId === id));
      const tested = Number(paper.attemptCount) > 0;
      const matchesState = this.testFilter === 'all' || (this.testFilter === 'tested' ? tested : !tested);
      const text = [paper.title, ...kps.map(kp => kp.name)].join(' ').toLocaleLowerCase();
      return matchesKp && matchesState && (!needle || text.includes(needle));
    });
    if (!items.length) {
      list.innerHTML = `<div class="card"><div class="card__body">${R.empty(this.papers.length ? '没有匹配的试卷' : '暂无已发布试卷', this.papers.length ? '请调整搜索词、知识点或测验状态' : '教师发布试卷后会显示在这里', 'search2')}</div></div>`;
      return;
    }
    list.innerHTML = items.map(paper => {
      const kps = paper.knowledgePoints || [];
      const state = paper.inProgress ? '继续测验' : paper.attemptCount ? '重新测验' : '开始测验';
      const result = paper.lastScore == null ? '<span class="fz-12 t-dim">尚未参加</span>' :
        `<span class="badge badge--brand">上次得分 ${U.esc(paper.lastScore)} / ${U.esc(paper.totalScore)}</span>
         <span class="badge badge--outline">试卷正确率 ${U.esc(paper.lastAccuracy)}%</span>`;
      return `<article class="card exam-paper-card">
        <div class="exam-paper-card__main">
          <div class="row exam-paper-card__title"><h3>${this.highlight(paper.title, this.query)}</h3>
            <span class="badge badge--outline">${U.esc(paper.totalScore)} 分</span></div>
          <div class="exam-paper-card__meta"><span>${paper.questionCount} 道题</span><span>·</span><span>${paper.attemptCount || 0} 次测验</span></div>
          <div class="exam-kp-tags">${kps.length ? kps.map(kp => `<span class="badge badge--outline">${this.highlight(kp.name, this.query)}</span>`).join('') : '<span class="fz-12 t-dim">未设置知识点</span>'}</div>
          <div class="exam-paper-card__result">${result}</div>
        </div>
        <button class="btn btn--primary exam-start" data-exam-start="${U.esc(paper.paperId)}">${icon(paper.inProgress ? 'arrowRight' : paper.attemptCount ? 'refresh' : 'play')} ${state}</button>
      </article>`;
    }).join('');
    U.$$('[data-exam-start]', list).forEach(button => button.addEventListener('click', () => this.start(button.dataset.examStart)));
  },

  highlight(value, query) {
    const source = String(value || '');
    const term = String(query || '').trim();
    if (!term) return U.esc(source);
    const re = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig');
    let html = '', at = 0, match;
    while ((match = re.exec(source))) {
      html += U.esc(source.slice(at, match.index)) + `<mark class="exam-highlight">${U.esc(match[0])}</mark>`;
      at = match.index + match[0].length;
      if (!match[0]) re.lastIndex++;
    }
    return html + U.esc(source.slice(at));
  },

  async start(paperId) {
    if (this.startingPaperId) return;
    this.startingPaperId = paperId;
    const button = document.querySelector(`[data-exam-start="${CSS.escape(paperId)}"]`);
    if (button) button.disabled = true;
    try {
      const data = await API.practice.startExam({ paperId });
      this.attempt = data;
      this.result = null;
      this.answers = Object.assign({}, data.answers || {});
      this.durations = Object.assign({}, data.durations || {});
      this.attemptStartedAt = Date.now() - Math.max(0, data.elapsedSeconds || 0) * 1000;
      this.index = data.questions.findIndex(q => !this._hasAnswer(q, this.answers[q.itemId] || ''));
      if (this.index < 0) this.index = 0;
      this.saveQueue = Promise.resolve();
      this.renderAttempt();
    } catch (error) {
      Toast.error('试卷无法打开', error.message || '请稍后重试');
    } finally {
      this.startingPaperId = '';
      if (button && button.isConnected) button.disabled = false;
    }
  },

  _hasAnswer(question, value) {
    if (question.type !== 'blank') return !!String(value || '').trim();
    try { return JSON.parse(value || '[]').some(part => String(part || '').trim()); }
    catch (_) { return !!String(value || '').trim(); }
  },

  _answerFor(question) {
    if (question.type === 'blank') {
      return JSON.stringify([...U.$$('.exam-blank')].map(input => input.value.trim()));
    }
    return [...U.$$('#examOptions .opt.is-picked')].map(option => option.dataset.key).sort().join('');
  },

  _currentQuestion() { return this.attempt && this.attempt.questions[this.index]; },
  _itemDuration(question) {
    return this.currentDurationBase + Math.max(0, Math.floor((Date.now() - this.itemStartedAt) / 1000));
  },

  _queueSave(itemId, answer, duration) {
    const attemptId = this.attempt.attemptId;
    this.answers[itemId] = answer;
    const operation = () => API.practice.saveExamAnswer({ attemptId, itemId, answer, durationSeconds: duration || 0 });
    this.saveQueue = this.saveQueue.catch(() => {}).then(operation);
    const queued = this.saveQueue;
    queued.then(() => {
      const status = U.$('#examSaveStatus');
      if (status && this.running) status.textContent = '已自动保存';
    }).catch(error => {
      const status = U.$('#examSaveStatus');
      if (status && this.running) status.textContent = '保存失败，请检查网络后重试';
      console.warn('[exam] answer autosave failed', error);
    });
    return queued;
  },

  _scheduleSave() {
    const question = this._currentQuestion();
    if (!question || !this.running) return;
    const status = U.$('#examSaveStatus');
    if (status) status.textContent = '正在保存…';
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      const answer = this._answerFor(question);
      this._queueSave(question.itemId, answer, this._itemDuration(question)).catch(() => {});
    }, 350);
  },

  async _saveCurrent() {
    const question = this._currentQuestion();
    if (!question || !this.running) return;
    clearTimeout(this.saveTimer);
    const answer = this._answerFor(question);
    return this._queueSave(question.itemId, answer, this._itemDuration(question));
  },

  _questionMarkup(q) {
    const number = this.index + 1;
    let stem = U.esc(q.stem || '');
    if (q.type === 'blank') {
      let count = 0;
      stem = stem.replace(/_{2,}|＿{2,}|（\s*）|\(\s*\)/g, () => `<input class="blank-input exam-blank" data-blank="${++count}" autocomplete="off" aria-label="第${count}空">`);
      const blanks = Array.isArray(q.blanks) ? q.blanks.length : 0;
      const extra = Array.from({ length: Math.max(0, blanks - count) }, (_, i) => `<label class="blank-fallback__row"><span>第 ${count + i + 1} 空</span><input class="blank-input exam-blank" data-blank="${count + i + 1}" autocomplete="off"></label>`).join('');
      return `<div class="q-stem" id="examStem"><span class="q-no">${number}</span>${stem}</div>${extra ? `<div class="blank-fallback">${extra}</div>` : ''}
        <p class="fz-12 t-dim">填空题：每个空填写一种正确答案。</p>`;
    }
    const multi = q.type === 'multi';
    return `<div class="q-stem"><span class="q-no">${number}</span>${stem}</div>
      ${multi ? '<p class="fz-12 t-dim">多选题：可选择多个选项，全部选对才算正确。</p>' : ''}
      <div class="opts" id="examOptions">${(q.options || []).map(option => `<button class="opt" type="button" data-key="${U.esc(option.key)}">
        <span class="opt__key">${U.esc(option.key)}</span><span style="flex:1">${U.esc(option.text)}</span>
        ${q.figure && q.figure.options_graph && q.figure.options_graph[option.key] ? `<div class="q-opt-fig" data-exam-optfig="${U.esc(option.key)}"></div>` : ''}
      </button>`).join('')}</div>`;
  },

  _mountFigure(root, figure) {
    if (!root || !figure) return;
    const slot = root.querySelector('#examFigure') || root.querySelector('[data-result-figure-slot]');
    const image = figure.imageUrl || figure.image_url;
    if (image && slot && U.mountQuestionImage(slot, image)) {
      // linked question figure
    } else if (figure.graph && window.DsFigure && slot) DsFigure.mount(slot, figure.graph);
    else if (figure.has_image && slot) slot.innerHTML = '<div class="callout callout--warn">本题配图暂时无法显示，请按题面作答。</div>';
    if (figure.options_graph && window.DsFigure) Object.entries(figure.options_graph).forEach(([key, graph]) => {
      const target = root.querySelector(`[data-exam-optfig="${key}"]`);
      if (target) DsFigure.mount(target, graph);
    });
  },

  renderAttempt() {
    const box = U.$('#pBody');
    const q = this._currentQuestion();
    if (!box || !q) return;
    clearInterval(this.clockTimer);
    this.itemStartedAt = Date.now();
    this.currentDurationBase = this.durations[q.itemId] || 0;
    let stored = this.answers[q.itemId] || '';
    let blankValues = [];
    if (q.type === 'blank') {
      try { blankValues = JSON.parse(stored || '[]'); } catch (_) { blankValues = []; }
    }
    const answered = this.attempt.questions.filter(item => this._hasAnswer(item, this.answers[item.itemId] || '')).length;
    box.innerHTML = `<section class="card exam-session">
      <header class="exam-session__head row">
        <button class="btn btn--sm btn--ghost" id="examExit">${icon('arrowLeft')} 退出试卷</button>
        <div class="exam-session__heading"><b>${U.esc(this.attempt.title)}</b><span>第 ${this.index + 1} / ${this.attempt.questions.length} 题 · 已答 ${answered} 题</span></div>
        <span class="badge badge--outline mono" id="examClock">00:00</span>
      </header>
      <div class="exam-session__progress">${U.bar((answered / this.attempt.questions.length) * 100, 'good', 'sm')}</div>
      <div class="q-body exam-session__body">
        <div class="row exam-question-meta"><span class="badge badge--brand">${U.esc(q.score)} 分</span><span class="badge badge--outline">${U.esc(q.chapter || '未分章')}</span>
          ${(q.kpNames || []).map(name => `<span class="badge badge--outline">${U.esc(name)}</span>`).join('')}
          <span class="spacer"></span><span class="fz-12 t-dim">难度 ${U.stars(q.difficulty)}</span></div>
        ${this._questionMarkup(q)}
        <div class="q-figure" id="examFigure"></div>
        <p class="fz-12 t-dim exam-save-status" id="examSaveStatus">答案会自动保存</p>
      </div>
      <footer class="card__foot exam-session__foot">
        <div class="exam-question-nav">${this.attempt.questions.map((item, i) => `<button type="button" data-exam-index="${i}" class="exam-number ${i === this.index ? 'is-current' : ''} ${this._hasAnswer(item, this.answers[item.itemId] || '') ? 'is-answered' : ''}" aria-label="第${i + 1}题">${i + 1}</button>`).join('')}</div>
        <div class="row exam-session__actions"><button class="btn btn--outline" id="examPrev" ${this.index === 0 ? 'disabled' : ''}>上一题</button>
          ${this.index < this.attempt.questions.length - 1 ? '<button class="btn btn--outline" id="examNext">下一题</button>' : ''}
          <button class="btn btn--primary" id="examSubmit">交卷</button></div>
      </footer>
    </section>`;
    const clockText = () => {
      const seconds = Math.max(0, Math.floor((Date.now() - this.attemptStartedAt) / 1000));
      return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    };
    const timer = U.$('#examClock', box);
    if (timer) timer.textContent = clockText();
    this.clockTimer = setInterval(() => {
      const element = U.$('#examClock');
      if (!element || !this.running) { clearInterval(this.clockTimer); return; }
      element.textContent = clockText();
    }, 1000);

    if (q.type === 'blank') {
      U.$$('.exam-blank', box).forEach((input, i) => {
        input.value = blankValues[i] || '';
        input.addEventListener('input', () => { this._scheduleSave(); this._updateProgress(); });
      });
    } else {
      const picked = new Set(String(stored).split(''));
      U.$$('#examOptions .opt', box).forEach(option => {
        if (picked.has(option.dataset.key)) option.classList.add('is-picked');
        option.addEventListener('click', () => {
          if (q.type === 'multi') option.classList.toggle('is-picked');
          else {
            U.$$('#examOptions .opt', box).forEach(other => other.classList.remove('is-picked'));
            option.classList.add('is-picked');
          }
          this._scheduleSave();
          this._updateProgress();
        });
      });
    }
    this._mountFigure(box, q.figure);
    U.$('#examExit', box).addEventListener('click', () => this.requestExit(null));
    U.$('#examPrev', box).addEventListener('click', () => this.switchQuestion(this.index - 1));
    const next = U.$('#examNext', box);
    if (next) next.addEventListener('click', () => this.switchQuestion(this.index + 1));
    U.$$('[data-exam-index]', box).forEach(button => button.addEventListener('click', () => this.switchQuestion(Number(button.dataset.examIndex))));
    U.$('#examSubmit', box).addEventListener('click', () => this.requestSubmit());
  },

  _updateProgress() {
    const current = this._currentQuestion();
    if (current) this.answers[current.itemId] = this._answerFor(current);
    const answered = this.attempt.questions.filter(item => this._hasAnswer(item, this.answers[item.itemId] || '')).length;
    const count = U.$('.exam-session__heading span');
    if (count) count.textContent = `第 ${this.index + 1} / ${this.attempt.questions.length} 题 · 已答 ${answered} 题`;
    const progressFill = U.$('.exam-session__progress .bar > i');
    if (progressFill) progressFill.style.width = `${answered / this.attempt.questions.length * 100}%`;
    U.$$('[data-exam-index]').forEach(button => {
      const item = this.attempt.questions[Number(button.dataset.examIndex)];
      button.classList.toggle('is-answered', this._hasAnswer(item, this.answers[item.itemId] || (item.itemId === this._currentQuestion().itemId ? this._answerFor(item) : '')));
    });
  },

  async switchQuestion(nextIndex) {
    if (nextIndex < 0 || nextIndex >= this.attempt.questions.length || nextIndex === this.index) return;
    try {
      await this._saveCurrent();
      const current = this._currentQuestion();
      if (current) this.durations[current.itemId] = this._itemDuration(current);
      this.index = nextIndex;
      this.renderAttempt();
    } catch (error) { Toast.error('答案保存失败', '网络恢复后再切换题目，当前作答仍保留在页面中'); }
  },

  async requestSubmit() {
    const missing = this.attempt.questions.filter(q => !this._hasAnswer(q, q.itemId === this._currentQuestion().itemId ? this._answerFor(q) : this.answers[q.itemId] || '')).length;
    if (!missing) return this.finish();
    Modal.open({
      title: '确认交卷',
      body: `<div class="callout callout--warn" style="margin:0"><div><b>还有 ${missing} 道题没有作答。</b><div class="fz-12 t-dim">交卷后会立即计算成绩，并将本次作答计入练习正确率和错题本。</div></div></div>`,
      footer: '<button class="btn" data-close>继续检查</button><button class="btn btn--primary" id="examConfirmSubmit">仍然交卷</button>',
      onMount: (overlay, close) => U.$('#examConfirmSubmit', overlay).addEventListener('click', () => { close(); this.finish(); })
    });
  },

  requestExit(target) {
    if (!this.running || this.finishing) return;
    this.pendingTarget = target;
    let confirmed = false;
    Modal.open({
      title: '退出试卷测验',
      body: `<div class="callout callout--warn" style="margin:0"><div><b>退出后将立即交卷并结算成绩。</b><div class="fz-12 t-dim">未作答的题目按答错计入成绩。结算后会显示本次得分和答题情况。</div></div></div>`,
      footer: '<button class="btn" data-close>继续答题</button><button class="btn btn--danger" id="examConfirmExit">退出并交卷</button>',
      onClose: () => { if (!confirmed && this.running) this.pendingTarget = null; },
      onMount: (overlay, close) => U.$('#examConfirmExit', overlay).addEventListener('click', async () => {
        const button = U.$('#examConfirmExit', overlay);
        button.disabled = true;
        confirmed = true;
        try { close(); await this.finish(); }
        catch (_) { this.pendingTarget = null; }
      })
    });
  },

  async finish(options = {}) {
    if (!this.running || this.finishing) return;
    this.finishing = true;
    clearTimeout(this.saveTimer);
    clearInterval(this.clockTimer);
    try {
      await this._saveCurrent();
      await this.saveQueue;
      const result = await API.practice.finishExam({ attemptId: this.attempt.attemptId });
      this.attempt.status = 'finished';
      this.result = result;
      this.finishing = false;
      clearInterval(this.clockTimer);
      if (options.render !== false) this.renderResult();
      return result;
    } catch (error) {
      this.finishing = false;
      Toast.error('试卷结算失败', error.message || '请检查网络后重试');
      throw error;
    }
  },

  renderResult() {
    const box = U.$('#pBody');
    const result = this.result;
    if (!box || !result) return;
    const target = this.pendingTarget;
    const targetLabel = target && target.kind === 'tab' ? (target.tab === 'wrong' ? '错题本' : '智能练习')
      : target && target.kind === 'route' ? ((Router.views[target.key] || {}).title || '目标页面')
      : target && target.kind === 'logout' ? '退出登录' : '';
    box.innerHTML = `<div class="card exam-result-summary">
      <div class="exam-result-summary__mark">${icon(result.accuracy >= 60 ? 'checkCircle' : 'target')}</div>
      <h2>试卷已结算</h2><p>${U.esc(result.title)}</p>
      <div class="exam-result-score"><strong>${U.esc(result.score)}</strong><span> / ${U.esc(result.totalScore)} 分</span></div>
      <div class="exam-result-stats"><div><b>${U.esc(result.correct)} / ${U.esc(result.total)}</b><span>答对题数</span></div><div><b>${U.esc(result.accuracy)}%</b><span>试卷正确率</span></div><div><b>${this.formatDuration(result.durationSeconds)}</b><span>用时</span></div></div>
      ${result.masteredCount ? `<p class="exam-mastered-note">本次答对的 ${result.masteredCount} 道曾错题已移出待攻克列表。</p>` : ''}
    </div>
    <div class="exam-result-details"><h3>答题情况</h3>${(result.items || []).map((item, i) => `<article class="card exam-result-item ${item.correct ? 'is-correct' : 'is-wrong'}" data-result-figure="${i}">
      <div class="row"><span class="badge ${item.correct ? 'badge--ok' : 'badge--danger'}">${item.correct ? '正确' : '错误'}</span><span class="badge badge--outline">${U.esc(item.score)} 分</span><span class="badge badge--outline">${U.esc(item.chapter || '未分章')}</span><span class="spacer"></span><span>第 ${i + 1} 题 · 得 ${U.esc(item.earnedScore)} 分</span></div>
      <div class="exam-result-item__stem">${U.esc(item.stem || '')}</div>
      ${item.options && item.options.length ? `<div class="exam-result-options">${item.options.map(option => `<div><b>${U.esc(option.key)}</b>　${U.esc(option.text)}${item.figure && item.figure.options_graph && item.figure.options_graph[option.key] ? `<div class="q-opt-fig" data-exam-optfig="${U.esc(option.key)}"></div>` : ''}</div>`).join('')}</div>` : ''}
      <div class="exam-result-answer"><span>你的答案：<b class="${item.correct ? 't-ok' : 't-danger'}">${U.esc(this.answerLabel(item.myAnswer, item.type) || '未作答')}</b></span><span>正确答案：<b class="t-ok">${U.esc(item.correctAnswer || '')}</b></span></div>
      ${item.analysis ? `<p class="fz-13 t-2"><b>解析：</b>${U.esc(item.analysis)}</p>` : ''}<div class="q-figure" data-result-figure-slot></div>
    </article>`).join('')}</div>
    <div class="row exam-result-actions"><button class="btn btn--outline" id="examBackList">${icon('arrowLeft')} 返回试卷列表</button>
      <button class="btn btn--outline" id="examRetake">${icon('refresh')} 重新测验</button>
      ${targetLabel ? `<button class="btn btn--primary" id="examContinueTarget">继续：${U.esc(targetLabel)}</button>` : ''}</div>`;
    (result.items || []).forEach((item, i) => this._mountFigure(box.querySelectorAll('.exam-result-item')[i], item.figure));
    U.$('#examBackList', box).addEventListener('click', () => this.backToList());
    U.$('#examRetake', box).addEventListener('click', () => {
      const paperId = result.paperId;
      this.attempt = null; this.result = null; this.pendingTarget = null;
      this.start(paperId);
    });
    const continueButton = U.$('#examContinueTarget', box);
    if (continueButton) continueButton.addEventListener('click', () => this.continueTarget());
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  formatDuration(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60), rest = value % 60;
    return `${minutes} 分 ${rest} 秒`;
  },

  answerLabel(value, type) {
    if (type !== 'blank') return String(value || '');
    try {
      const parts = JSON.parse(value || '[]');
      return Array.isArray(parts) ? parts.join('；') : String(value || '');
    } catch (_) { return String(value || ''); }
  },

  backToList() {
    this.attempt = null;
    this.result = null;
    this.pendingTarget = null;
    clearInterval(this.clockTimer);
    this.renderList();
  },

  continueTarget() {
    const target = this.pendingTarget;
    this.pendingTarget = null;
    this.attempt = null;
    this.result = null;
    if (!target) return this.backToList();
    if (target.kind === 'tab') {
      const practice = window.StudentPractice;
      practice.tab = target.tab;
      U.$$('#pTabs button').forEach(button => button.classList.toggle('is-active', button.dataset.t === target.tab));
      if (target.tab === 'wrong') practice.renderWrong();
      else practice.renderSelect();
    } else if (target.kind === 'route') Router.go(target.key, target.params);
    else if (target.kind === 'logout') confirmLogout();
  },

  allowTabLeave(nextTab) {
    if (!this.running) return true;
    this.requestExit({ kind: 'tab', tab: nextTab || 'quiz' });
    return false;
  },

  guardRoute(key, params) {
    this.requestExit({ kind: 'route', key, params });
  },

  beforeCourseChange() {
    if (!this.running) return Promise.resolve(true);
    return new Promise(resolve => {
      let stage = 0, completed = false;
      const finishPrompt = Modal.open({
        title: '切换课程',
        body: '<div class="callout callout--warn" style="margin:0"><div><b>切换课程会退出当前试卷并结算成绩。</b><div class="fz-12 t-dim">确认后，未作答的题目按答错计入成绩。</div></div></div>',
        footer: '<button class="btn" data-close>留在当前课程</button><button class="btn btn--danger" id="examCourseSettle">结算并切换课程</button>',
        onClose: () => {
          if (!completed) {
            completed = true;
            if (stage === 1) this.renderResult();
            resolve(false);
          }
        }
      });
      U.$('#examCourseSettle', finishPrompt.el).addEventListener('click', async () => {
        const button = U.$('#examCourseSettle', finishPrompt.el);
        button.disabled = true;
        try {
          const result = await this.finish({ render: false });
          if (completed) { this.renderResult(); return; }
          stage = 1;
          finishPrompt.el.querySelector('.modal__head h3').textContent = '本次测验已结算';
          finishPrompt.el.querySelector('.modal__body').innerHTML = `<div class="exam-course-result"><b>${U.esc(result.title)}</b><strong>${U.esc(result.score)} / ${U.esc(result.totalScore)} 分</strong><span>正确率 ${U.esc(result.accuracy)}% · ${this.formatDuration(result.durationSeconds)}</span></div>`;
          finishPrompt.el.querySelector('.modal__foot').innerHTML = '<button class="btn" id="examCourseStay">留在当前课程</button><button class="btn btn--primary" id="examCourseContinue">确认切换课程</button>';
          U.$('#examCourseStay', finishPrompt.el).addEventListener('click', () => {
            completed = true; finishPrompt.close(); this.renderResult(); resolve(false);
          });
          U.$('#examCourseContinue', finishPrompt.el).addEventListener('click', () => {
            completed = true; finishPrompt.close(); resolve(true);
          });
        } catch (_) { button.disabled = false; }
      });
    });
  },

  _guardRouter() {
    if (this._routerGuardInstalled) return;
    this._routerGuardInstalled = true;
    const previous = Router.beforeNavigate;
    Router.beforeNavigate = function (key, params) {
      if (key !== this.current && StudentExams.running) {
        StudentExams.guardRoute(key, params);
        return false;
      }
      return typeof previous === 'function' ? previous.call(this, key, params) : true;
    };
    window.addEventListener('beforeunload', event => {
      if (!StudentExams.running) return;
      event.preventDefault();
      event.returnValue = '';
    });
    document.addEventListener('click', event => {
      if (!event.target.closest('#logoutBtn') || !StudentExams.running) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      StudentExams.requestExit({ kind: 'logout' });
    }, true);
  },
};

StudentExams._guardRouter();
window.StudentExams = StudentExams;
StudentPractice.beforeCourseChange = () => StudentExams.beforeCourseChange();
