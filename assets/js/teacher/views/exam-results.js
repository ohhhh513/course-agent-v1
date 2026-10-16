'use strict';

/* 教师试卷作答分析；整卷统计与个人作答均只读取服务端快照。 */
window.TeacherExamResults = {
  data: null, student: null, box: null, context: '', epoch: 0, sequence: 0, detailSequence: 0,
  events: null, rankingModal: null,
  contextKey() {
    const session = Auth.getSession();
    return `${session?.user?.userId || ''}:${session?.loginStartedAt || ''}:${API.config.activeCourseId}`;
  },
  active() {
    return !!this.box?.isConnected && this.context === this.contextKey() && TeacherExams.active(this.epoch) && U.$('#qBody') === this.box;
  },
  close() {
    this.sequence++; this.detailSequence++;
    this.events?.abort(); this.rankingModal?.close();
    this.data = null; this.student = null; this.box = null; this.context = '';
  },
  async open(paperId) {
    this.close();
    this.box = U.$('#qBody'); this.context = this.contextKey(); this.epoch = ++TeacherExams.epoch;
    TeacherExams.courseId = API.config.activeCourseId;
    const request = ++this.sequence;
    this.box.innerHTML = '<div class="card"><div class="card__body">正在加载作答详细…</div></div>';
    try {
      const data = await API.question.exams.results(paperId);
      if (!this.active() || request !== this.sequence) return;
      this.data = data; this.render(); window.scrollTo({top: 0, behavior: 'smooth'});
    } catch (error) {
      if (!this.active() || request !== this.sequence) return;
      this.box.innerHTML = `<div class="card"><div class="card__body"><button class="btn btn--sm" id="teacherExamResultsBack">${icon('arrowLeft')} 返回试卷列表</button><p class="t-danger">${U.esc(error.message || '作答详情加载失败')}</p><button class="btn" id="teacherExamResultsRetry">重试</button></div></div>`;
      this.box.querySelector('#teacherExamResultsBack').onclick = () => TeacherExams.list();
      this.box.querySelector('#teacherExamResultsRetry').onclick = () => this.open(paperId);
    }
  },
  render() {
    this.events?.abort(); this.events = new AbortController();
    this.box.innerHTML = `<section class="teacher-exam-results">
      <header class="card teacher-exam-results__header"><div><button class="btn btn--ghost btn--sm" id="teacherExamResultsBack">${icon('arrowLeft')} 返回试卷列表</button><h2>${U.esc(this.data.title)} · 作答详细</h2></div>
        <div class="teacher-exam-results__tools"><button class="btn btn--outline btn--sm" id="teacherExamRanking">${icon('users')} 查看班级排名</button>
          <div class="teacher-exam-student-search"><label class="teacher-exam-student-search__input">${icon('search2')}<input class="input" id="teacherExamStudentSearch" type="search" placeholder="搜索学生姓名" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="teacherExamStudentOptions" aria-label="查询学生作答详情"><button class="btn btn--ghost btn--icon btn--sm" id="teacherExamStudentToggle" aria-label="展开学生列表" type="button">${icon('chevronDown')}</button></label>
            <div class="teacher-exam-student-options" id="teacherExamStudentOptions" role="listbox" aria-label="学生列表" hidden></div></div></div></header>
      <div id="teacherExamResultsBody"></div></section>`;
    this.box.querySelector('#teacherExamResultsBack').onclick = () => TeacherExams.list();
    this.box.querySelector('#teacherExamRanking').onclick = () => this.openRanking();
    const input = this.box.querySelector('#teacherExamStudentSearch'), options = this.box.querySelector('#teacherExamStudentOptions');
    let focused = -1;
    const hide = () => { options.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); focused = -1; };
    const paint = () => {
      const keyword = input.value.trim();
      const students = this.data.students.filter(student => student.name.toLocaleLowerCase().includes(keyword.toLocaleLowerCase()));
      focused = -1; input.removeAttribute('aria-activedescendant');
      options.innerHTML = students.map((student, index) => `<button class="teacher-exam-student-option" type="button" role="option" id="teacherExamStudentOption${index}" aria-selected="false" data-exam-student="${U.esc(student.userId)}"><span>${TeacherExams.highlight(student.name, keyword)}</span><small>${U.esc(student.className || '未设置班级')} · ${student.status === 'finished' ? '已测验' : '未测验'}</small></button>`).join('') || '<p class="t-dim fz-12">没有匹配的学生</p>';
      options.hidden = false; options.scrollTop = 0; input.setAttribute('aria-expanded', 'true');
    };
    input.addEventListener('focus', paint);
    input.addEventListener('input', paint);
    this.box.querySelector('#teacherExamStudentToggle').onclick = () => { if (options.hidden) { input.focus(); paint(); } else hide(); };
    options.addEventListener('click', event => {
      const button = event.target.closest('[data-exam-student]');
      if (!button) return;
      hide(); this.selectStudent(button.dataset.examStudent);
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { hide(); return; }
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (options.hidden) paint();
      const buttons = [...options.querySelectorAll('[data-exam-student]')];
      if (event.key === 'Enter') { if (buttons[focused]) buttons[focused].click(); return; }
      if (!buttons.length) return;
      focused = event.key === 'ArrowDown' ? (focused + 1) % buttons.length : (focused < 0 ? buttons.length - 1 : (focused + buttons.length - 1) % buttons.length);
      buttons.forEach((button, index) => button.setAttribute('aria-selected', String(index === focused)));
      input.setAttribute('aria-activedescendant', buttons[focused].id); buttons[focused].scrollIntoView({ block: 'nearest' });
    });
    document.addEventListener('click', event => { if (!this.box?.querySelector('.teacher-exam-student-search')?.contains(event.target)) hide(); }, { signal: this.events.signal });
    this.overview();
  },
  metric(value, label) { return `<div><b>${U.esc(value == null ? '—' : value)}</b><span>${label}</span></div>`; },
  duration(value) {
    if (value == null) return '—';
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
  },
  rankLabel(ranking) { return ranking?.rank != null && ranking.classSize ? `${ranking.rank}/${ranking.classSize}` : '暂无排名'; },
  overview() {
    this.detailSequence++; this.student = null;
    const summary = this.data.summary, body = this.box.querySelector('#teacherExamResultsBody');
    body.innerHTML = `<div class="card teacher-exam-metrics">${this.metric(summary.submittedCount, '提交人数')}${this.metric(summary.averageScore, '平均分')}${this.metric(summary.highestScore, '最高分')}${this.metric(summary.lowestScore, '最低分')}</div>
      <div class="row row--wrap teacher-exam-results__section"><h3>题目作答统计</h3><span class="spacer"></span><span class="fz-12 t-dim">每名学生取最近一次提交；多选题按每个选项分别计人数。</span></div>
      ${this.data.questions.map(question => this.questionHtml(question)).join('') || '<div class="card card__body t-dim">暂无题目</div>'}`;
    this.mountFigures(body, this.data.questions);
  },
  answerText(raw, type) {
    if (type !== 'blank') return String(raw || '未作答');
    try { const parts = JSON.parse(raw); return Array.isArray(parts) ? parts.map(part => part || '未作答').join('；') : String(raw || '未作答'); }
    catch (_) { return String(raw || '未作答'); }
  },
  questionHtml(question, index, individual = false) {
    const number = individual ? index + 1 : question.number;
    const options = question.options || [], right = new Set(String(question.correctAnswer || question.answer || '').toUpperCase());
    const selected = new Set(String(question.myAnswer || '').toUpperCase());
    const blank = question.type === 'blank';
    return `<article class="card teacher-exam-question" data-teacher-exam-question>
      <div class="row row--wrap"><h3>第 ${number} 题</h3><span class="badge badge--outline">${U.esc(TeacherExams.types[question.type] || question.type)}</span><span class="badge badge--outline">${U.esc(question.score)} 分</span><span class="badge badge--outline">${U.esc(question.chapter || '未分章')}</span>
        ${question.historical ? '<span class="badge badge--warn">历史题目快照</span>' : ''}<span class="spacer"></span>${individual ? `<span class="badge ${question.correct ? 'badge--ok' : 'badge--danger'}">${question.correct ? '正确' : '错误'} · 得 ${U.esc(question.earnedScore)} 分</span>` : `<span class="t-dim fz-12">作答 ${question.respondentCount} 人 · 答对 ${question.correctCount} 人 · 未答 ${question.unansweredCount} 人</span>`}</div>
      <div class="exam-stem">${U.esc(question.stem)}</div><div data-teacher-exam-figure></div>
      ${blank ? (individual ? '' : `<div class="teacher-exam-blank-stats">${(question.blanks || []).map(part => `<div><b>第 ${part.index} 空</b><span class="t-ok">${U.esc(part.accept.join(' / '))}</span><span>答对 ${part.correctCount} 人 · 答错 ${part.wrongCount} 人 · 未答 ${part.unansweredCount} 人</span></div>`).join('')}</div>`) : `<div class="teacher-exam-options">${options.map(option => {
        const correct = individual ? right.has(option.key) : option.right;
        return `<div class="teacher-exam-option ${correct ? 'is-right' : 'is-wrong'}"><b>${U.esc(option.key)}</b><div class="teacher-exam-option__text">${U.esc(option.text)}<div data-teacher-exam-opt="${U.esc(option.key)}"></div></div>
          ${individual ? (selected.has(option.key) ? '<span class="badge badge--outline">学生选择</span>' : '') : `<span class="teacher-exam-option__count">${option.count} 人选择</span>`}${correct ? '<span class="badge badge--ok">正确选项</span>' : ''}</div>`;
      }).join('')}</div>`}
      ${individual ? `<div class="exam-result-answer"><span>学生答案：<b class="${question.correct ? 't-ok' : 't-danger'}">${U.esc(this.answerText(question.myAnswer, question.type))}</b></span><span>正确答案：<b class="t-ok">${U.esc(question.correctAnswer)}</b></span></div>` : `<p class="fz-13"><b>答案：</b>${U.esc(question.answer)}</p>`}
      <p class="fz-13 exam-stem"><b>解析：</b>${U.esc(question.analysis || '暂无解析')}</p></article>`;
  },
  mountFigures(root, questions) {
    root.querySelectorAll('[data-teacher-exam-question]').forEach((element, index) => {
      const figure = questions[index]?.figure;
      if (!figure) return;
      const slot = element.querySelector('[data-teacher-exam-figure]');
      const image = figure.imageUrl || figure.image_url;
      if (image && slot && U.mountQuestionImage(slot, image)) { /* 共享图片校验与展示 */ }
      else if (figure.graph && slot && window.DsFigure) DsFigure.mount(slot, figure.graph);
      else if (figure.has_image && slot) slot.textContent = '本题配图暂时无法显示';
      if (figure.options_graph && window.DsFigure) Object.entries(figure.options_graph).forEach(([key, graph]) => {
        const target = element.querySelector(`[data-teacher-exam-opt="${CSS.escape(key)}"]`);
        if (target) DsFigure.mount(target, graph);
      });
    });
  },
  async selectStudent(studentId) {
    const request = ++this.detailSequence;
    const body = this.box.querySelector('#teacherExamResultsBody');
    body.innerHTML = '<div class="card card__body t-dim">正在加载学生作答…</div>';
    try {
      const result = await API.question.exams.studentResult(this.data.paperId, studentId);
      if (!this.active() || request !== this.detailSequence) return;
      this.student = result.student;
      const pending = result.student.status !== 'finished';
      body.innerHTML = `<div class="card teacher-exam-individual"><div class="row row--wrap"><h3>${U.esc(result.student.name)} · ${pending ? '未测验' : '作答详情'}</h3><span class="t-dim fz-12">${U.esc(result.student.className || '未设置班级')}</span><span class="spacer"></span><button class="btn btn--outline btn--sm" id="teacherExamOverview">返回整卷统计</button></div>
        <div class="teacher-exam-metrics teacher-exam-metrics--three">${this.metric(pending ? null : `${result.score} / ${result.totalScore}`, '分数')}${this.metric(this.duration(result.durationSeconds), '时长')}${this.metric(this.rankLabel(result.ranking), '班级排名')}</div></div>
        ${pending ? '<div class="card card__body t-dim">该学生尚未提交此试卷，暂无作答记录。</div>' : (result.items || []).map((question, index) => this.questionHtml(question, index, true)).join('')}`;
      body.querySelector('#teacherExamOverview').onclick = () => this.overview();
      this.mountFigures(body, result.items || []);
    } catch (error) {
      if (!this.active() || request !== this.detailSequence) return;
      body.innerHTML = `<div class="card card__body"><p class="t-danger">${U.esc(error.message || '学生作答加载失败')}</p><button class="btn" id="teacherExamStudentRetry">重试</button><button class="btn" id="teacherExamOverview">返回整卷统计</button></div>`;
      body.querySelector('#teacherExamStudentRetry').onclick = () => this.selectStudent(studentId);
      body.querySelector('#teacherExamOverview').onclick = () => this.overview();
    }
  },
  openRanking() {
    if (!this.data || this.rankingModal?.el.isConnected) return;
    const paperId = this.data.paperId;
    let generation = 0;
    this.rankingModal = Modal.open({title: '班级排名', size: 'wide',
      body: `<label class="row row--wrap"><span>班级</span><span class="exam-select-wrap"><select class="select" id="teacherExamRankClass" aria-label="选择排名班级">${this.data.classes.map(name => `<option value="${U.esc(name)}">${U.esc(name)}</option>`).join('') || '<option value="">未设置班级</option>'}</select>${icon('chevronDown')}</span></label><div id="teacherExamRankingContent" aria-live="polite"></div>`,
      onClose: () => { this.rankingModal = null; },
      onMount: (ov, close) => {
        const select = ov.querySelector('#teacherExamRankClass'), content = ov.querySelector('#teacherExamRankingContent');
        if (this.student?.className) select.value = this.student.className;
        const load = async () => {
          const request = ++generation; content.textContent = '正在加载排名…';
          try {
            const ranking = await API.question.exams.ranking(paperId, select.value);
            if (!ov.isConnected || request !== generation) return;
            if (!this.active()) { close(); return; }
            content.innerHTML = `<p class="fz-12 t-dim">${ranking.testedCount} / ${ranking.classSize} 人已测验；分数优先，同分用时短者优先，两项相同则并列。</p>${ranking.message ? `<p class="callout callout--info">${U.esc(ranking.message)}</p>` : ''}
              <div class="exam-ranking-table"><table class="tbl"><thead><tr><th>排名</th><th>学生</th><th>分数</th><th>时长</th><th>状态</th></tr></thead><tbody>${ranking.list.map(entry => `<tr><td>${entry.rank ?? '—'}</td><td><button class="btn btn--ghost btn--sm" data-exam-rank-user="${U.esc(entry.userId)}">${U.esc(entry.name)}</button></td><td>${entry.score == null ? '—' : `${U.esc(entry.score)} / ${U.esc(entry.totalScore)}`}</td><td>${this.duration(entry.durationSeconds)}</td><td>${entry.status === 'finished' ? '已测验' : '未测验'}</td></tr>`).join('') || '<tr><td colspan="5">暂无排名</td></tr>'}</tbody></table></div>`;
            content.querySelectorAll('[data-exam-rank-user]').forEach(button => button.onclick = () => { close(); this.selectStudent(button.dataset.examRankUser); });
          } catch (error) {
            if (!ov.isConnected || request !== generation || !this.active()) return;
            content.innerHTML = `<p class="t-danger">${U.esc(error.message || '排名加载失败')}</p><button class="btn" id="teacherExamRankingRetry">重试</button>`;
            content.querySelector('#teacherExamRankingRetry').onclick = load;
          }
        };
        select.onchange = load; load();
      },
    });
  },
};

const previousExamResultsNavigation = Router.beforeNavigate;
Router.beforeNavigate = function (key, params) {
  if (key !== this.current) TeacherExamResults.close();
  return typeof previousExamResultsNavigation === 'function' ? previousExamResultsNavigation.call(this, key, params) : true;
};
