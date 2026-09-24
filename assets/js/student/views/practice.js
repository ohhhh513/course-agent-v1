'use strict';

  /* ================================================================
     视图 5 · 智能练习 / 专属题库
     ================================================================ */
  const Practice = {
    tab: 'quiz', state: 'select', mode: null,
    qs: [], idx: 0, answers: {}, picked: null, startAt: 0,
    // 错题本「按章节知识点归纳」的筛选状态（跨重渲染保留）
    _wChapter: '', _wKpId: '', _wSumOpen: true,

    resetCourseContext() {
      clearInterval(this._timer);
      this.tab = 'quiz';
      this.state = 'select';
      this.mode = null;
      this.activeMode = null;
      this.qs = [];
      this.idx = 0;
      this.answers = {};
      this.picked = null;
      this.startAt = 0;
      this.sessionId = '';
      this._wChapter = '';
      this._wKpId = '';
      this._wSumOpen = true;
      this.lastWrongFilter = 'false';
      this._weakKpIds = [];
      this._lastKpIds = undefined;
      this._lastQIds = undefined;
      this._pendingTarget = null;
      this._pendingResume = null;
      this._startTab = null;
    },

    render() {
      const el = U.$('#view-practice');
      el.innerHTML = `
      <div class="tabs" id="pTabs" style="margin-bottom:16px">
        <button class="is-active" data-t="quiz">智能练习</button>
        <button data-t="wrong">错题本</button>
      </div>
      <div id="pBody"></div>`;
      U.$$('#pTabs button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#pTabs button', el).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active');
        this.tab = b.dataset.t;
        this.tab === 'quiz' ? this.renderSelect() : this.renderWrong();
      }));
      this.renderSelect();
    },

    /* --- 模式选择 --- */
    renderSelect() {
      this.state = 'select';
      this.activeMode = null;
      const box = U.$('#pBody');
      // 竞态防护：本视图要等两个接口才渲染。若期间用户已经切到「错题本」，
      // 后到的回调不能再把 #pBody 覆盖回练习页（否则切页会被"弹回去"）。
      const courseId = API.config.activeCourseId;
      const stale = () => this.tab !== 'quiz' || U.$('#pBody') !== box || API.config.activeCourseId !== courseId;
      API.practice.modes().then(ms => {
        if (stale()) return;
        // 随机练习的题量口径 = 「学过且做错过」的知识点题量（后端按此统计）。
        // 若为 0（已学的全对了 / 压根没做过题），按钮前置提示，不必等组卷回来才知道。
        this._randomCount = ((ms || []).find(x => x.key === 'random') || {}).count || 0;
        API.student.dashboard().then(d => {
          if (stale()) return;
          // 记住薄弱知识点 kpId，供「薄弱点强化」/「靶向强化出题」按知识点组卷
          this._weakKpIds = (d.weakPoints || []).map(w => w.kpId).filter(Boolean);
          // 薄弱点与预警共用门槛（同一知识点至少作答 2 道不同题）：没有达标的知识点时给明确说明，
          // 不留空白横幅，也不让「薄弱点强化」静默退化成整门课随机（后端同样会返回空池）。
          const wps = d.weakPoints || [];
          const weakBanner = wps.length
            ? `<b>系统已为你定位 ${wps.length} 个薄弱知识点</b>` +
              wps.map(w => `<span class="badge badge--danger" style="margin:4px 4px 0 0">${U.esc(w.name)} ${w.accuracyRate}%</span>`).join('') +
              `<div style="margin-top:6px">推荐使用「薄弱点强化」模式，习题将自动命中上述知识点并按前后置关系排序。</div>`
            : `<b>暂无可定位的薄弱知识点</b><div style="margin-top:6px">` +
              `每个知识点<b>至少作答 2 道不同题</b>（与预警同一门槛）后才会计入薄弱点与靶向练习；` +
              `可先用「顺序练习」或「随机练习」积累答题记录。</div>`;
          const weakSugs = wps.length
            ? wps.map(w => `
                <div class="todo">
                  <div class="todo__ico todo__ico--${w.level}">${icon('target')}</div>
                  <div class="todo__main"><b>${U.esc(w.name)}</b>
                    <span>正确率 ${w.accuracyRate}% · 建议 ${Math.ceil((60 - w.accuracyRate) / 5)} 组靶向练习</span></div>
                  <button class="btn btn--sm btn--outline" data-weak-start data-weak-kp="${U.esc(w.kpId)}">出题</button>
                </div>`).join('')
            : R.empty('暂无靶向强化建议', '同一知识点作答 2 道以上不同题后，这里会给出针对性建议', 'target');
          box.innerHTML = `
          <div class="callout ${wps.length ? 'callout--brand' : 'callout--warn'}" style="margin-bottom:16px">
            ${icon(wps.length ? 'sparkle' : 'info')}
            <div>${weakBanner}</div>
          </div>

          <div class="grid g-4" id="modeGrid" style="margin-bottom:16px">
            ${ms.map(m => `
              <div class="card" style="cursor:pointer;position:relative" data-mode="${m.key}">
                ${m.recommend ? '<span class="badge badge--brand" style="position:absolute;top:12px;right:12px">推荐</span>' : ''}
                <div class="card__body">
                  <div class="todo__ico ${m.recommend ? 'todo__ico--brand' : 'todo__ico--ok'}" style="margin-bottom:10px">${icon(m.icon)}</div>
                  <b style="font-size:14.5px;display:block">${m.name}</b>
                  <p class="fz-12 t-dim" style="margin:5px 0 12px;line-height:1.6">${m.desc}</p>
                  <div class="row fz-12"><span class="badge badge--outline">${m.count} 题</span><span class="spacer"></span>
                    <span class="t-brand fw-6 row" style="gap:3px">开始 ${icon('arrowRight')}</span></div>
                </div>
              </div>`).join('')}
          </div>

          <div id="modePanel" class="mode-panel" hidden></div>

          <div class="card">
            <div class="card__head"><h3>${icon('target')} 靶向强化建议</h3></div>
            <div class="card__body stack" style="gap:10px">
              ${weakSugs}
            </div>
          </div>`;

        U.$$('#modeGrid .card[data-mode]', box).forEach(c => c.addEventListener('click', () => {
          const mode = c.dataset.mode;
          if (this.activeMode === mode) { this.collapsePanel(); return; }
          this.enterMode(mode, ms, c);
        }));
        U.$$('[data-weak-start]', box).forEach(b => b.addEventListener('click', e => {
          e.stopPropagation();
          const kp = b.dataset.weakKp;
          this.expandPanel('weak', ms, box.querySelector('#modeGrid .card[data-mode="weak"]'), kp ? { kpIds: [kp] } : undefined);
        }));
        // 从「预警 → 去补救」进入：直接按该知识点开一组靶向练习
        if (this._pendingTarget) {
          const pt = this._pendingTarget; this._pendingTarget = null;
          if (pt.kpId) {
            const panel = U.$('#modePanel');
            if (panel) panel.hidden = false;
            Toast.info('靶向练习', `已按「${pt.kpName || pt.kpId}」组卷`);
            this.start('weak', ms, { kpIds: [pt.kpId] });
            return;
          }
        }
        // 从「待办 → 继续练习」进入：自动打开对应模式的存档面板
        if (this._pendingResume) {
          const pr = this._pendingResume; this._pendingResume = null;
          const mode = pr.mode || 'order';
          const card = box.querySelector(`#modeGrid .card[data-mode="${mode}"]`);
          if (card) this.enterMode(mode, ms, card);
        }
        });
      });
    },

    /* --- 内联展开 / 收起 --- */
    expandPanel(mode, ms, cardEl, opts) {
      this.activeMode = mode;
      U.$$('#modeGrid .card[data-mode]').forEach(c => c.classList.toggle('is-active', c === cardEl));
      const panel = U.$('#modePanel');
      if (panel) panel.hidden = false;
      this.start(mode, ms, opts);
    },
    collapsePanel() {
      clearInterval(this._timer);
      this.activeMode = null;
      this.state = 'select';
      const panel = U.$('#modePanel');
      if (panel) {
        panel.hidden = true;
        panel.innerHTML = '';
        U.$$('#modeGrid .card[data-mode]').forEach(c => c.classList.remove('is-active'));
      }
      // 无论从哪个 tab 进入练习，退出后必须能回到一个列表视图。
      // 错题本 tab 没有 #modePanel，原有逻辑只清理 panel 会导致 quiz 卡片残留
      // 出现「无法有效退出」的问题。这里按 _startTab 恢复到对应列表。
      const startTab = this._startTab || this.tab;
      if (startTab === 'wrong') {
        if (this.tab !== 'wrong') {
          this.tab = 'wrong';
          U.$$('#pTabs button').forEach(b => b.classList.toggle('is-active', b.dataset.t === 'wrong'));
        }
        this.renderWrong(this.lastWrongFilter || 'false');
      } else {
        if (this.tab !== 'quiz') {
          this.tab = 'quiz';
          U.$$('#pTabs button').forEach(b => b.classList.toggle('is-active', b.dataset.t === 'quiz'));
        }
        this.renderSelect();
      }
    },

    /* --- 练习入口（任意模式）：检查存档 → 继续挑战 / 开始新练习 --- */
    enterMode(mode, ms, cardEl) {
      const courseId = API.config.activeCourseId;
      this.activeMode = mode;
      U.$$('#modeGrid .card[data-mode]').forEach(c => c.classList.toggle('is-active', c === cardEl));
      const panel = U.$('#modePanel');
      if (panel) panel.hidden = false;
      panel.innerHTML = `<div class="card"><div class="card__body t-dim fz-13">检查存档…</div></div>`;
      API.practice.current({ mode }).then(sv => {
        if (API.config.activeCourseId !== courseId) return;
        // 有实际作答进度、且未做完，才算「存档」；空会话（0 题）不提示
        if (sv && sv.sessionId && sv.answered > 0 && sv.answered < sv.total) this._renderResumePanel(mode, ms, sv);
        else this._startMode(mode, ms);
      }).catch(() => this._startMode(mode, ms));
    },

    /* --- 正常开始某模式（顺序练习先选章节，其余直接组卷）--- */
    _startMode(mode, ms) {
      if (mode === 'order') { this._renderChapterPick(ms); return; }
      const card = U.$(`#modeGrid .card[data-mode="${mode}"]`);
      if (mode === 'weak' && !(this._weakKpIds || []).length) {
        // 没有达标的薄弱点（未作答，或每个知识点都不到 2 道题）：不要退化成"整门课随机抽"
        Toast.warn('暂无可定位的薄弱知识点', '每个知识点至少作答 2 道不同题后才会计入（与预警同一门槛），可先用顺序/随机练习');
        return;
      }
      if (mode === 'random' && !this._randomCount) {
        // 随机练习范围 = 「学过且做错过」的知识点。已学的全对、或还没做过题时无可抽范围，
        // 说明原因并给替代路径，不静默抽整门课（后端同样返回 emptyReason: random_scope_empty）。
        Toast.warn('随机练习暂无可抽题范围', '随机练习只抽「学过且做错过」的知识点；你学过的都答对了、或还没做过题，可先用顺序练习');
        return;
      }
      const opts = mode === 'weak' ? { kpIds: this._weakKpIds } : undefined;
      this.expandPanel(mode, ms, card, opts);
    },

    /* --- 有存档时先选「继续挑战 / 开始新练习」（任意模式）--- */
    _renderResumePanel(mode, ms, sv) {
      const MODE_CN = { weak: '薄弱点强化', order: '顺序练习', random: '随机练习', wrong: '错题重练' };
      const panel = U.$('#modePanel');
      panel.innerHTML = `
      <div class="card">
        <div class="card__head">
          <button class="btn btn--sm btn--ghost" id="rsBack">${icon('arrowLeft')} 返回</button>
          <span class="badge badge--brand">${MODE_CN[mode] || mode}</span>
          <h3 style="margin-left:6px">发现未完成的练习</h3>
        </div>
        <div class="card__body">
          <div class="callout callout--brand">${icon('clock')}
            <div><b>你上次练到一半</b><div class="fz-12 t-dim" style="margin-top:2px">已完成 ${sv.answered}/${sv.total} 题，可继续上次进度。</div></div>
          </div>
          <div class="row" style="margin-top:14px">
            <button class="btn btn--primary" id="rsContinue">${icon('arrowRight')} 继续挑战（${sv.answered}/${sv.total}）</button>
            <button class="btn btn--outline" id="rsNew">开始新练习</button>
          </div>
        </div>
      </div>`;
      U.$('#rsBack', panel).addEventListener('click', () => this.collapsePanel());
      U.$('#rsNew', panel).addEventListener('click', () => this._startMode(mode, ms));
      U.$('#rsContinue', panel).addEventListener('click', () => this.resume(sv));
    },

    /* --- 顺序练习：选择章节 / 知识点 --- */
    _renderChapterPick(ms) {
      const courseId = API.config.activeCourseId;
      const panel = U.$('#modePanel');
      if (panel) panel.hidden = false;
      const mCount = ((ms || []).find(x => x.key === 'order') || {}).count || 20;
      panel.innerHTML = `<div class="card"><div class="card__body t-dim fz-13">加载章节…</div></div>`;
      // 同时取「各知识点已发布题量」：没有题的知识点选了也组不出卷，直接不显示（2026-09-24）。
      Promise.all([
        API.graph.get({ type: 'knowledge' }),
        API.practice.kpPool().catch(() => null),
      ]).then(([g, pool]) => {
        if (API.config.activeCourseId !== courseId) return;
        // 题量接口失败时（pool=null）退回旧行为：全部列出，不做隐藏 ——
        // 宁可多显示几个按钮，也不能因为一次请求失败就让学生以为"这门课没题"。
        const counts = (pool && pool.counts) ? pool.counts : null;
        const hasQ = (kpId) => !counts || (counts[kpId] > 0);
        const byCh = {};
        (g.nodes || []).forEach(n => {
          if (!hasQ(n.id)) return;              // 该知识点没有已发布题目 → 不列出
          const ch = n.chapter || '其它';
          (byCh[ch] = byCh[ch] || []).push(n);
        });
        const chapters = Object.keys(byCh).sort((a, b) => a.localeCompare(b, 'zh'));
        // 整章都没有题 → 这一章连标题带「整章练习」一起不显示
        if (!chapters.length) {
          panel.innerHTML = `<div class="card"><div class="card__body">
            <div class="callout callout--warn">${icon('info')}<div><b>暂无可练习的知识点</b>
            <div class="fz-12 t-dim">当前课程的题库里还没有已发布的题目，可先用「薄弱点强化」或「错题重练」，或等教师补充题目。</div></div></div>
          </div></div>`;
          return;
        }
        // 一屏平铺所有章节 + 各自知识点
        const sections = chapters.map(ch => {
          const kps = byCh[ch].slice().sort((a, b) => a.id.localeCompare(b.id));
          return `
            <div style="padding:14px 0;border-bottom:1px solid var(--border)">
              <div class="row" style="align-items:center;gap:10px;margin-bottom:10px">
                <b style="font-size:14.5px">${U.esc(ch)}</b>
                <span class="t-dim fz-12">${kps.length} 个可练习知识点</span>
                <span class="spacer"></span>
                <button class="btn btn--sm btn--outline" data-kp="__all__" data-ch="${U.esc(ch)}">整章练习</button>
              </div>
              <div class="row" style="flex-wrap:wrap;gap:8px">
                ${kps.map(k => `<button class="btn btn--sm btn--outline" data-kp="${U.esc(k.id)}">${U.esc(k.name)}${counts ? `<span class="t-dim" style="margin-left:6px;font-size:11px">${counts[k.id] || 0} 题</span>` : ''}</button>`).join('')}
              </div>
            </div>`;
        }).join('');
        panel.innerHTML = `
        <div class="card">
          <div class="card__head">
            <button class="btn btn--sm btn--ghost" id="chBack">${icon('arrowLeft')} 返回</button>
            <span class="badge badge--brand">顺序练习</span>
            <h3 style="margin-left:6px">选择章节 / 知识点</h3>
            <span class="spacer"></span>
            <span class="fz-12 t-dim">只列出有题目的知识点 · 点「整章练习」或具体知识点开始</span>
          </div>
          <div class="card__body" style="padding-top:4px">${sections}</div>
        </div>`;
        U.$('#chBack', panel).addEventListener('click', () => this.collapsePanel());
        U.$$('[data-kp]', panel).forEach(b => b.addEventListener('click', () => {
          const kp = b.dataset.kp;
          const kpIds = (kp === '__all__') ? byCh[b.dataset.ch].map(k => k.id) : [kp];
          this.start('order', ms, { kpIds, count: mCount });
        }));
      }).catch(() => {
        panel.innerHTML = `<div class="card"><div class="card__body t-dim">章节加载失败，请重试</div></div>`;
      });
    },

    /* --- 继续挑战：载入存档，从第一道未答题继续 --- */
    resume(sv) {
      this.mode = sv.mode || 'order';
      this.qs = sv.questions || [];
      this.sessionId = sv.sessionId;
      this.answers = {};
      this.qs.forEach(q => { if (q.answered) this.answers[q.qId] = q.myAnswer; });
      const idx = this.qs.findIndex(q => !q.answered);
      this.idx = idx >= 0 ? idx : 0;
      this.state = 'quiz';
      Toast.ok('已继续上次进度', `第 ${this.idx + 1} / ${this.qs.length} 题`);
      this.renderQuiz();
    },

    /* --- 开始练习 --- */
    start(mode, ms, opts) {
      const courseId = API.config.activeCourseId;
      const m = (ms || []).find(x => x.key === mode);
      // 记录进入练习时的 tab，退出时按此恢复到对应列表
      this._startTab = this.tab;
      this._lastKpIds = (opts && opts.kpIds && opts.kpIds.length) ? opts.kpIds : undefined;
      this._lastQIds = (opts && opts.qIds && opts.qIds.length) ? opts.qIds : undefined;
      const body = { mode, count: (opts && opts.count) || (m ? m.count : 10) };
      if (this._lastKpIds) body.kpIds = this._lastKpIds;
      if (this._lastQIds) body.qIds = this._lastQIds;
      API.practice.create(body).then(s => {
        if (API.config.activeCourseId !== courseId) return;
        if (!s.questions || !s.questions.length) {
          this.qs = [];
          this.state = 'select';
          const target = U.$('#modePanel') || U.$('#pBody');
          // 指定了知识点却组不出题（该知识点暂无题 / 切换课程后的残留 kpId）：
          // 提示要具体，不能笼统说"当前课程无题"，否则学生会以为整门课都没有题。
          const byKp = !!(body.kpIds && body.kpIds.length);
          const weakNoKp = body.mode === 'weak' && !byKp;      // 薄弱点强化但无可定位的薄弱点
          const randomEmpty = s.emptyReason === 'random_scope_empty';  // 随机练习范围（学过且有错）为空
          const title = randomEmpty ? '随机练习无可抽题范围'
                      : weakNoKp ? '暂无可定位的薄弱知识点'
                      : byKp ? '该知识点暂无可用题目'
                             : '当前课程暂无可练习题目';
          const hint = randomEmpty ? '随机练习只抽「学过且做错过」的知识点；你学过的都答对了、或还没做过题，可先用顺序练习。'
                     : weakNoKp ? '每个知识点至少作答 2 道不同题后才会计入（与预警同一门槛），可先用顺序/随机练习。'
                     : byKp ? '可改用「顺序练习」或「随机练习」，或等教师补充该知识点的题目。'
                            : '请等待教师发布题目后再开始练习。';
          if (target) target.innerHTML = `<div class="callout callout--warn">${icon('info')}<div><b>${title}</b><div class="fz-12 t-dim">${hint}</div></div></div>`;
          Toast.warn(title);
          return;
        }
        this.mode = mode; this.qs = s.questions; this.idx = 0; this.answers = {};
        this.sessionId = s.sessionId;  // 保存真实 sessionId，后续 submit/finish 要用
        this.state = 'quiz';
        Toast.ok('已组卷 ' + this.qs.length + ' 题', m ? m.name : '');
        this.renderQuiz();
      });
    },

    /**
     * 图题渲染（源自课后题库/智能出题的 figure 规格）
     * figureMode 优先级：options_graph → graph（含 adjacency_matrix）→ has_image 纯文本提示
     * 绘制由 assets/js/st/ds-figure.js 的 DsFigure 完成（含边权标签防遮挡）
     */
    mountQFigure(rootEl, figure) {
      if (!rootEl || !figure || !window.DsFigure) return;
      const figEl = rootEl.querySelector('#qFig') || rootEl.querySelector('#wrongFig');
      if (figEl) {
        if (figure.graph) {
          DsFigure.mount(figEl, figure.graph);
        } else if (figure.has_image) {
          figEl.innerHTML = '<div class="callout callout--warn" style="padding:8px 12px">本题配图暂不绘制，请按纯文本作答。</div>';
        }
      }
      if (figure.options_graph) {
        Object.keys(figure.options_graph).forEach(k => {
          const slot = rootEl.querySelector(`[data-optfig="${k}"]`);
          if (slot) DsFigure.mount(slot, figure.options_graph[k]);
        });
      }
    },

    renderQuiz() {
      const q = this.qs[this.idx];
      this.picked = null; this.startAt = Date.now(); this._submitting = false;
      const modeName = { weak: '薄弱点强化', order: '顺序练习', random: '随机练习', wrong: '错题重练' }[this.mode];
      // 渲染目标：错题本 tab 没有 #modePanel，直接覆盖 #pBody；智能练习 tab 优先用 #modePanel 实现「内联展开」。
      const panel = U.$('#modePanel');
      const target = (this.tab === 'wrong') ? U.$('#pBody') : ((panel && !panel.hidden) ? panel : U.$('#pBody'));
      target.innerHTML = `
      <div class="card">
        <div class="quiz-head">
          <button class="btn btn--sm btn--ghost" id="qBack">${icon('arrowLeft')} 退出</button>
          <span class="badge badge--brand">${modeName}</span>
          <div class="quiz-prog">
            <div class="row fz-12" style="margin-bottom:4px">
              <span class="t-dim">进度</span><span class="spacer"></span>
              <span class="mono fw-6">${this.idx + 1} / ${this.qs.length}</span>
            </div>
            ${U.bar((this.idx / this.qs.length) * 100, 'good', 'sm')}
          </div>
          <span class="badge badge--outline">难度 ${U.stars(q.difficulty)}</span>
          <span class="badge badge--outline mono" id="qTimer">00:00</span>
        </div>

        <div class="q-body">
          <div class="q-stem"><span class="q-no">${this.idx + 1}</span>${q.stem}</div>
          <div class="q-figure" id="qFig"></div>
          <div class="opts" id="opts">
            ${q.options.map(o => `
              <button class="opt" data-k="${o.key}">
                <span class="opt__key">${o.key}</span>
                <span style="flex:1">${o.text}</span>
                ${q.figure && q.figure.options_graph && q.figure.options_graph[o.key] ? `<div class="q-opt-fig" data-optfig="${o.key}"></div>` : ''}
              </button>`).join('')}
          </div>
          <div id="fbBox"></div>
        </div>

        <div class="card__foot row">
          <span class="fz-12 t-dim">知识点定位：${(q.kpPath || []).join(' › ') || '—'}</span>
          <span class="spacer"></span>
          <button class="btn btn--primary" id="qSubmit" disabled>提交答案</button>
        </div>
      </div>`;

      // 计时
      clearInterval(this._timer);
      this._timer = setInterval(() => {
        const s = Math.floor((Date.now() - this.startAt) / 1000);
        const t = U.$('#qTimer');
        if (t) t.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
        else clearInterval(this._timer);
      }, 1000);

      U.$('#qBack').addEventListener('click', () => { clearInterval(this._timer); this.collapsePanel(); });
      this.mountQFigure(target, q.figure);
      U.$$('#opts .opt').forEach(o => o.addEventListener('click', () => {
        U.$$('#opts .opt').forEach(x => x.classList.remove('is-picked'));
        o.classList.add('is-picked');
        this.picked = o.dataset.k;
        U.$('#qSubmit').disabled = false;
      }));
      U.$('#qSubmit').addEventListener('click', () => this.submit(q));
      if (this.idx === 0 && target.scrollIntoView) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    submit(q) {
      // 防重入：禁用提交按钮 + 设 flag，防止 API 未返回时用户再次点击导致 badge 重复追加
      if (this._submitting) return;
      this._submitting = true;
      const btn = U.$('#qSubmit');
      if (btn) btn.disabled = true;
      clearInterval(this._timer);
      const dur = Math.floor((Date.now() - this.startAt) / 1000);
      const sid = this.sessionId || 'cur';
      API.practice.submitAnswer({ sessionId: sid, qId: q.qId, answer: this.picked, durationSeconds: dur }).then(r => {
        this.answers[q.qId] = r;
        // 标注选项：先清除之前可能残留的 badge（防重复渲染），再加一次
        U.$$('#opts .opt').forEach(o => {
          o.classList.add('is-disabled');
          // 移除已有的 opt__flag badge（防止多次提交时叠加）
          o.querySelectorAll('.opt__flag').forEach(b => b.remove());
          if (o.dataset.k === r.rightAnswer) {
            o.classList.remove('is-picked'); o.classList.add('is-right');
            o.insertAdjacentHTML('beforeend', `<span class="opt__flag badge badge--ok">正确答案</span>`);
          } else if (o.dataset.k === this.picked) {
            o.classList.remove('is-picked'); o.classList.add('is-wrong');
            o.insertAdjacentHTML('beforeend', `<span class="opt__flag badge badge--danger">你的选择</span>`);
          }
        });

        // 知识点定位树：题库里 kp_path 有 2 级也有 3 级，按实际层级渲染，
        // 不能写死 kpPath[0..2]（否则二级路径的最后一行会显示 undefined）
        const path = (r.kpPath || []).map(x => String(x || '')).filter(Boolean);
        if (!path.length && q.kpPath && q.kpPath.length) path.push(...q.kpPath);
        const leafIdx = Math.max(0, path.length - 1);
        const pathHtml = path.map((p, i) => {
          const isLeaf = i === leafIdx;
          const cls = isLeaf ? 'kp-tree__row--leaf' : (i ? 'kp-tree__row--sub' : '');
          const ic = isLeaf ? 'target' : (i ? 'chevronRight' : 'folder');
          const inner = isLeaf
            ? `<b class="t-brand">${U.esc(p)}</b>${q.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}`
            : (i ? `<span>${U.esc(p)}</span>` : `<b>${U.esc(p)}</b>`);
          return `<div class="kp-tree__row ${cls}">${icon(ic)}${inner}</div>`;
        }).join('');

        U.$('#fbBox').innerHTML = `
        <div class="feedback feedback--${r.correct ? 'ok' : 'no'}">
          <div class="feedback__head">${icon(r.correct ? 'checkCircle' : 'xCircle')}
            ${r.correct ? '回答正确' : '回答错误'}
            <span class="spacer"></span>
            <span class="fz-12" style="font-weight:500">用时 ${dur}s · 班级平均 ${r.avgSeconds}s · 班级正确率 ${r.classCorrectRate}%</span>
          </div>
          <div class="feedback__body">
            <div class="feedback__sec">
              <h5>题目解析</h5>
              <div>${r.analysis || '暂无解析'}</div>
            </div>
            <div class="feedback__sec">
              <h5>知识点定位树</h5>
              <div class="kp-tree">${pathHtml || '<div class="kp-tree__row kp-tree__row--leaf">' + icon('target') + '<b class="t-brand">未标注知识点</b></div>'}</div>
              <div class="row row--wrap fz-12 t-dim" style="margin-top:9px">
                <span>前置知识点：</span>${(q.preKp || []).length ? (q.preKp || []).map(k => `<span class="badge badge--outline">${U.esc(k)}</span>`).join('') : '<span>—</span>'}
              </div>
            </div>
            <div class="feedback__sec">
              <h5>学情回写</h5>
              <div class="row row--wrap">
                <span class="badge ${r.masteryDelta >= 0 ? 'badge--ok' : 'badge--danger'}">
                  掌握率 ${r.masteryDelta >= 0 ? '+' : ''}${r.masteryDelta}pp</span>
                <span class="badge badge--outline">${r.correct ? '完成率已更新' : '已自动归入错题本'}</span>
              </div>
            </div>
          </div>
        </div>`;

        const foot = U.$('#qSubmit');
        foot.textContent = this.idx < this.qs.length - 1 ? '下一题' : '查看练习报告';
        foot.disabled = false;
        foot.replaceWith(foot.cloneNode(true));
        U.$('#qSubmit').addEventListener('click', () => {
          if (this.idx < this.qs.length - 1) { this.idx++; this.renderQuiz(); }
          else API.practice.finish({ sessionId: sid })
            .then(rep => this.renderReport(rep))
            .catch(err => Toast.error('报告加载失败', err && err.message || '请重试'));
        });
        this._submitting = false;
      }).catch(err => {
        // 提交失败时也清除 flag 并恢复按钮
        this._submitting = false;
        if (btn) { btn.disabled = false; btn.textContent = '提交答案'; }
        // 后端异常会把原始错误带回来（如 SQL 报错），对学习者只给一行可读提示
        const msg = String((err && err.message) || '').replace(/\s+/g, ' ').trim();
        Toast.err('提交失败', msg ? (msg.length > 60 ? msg.slice(0, 60) + '…' : msg) : '请重试');
      });
    },

    /* --- 练习报告 --- */
    renderReport(r) {
      this.state = 'report';
      if (!r) { Toast.error('报告加载失败', '后端返回空数据'); return; }
      const panel = U.$('#modePanel');
      const target = (panel && !panel.hidden) ? panel : U.$('#pBody');
      const kpChanges = r.kpChanges || [];
      const wrongByKp = r.wrongByKp || [];
      target.innerHTML = `
      <div class="grid g-4" style="margin-bottom:16px">
        <div class="stat" style="--_c:var(--ok)"><div class="stat__label">正确率</div>
          <div class="stat__value">${r.accuracy ?? 0}<small>%</small></div>
          <div class="stat__hint">班级平均 ${r.classAccuracy ?? 0}% ${U.delta((r.accuracy ?? 0) - (r.classAccuracy ?? 0))}</div></div>
        <div class="stat" style="--_c:var(--brand-500)"><div class="stat__label">答对 / 总题数</div>
          <div class="stat__value">${r.correct ?? 0}<small>/${r.total ?? 0}</small></div>
          <div class="stat__hint">错题 ${r.wrong ?? 0} 道已归入错题本</div></div>
        <div class="stat" style="--_c:var(--info)"><div class="stat__label">总用时</div>
          <div class="stat__value">${U.dur(r.durationSeconds)}</div>
          <div class="stat__hint">均每题 ${r.avgSeconds ?? 0} 秒</div></div>
        <div class="stat" style="--_c:var(--accent-500)"><div class="stat__label">能力目标增益</div>
          <div class="stat__value">+${r.scoreGain ?? 0}</div></div>
      </div>

      ${(r.masteredCount > 0) ? `<div class="callout" style="margin-bottom:16px">${icon('checkCircle')}<div><b>${r.masteredCount} 道答对题目已自动标记为「已掌握」</b><span class="fz-12 t-dim" style="margin-left:6px">可到错题本「已掌握」查看</span></div></div>` : ''}

      <div class="grid g-21" style="margin-bottom:16px">
        <div class="card">
          <div class="card__head"><h3>${icon('trend')} 薄弱点变化对比</h3><span class="spacer"></span>
            <span class="badge badge--outline">练习前 vs 练习后</span></div>
          <div class="card__body">
            ${kpChanges.length ? `<div class="chart chart--sm" id="kpChangeChart"></div>` : `<p class="fz-12 t-dim">本次练习未涉及已跟踪知识点变化</p>`}
            ${kpChanges.length ? `<div class="stack" style="gap:10px;margin-top:8px">
              ${kpChanges.map(k => `
                <div class="row fz-13">
                  <span style="flex:1;min-width:0" class="nowrap">${U.esc(k.name)}</span>
                  <div style="width:120px">${U.bar(k.after)}</div>
                  <span class="mono t-dim" style="width:38px;text-align:right">${k.before}%</span>
                  <span class="t-dim">→</span>
                  <span class="mono fw-6" style="width:38px">${k.after}%</span>
                  <span class="badge ${k.delta >= 0 ? 'badge--ok' : 'badge--danger'}" style="width:52px;justify-content:center">${k.delta > 0 ? '+' : ''}${k.delta}pp</span>
                </div>`).join('')}
            </div>` : ''}
          </div>
        </div>
        <div class="card">
          <div class="card__head"><h3>${icon('alert')} 错题知识点分布</h3></div>
          <div class="card__body">
            ${wrongByKp.length ? `<div class="chart chart--sm" id="wrongKpChart"></div>` : `<p class="fz-12 t-dim">本次没有错题，继续保持！</p>`}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card__head"><h3>${icon('bulb')} 下一步建议</h3></div>
        <div class="card__body">
          <div class="callout callout--brand">${icon('sparkle')}<div><b>AI 学习路径建议</b>${U.esc(r.nextSuggestion || '')}</div></div>
          <div class="row" style="margin-top:14px">
            <button class="btn btn--primary" id="againBtn">${icon('refresh')} 再练一组</button>
            <button class="btn btn--outline" id="toWrong">查看错题本</button>
            <button class="btn" id="toMastery">查看我的学情</button>
            <span class="spacer"></span>
            <button class="btn btn--ghost" id="backSelect">返回练习首页</button>
          </div>
        </div>
      </div>`;

      if (kpChanges.length) {
        Charts.line('#kpChangeChart', {
          xAxis: kpChanges.map(k => k.name.length > 8 ? k.name.slice(0, 8) + '…' : k.name),
          series: [
            { name: '练习前', data: kpChanges.map(k => k.before), color: Charts.tokens().dim, dashed: true },
            { name: '练习后', data: kpChanges.map(k => k.after), color: Charts.tokens().ok }
          ]
        }, { area: true, max: 100 });
      }
      if (wrongByKp.length) {
        Charts.bar('#wrongKpChart', wrongByKp.map(e => ({ name: e.name, value: e.count })),
          { horizontal: true, showLabel: true, minInterval: 1, labelFmt: '{c} 题' });
      }

      U.$('#againBtn').addEventListener('click', () => API.practice.modes().then(ms => this.start(this.mode || 'weak', ms, { kpIds: this._lastKpIds, qIds: this._lastQIds })));
      U.$('#toWrong').addEventListener('click', () => {
        U.$$('#pTabs button').forEach(x => x.classList.toggle('is-active', x.dataset.t === 'wrong'));
        this.renderWrong();
      });
      U.$('#toMastery').addEventListener('click', () => Router.go('mastery'));
      U.$('#backSelect').addEventListener('click', () => this.renderSelect());
    },

    /* --- 错题本（含「按章节 → 知识点」归纳筛选） --- */
    renderWrong(filter) {
      const courseId = API.config.activeCourseId;
      const f = filter || 'false';
      this.lastWrongFilter = f;
      this.tab = 'wrong';
      const chapter = this._wChapter || '';
      const kpId = this._wKpId || '';
      const box = U.$('#pBody');
      API.practice.wrongBook({
        mastered: f,
        chapter: chapter || undefined,
        kpId: kpId || undefined,
      }).then(r => {
        // 竞态防护：请求期间用户已切走（如切回「智能练习」）就不再覆盖页面
        if (this.tab !== 'wrong' || U.$('#pBody') !== box || API.config.activeCourseId !== courseId) return;
        const groups = r.groups || [];
        // 归纳面板里的知识点名（用于「已筛选」回显）
        let kpLabel = kpId;
        groups.some(g => g.kps.some(k => {
          if (k.kpId === kpId) { kpLabel = k.name; return true; }
          return false;
        }));
        const filtering = !!(chapter || kpId);
        const open = this._wSumOpen !== false;

        U.$('#pBody').innerHTML = `
        <div class="card" style="margin-bottom:16px">
          <div class="card__head">
            <h3>${icon('target')} 按章节知识点归纳</h3>
            <span class="badge badge--outline">${groups.length} 个章节</span>
            <span class="badge badge--outline">${groups.reduce((s, g) => s + g.total, 0)} 道错题</span>
            <span class="spacer"></span>
            ${filtering
              ? `<span class="badge badge--brand">筛选：${U.esc(chapter || '全部章节')}${kpId ? ' › ' + U.esc(kpLabel) : ''}</span>
                 <button class="btn btn--sm btn--ghost" id="wClearKp">清除筛选</button>`
              : '<span class="fz-12 t-dim">点章节 / 知识点可筛出下方错题</span>'}
            <button class="btn btn--sm btn--ghost" id="wSumToggle">${open ? '收起' : '展开'}</button>
          </div>
          <div class="card__body" id="wGroups" ${open ? '' : 'hidden'}>
            ${groups.length ? groups.map(g => `
              <div class="wb-group">
                <div class="row" style="align-items:center;gap:8px;margin-bottom:8px">
                  <button class="chip chip--chapter ${chapter === g.chapter ? 'is-active' : ''}"
                          data-ch="${U.esc(g.chapter)}" title="按本章筛选">
                    ${U.esc(g.chapter)}<span class="chip__count">${g.total}</span>
                  </button>
                  <span class="fz-12 t-dim">${g.kpCount} 个知识点</span>
                </div>
                <div class="chips-row">
                  ${g.kps.map(k => `
                    <button class="chip chip--kp ${kpId === k.kpId ? 'is-active' : ''}"
                            data-kp="${U.esc(k.kpId)}" data-kp-ch="${U.esc(g.chapter)}" title="按此知识点筛选">
                      ${U.esc(k.name)}<span class="chip__count">${k.count}</span>
                    </button>`).join('')}
                </div>
              </div>`).join('') : `<p class="fz-12 t-dim">当前分类下暂无错题，归纳数据为空</p>`}
          </div>
        </div>

        <div class="card">
          <div class="card__head">
            <h3>${icon('pencil')} 错题本</h3>
            <span class="badge badge--danger">${r.total} 题</span>
            <span class="spacer"></span>
            <div class="seg" id="wFilter">
              <button data-f="false" class="${f === 'false' ? 'is-active' : ''}">待攻克</button>
              <button data-f="true" class="${f === 'true' ? 'is-active' : ''}">已掌握</button>
              <button data-f="all" class="${f === 'all' ? 'is-active' : ''}">全部</button>
            </div>
            <button class="btn btn--sm btn--primary" id="wPractice">${icon('refresh')} 一键重练</button>
          </div>
          <div class="card__body card__body--flush">
            ${r.list.length ? r.list.map(w => `
              <div class="wrong-item" data-wrong-detail="${w.qId}" role="button" tabindex="0">
                <div class="row" style="margin-bottom:6px">
                  <span class="badge badge--outline mono">${w.qId}</span>
                  <span class="badge badge--danger">错 ${w.wrongCount} 次</span>
                  <span class="spacer"></span>
                  <span class="fz-11 t-dim">${w.lastTime}</span>
                </div>
                <div class="wrong-item__stem">${U.esc(w.stem)}</div>
                <div class="wrong-item__tags">
                  <span class="badge badge--brand">${U.esc(w.kpName || w.kp)}</span>
                  <span class="badge badge--outline">${U.esc(w.chapter || '未分章')}</span>
                  <span class="badge badge--outline">难度 ${U.stars(w.difficulty)}</span>
                  <span class="fz-12 t-dim">我的答案 <b class="t-danger">${w.myAnswer}</b> · 正确答案 <b class="t-ok">${w.answer}</b></span>
                  <span class="spacer"></span>
                  ${w.mastered ? '<span class="badge badge--ok">已掌握</span>'
              : `<button class="btn btn--xs btn--outline" data-redo="${w.qId}">重做</button>
                     <button class="btn btn--xs btn--ghost" data-mastered="${w.qId}">标记已掌握</button>`}
                </div>
              </div>`).join('')
            : R.empty(filtering ? '当前筛选下没有错题' : '太棒了，没有待攻克的错题',
                      filtering ? '试试清除筛选或切换上方分类' : '继续保持，可以去做新的练习', filtering ? 'search2' : 'award')}
          </div>
        </div>`;

        // ---- 归纳面板交互：章节 / 知识点 chip 切换筛选 ----
        U.$$('#wGroups .chip--chapter[data-ch]').forEach(c => c.addEventListener('click', () => {
          const ch = c.dataset.ch;
          this._wChapter = (this._wChapter === ch) ? '' : ch;
          this._wKpId = '';                       // 换章时清掉知识点筛选，避免出现空列表
          this.renderWrong(f);
        }));
        U.$$('#wGroups .chip--kp[data-kp]').forEach(c => c.addEventListener('click', () => {
          const kp = c.dataset.kp;
          this._wKpId = (this._wKpId === kp) ? '' : kp;
          this._wChapter = '';                    // 选知识点时不再限定章节
          this.renderWrong(f);
        }));
        const clearBtn = U.$('#wClearKp');
        if (clearBtn) clearBtn.addEventListener('click', () => {
          this._wChapter = ''; this._wKpId = '';
          this.renderWrong(f);
        });
        const sumBtn = U.$('#wSumToggle');
        if (sumBtn) sumBtn.addEventListener('click', () => {
          this._wSumOpen = !open;
          this.renderWrong(f);
        });

        U.$$('#wFilter button').forEach(b => b.addEventListener('click', () => this.renderWrong(b.dataset.f)));
        U.$('#wPractice').addEventListener('click', () => {
          // 一键重练：只重练当前筛选下列表里显示的那些题
          const qIds = r.list.map(w => w.qId);
          if (!qIds.length) { Toast.err('当前分类下没有可重练的题目'); return; }
          API.practice.modes().then(ms => this.start('wrong', ms, { qIds, count: qIds.length }));
        });
        U.$$('[data-redo]').forEach(b => b.addEventListener('click', e => {
          e.stopPropagation();
          API.practice.modes().then(ms => {
            // 重做本题：只组卷这一个错题
            this.start('wrong', ms, { qIds: [b.dataset.redo] });
          });
        }));
        U.$$('[data-mastered]').forEach(b => b.addEventListener('click', () => {
          API.practice.removeWrong({ qId: b.dataset.mastered }).then(() => {
            Toast.ok('已标记为掌握', '该题移出待攻克列表');
            this.renderWrong(f);
          });
        }));
        // 错题详情：点错题项打开弹窗；点内部按钮不触发
        U.$$('[data-wrong-detail]', U.$('#pBody')).forEach(el => el.addEventListener('click', e => {
          if (e.target.closest('[data-redo], [data-mastered]')) return;
          this.openWrongDetail(el.dataset.wrongDetail, f);
        }));
      });
    },

    /* --- 错题详情弹窗 --- */
    openWrongDetail(qId, filter) {
      const f = filter || 'false';
      API.practice.wrongDetail({ qId }).then(d => {
        const optHtml = d.options.map(o => {
          const isRight = o.key === d.answer;
          const hasMini = d.figure && d.figure.options_graph && d.figure.options_graph[o.key];
          return `<div class="opt${isRight ? ' is-right' : ''}"><span class="opt__key">${o.key}</span><span style="flex:1">${o.text}</span>${hasMini ? `<div class="q-opt-fig" data-optfig="${o.key}"></div>` : ''}${isRight ? '<span class="opt__flag badge badge--ok">正确答案</span>' : ''}</div>`;
        }).join('');

        Modal.open({
          title: `错题详情 · ${d.qId}`,
            size: 'wide',
            body: `
              <div class="row fz-12 t-dim" style="margin-bottom:10px">
                <span class="badge badge--outline mono">${d.qId}</span>
                <span class="badge badge--brand">${U.esc(d.kpPath.join(' › '))}</span>
                <span class="badge badge--outline">难度 ${U.stars(d.difficulty)}</span>
                ${d.isKey ? '<span class="badge badge--danger">◆ 重难点</span>' : ''}
              </div>

              <div class="callout" style="margin-bottom:14px"><b style="font-size:14.5px;line-height:1.7">${d.stem}</b></div>
              <div class="q-figure" id="wrongFig" style="margin:-6px 0 14px"></div>

              <h5 class="fz-12 t-dim" style="margin:0 0 6px">选项</h5>
              <div class="opts opts--readonly" style="margin-bottom:14px">${optHtml}</div>

              <div class="grid g-3" style="margin-bottom:14px">
                <div class="stat" style="--_c:var(--danger)"><div class="stat__label">错题次数</div><div class="stat__value">${d.history.length}<small>次</small></div></div>
                <div class="stat" style="--_c:var(--info)"><div class="stat__label">班级正确率</div><div class="stat__value">${d.classCorrectRate}<small>%</small></div></div>
                <div class="stat" style="--_c:var(--brand-500)"><div class="stat__label">平均用时</div><div class="stat__value">${d.avgSeconds}<small>s</small></div></div>
              </div>

              <h5 class="fz-12 t-dim" style="margin:14px 0 6px">题目解析</h5>
              <div class="callout callout--brand" style="margin-bottom:14px">${d.analysis}</div>

              <div class="grid g-21" style="margin-bottom:14px">
                <div>
                  <h5 class="fz-12 t-dim" style="margin:0 0 6px">错题历史</h5>
                  ${d.history.length ? `<div class="stack" style="gap:6px">
                    ${d.history.map(h => `<div class="row fz-12">
                      <span class="t-dim">${h.time}</span>
                      <span class="spacer"></span>
                      <span>你的答案 <b class="t-danger">${h.answer}</b></span>
                      <span class="badge ${h.correct ? 'badge--ok' : 'badge--danger'}">${h.correct ? '已掌握' : '未掌握'}</span>
                    </div>`).join('')}
                  </div>` : '<p class="fz-12 t-dim">暂无</p>'}
                </div>
                <div>
                  <h5 class="fz-12 t-dim" style="margin:0 0 6px">相似题推荐</h5>
                  ${d.similar.length ? `<div class="stack" style="gap:6px">
                    ${d.similar.map(s => `<button class="ask-item" data-similar="${s.qId}">
                      ${icon('chevronRight')}<span><b>${U.esc(s.qId)} · ${U.esc(s.kp)}</b><br><span class="fz-11 t-dim">${U.esc(s.stem)}</span></span>
                    </button>`).join('')}
                  </div>` : '<p class="fz-12 t-dim">暂无</p>'}
                </div>
              </div>

              <h5 class="fz-12 t-dim" style="margin:14px 0 6px">推荐资源</h5>
              <div class="row row--wrap" style="gap:6px;margin-bottom:14px">
                ${d.resources.map(r => r.url
                  ? `<a class="badge badge--outline res-badge-link" href="${U.esc(r.url)}" target="_blank" rel="noopener noreferrer" data-res-id="${U.esc(r.resId)}" data-type="${U.esc(r.type)}" data-url="${U.esc(r.url)}" data-title="${U.esc(r.name)}">${icon(r.type === 'video' ? 'play' : 'file')} ${U.esc(r.name)} · <span class="t-dim">${U.esc(r.meta)}</span></a>`
                  : `<span class="badge badge--outline">${icon(r.type === 'video' ? 'play' : 'file')} ${U.esc(r.name)} · <span class="t-dim">${U.esc(r.meta)}</span></span>`
                ).join('') || '<span class="fz-12 t-dim">暂无推荐资源</span>'}
              </div>

              ${d.tips ? `<div class="callout" style="border-left:3px solid var(--ok);">${d.tips}</div>` : ''}
            `,
            footer: `
              <button class="btn btn--ghost" data-close>关闭</button>
              <button class="btn btn--outline" id="wdRedo">${icon('refresh')} 重做本题</button>
              <button class="btn btn--primary" id="wdMastered">${icon('check')} 标记已掌握</button>
            `,
            onMount(ov, close) {
              Practice.mountQFigure(ov, d.figure);
              U.$('#wdRedo', ov).addEventListener('click', () => {
                close();
                API.practice.modes().then(ms => Practice.start('wrong', ms, { qIds: [qId] }));
              });
              U.$('#wdMastered', ov).addEventListener('click', () => {
                API.practice.removeWrong({ qId }).then(() => {
                  Toast.ok('已标记为掌握', '该题移出待攻克列表');
                  close();
                  Practice.renderWrong(f);
                });
              });
              U.$$('[data-similar]', ov).forEach(b => b.addEventListener('click', () => {
                Toast.ok('已加入练习计划', '可在错题重练中找到');
                close();
              }));
              U.$$('.res-badge-link', ov).forEach(a => a.addEventListener('click', e => {
                e.preventDefault();
                const res = {
                  resId: a.dataset.resId, type: a.dataset.type, title: a.dataset.title,
                  kp: '', duration: '', pages: 0, url: a.dataset.url
                };
                if (res.resId) API.student.resourceView({ resId: res.resId }).catch(() => {});
                if (window.ResourceView) ResourceView.openResource(res);
              }));
            }
          });
        }).catch(err => Toast.error('详情加载失败', err && err.message || ''));
    }
  };

Router.register('practice', {
  title: '智能练习',
  mount: () => Practice.render(),
  reset: () => Practice.resetCourseContext(),
  // 已 mount 过时再次进入：只在带「继续挑战」待办时重绘（否则会打断进行中的练习）
  update: () => { if (Practice._pendingResume) Practice.render(); },
});
