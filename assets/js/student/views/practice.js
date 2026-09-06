'use strict';

  /* ================================================================
     视图 5 · 智能练习 / 专属题库
     ================================================================ */
  const Practice = {
    tab: 'quiz', state: 'select', mode: null,
    qs: [], idx: 0, answers: {}, picked: null, startAt: 0,

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
      API.practice.modes().then(ms => {
        API.student.dashboard().then(d => {
          // 记住薄弱知识点 kpId，供「薄弱点强化」/「靶向强化出题」按知识点组卷
          this._weakKpIds = (d.weakPoints || []).map(w => w.kpId).filter(Boolean);
          box.innerHTML = `
          <div class="callout callout--brand" style="margin-bottom:16px">
            ${icon('sparkle')}
            <div><b>系统已为你定位 ${d.weakPoints.length} 个薄弱知识点</b>
            ${d.weakPoints.map(w => `<span class="badge badge--danger" style="margin:4px 4px 0 0">${U.esc(w.name)} ${w.masteryRate}%</span>`).join('')}
            <div style="margin-top:6px">推荐使用「薄弱点强化」模式，习题将自动命中上述知识点并按前后置关系排序。</div></div>
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
              ${d.weakPoints.map(w => `
                <div class="todo">
                  <div class="todo__ico todo__ico--${w.level}">${icon('target')}</div>
                  <div class="todo__main"><b>${U.esc(w.name)}</b>
                    <span>掌握率 ${w.masteryRate}% · 建议 ${Math.ceil((60 - w.masteryRate) / 5)} 组靶向练习</span></div>
                  <button class="btn btn--sm btn--outline" data-weak-start data-weak-kp="${U.esc(w.kpId)}">出题</button>
                </div>`).join('')}
            </div>
          </div>`;

        U.$$('#modeGrid .card[data-mode]', box).forEach(c => c.addEventListener('click', () => {
          if (this.activeMode === c.dataset.mode) { this.collapsePanel(); return; }
          const kpIds = c.dataset.mode === 'weak' ? this._weakKpIds : undefined;
          this.expandPanel(c.dataset.mode, ms, c, kpIds);
        }));
        U.$$('[data-weak-start]', box).forEach(b => b.addEventListener('click', e => {
          e.stopPropagation();
          const kp = b.dataset.weakKp;
          this.expandPanel('weak', ms, box.querySelector('#modeGrid .card[data-mode="weak"]'), kp ? [kp] : undefined);
        }));
        });
      });
    },

    /* --- 内联展开 / 收起 --- */
    expandPanel(mode, ms, cardEl, kpIds) {
      this.activeMode = mode;
      U.$$('#modeGrid .card[data-mode]').forEach(c => c.classList.toggle('is-active', c === cardEl));
      const panel = U.$('#modePanel');
      if (panel) panel.hidden = false;
      this.start(mode, ms, kpIds);
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

    /* --- 开始练习 --- */
    start(mode, ms, kpIds) {
      const m = (ms || []).find(x => x.key === mode);
      // 记录进入练习时的 tab，退出时按此恢复到对应列表
      this._startTab = this.tab;
      this._lastKpIds = (kpIds && kpIds.length) ? kpIds : undefined;
      const body = { mode, count: m ? m.count : 10 };
      if (this._lastKpIds) body.kpIds = this._lastKpIds;
      API.practice.create(body).then(s => {
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
          <span class="fz-12 t-dim">知识点定位：${q.kpPath.join(' › ')}</span>
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
              <div class="kp-tree">
                <div class="kp-tree__row">${icon('folder')}<b>${r.kpPath[0]}</b></div>
                <div class="kp-tree__row kp-tree__row--sub">${icon('chevronRight')}<span>${r.kpPath[1]}</span></div>
                <div class="kp-tree__row kp-tree__row--leaf">${icon('target')}<b class="t-brand">${r.kpPath[2]}</b>
                  ${q.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}</div>
              </div>
              <div class="row row--wrap fz-12 t-dim" style="margin-top:9px">
                <span>前置知识点：</span>${(q.preKp || []).map(k => `<span class="badge badge--outline">${U.esc(k)}</span>`).join('')}
              </div>
            </div>
            <div class="feedback__sec">
              <h5>学情回写</h5>
              <div class="row row--wrap">
                <span class="badge ${r.masteryDelta >= 0 ? 'badge--ok' : 'badge--danger'}">
                  掌握率 ${r.masteryDelta >= 0 ? '+' : ''}${r.masteryDelta}pp</span>
                ${r.errorType ? `<span class="badge badge--warn">错误类型：${r.errorType}</span>
                  <span class="badge badge--outline">已自动归入错题本</span>` : '<span class="badge badge--outline">完成率已更新</span>'}
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
        Toast.error('提交失败', err && err.message || '请重试');
      });
    },

    /* --- 练习报告 --- */
    renderReport(r) {
      this.state = 'report';
      if (!r) { Toast.error('报告加载失败', '后端返回空数据'); return; }
      const panel = U.$('#modePanel');
      const target = (panel && !panel.hidden) ? panel : U.$('#pBody');
      const kpChanges = r.kpChanges || [];
      const errorTypes = r.errorTypes || [];
      target.innerHTML = `
      <div class="grid g-4" style="margin-bottom:16px">
        <div class="stat" style="--_c:var(--ok)"><div class="stat__label">正确率</div>
          <div class="stat__value">${r.accuracy ?? 0}<small>%</small></div>
          <div class="stat__hint">班级平均 ${r.classAccuracy ?? 0}% ${U.delta((r.accuracy ?? 0) - (r.classAccuracy ?? 0))}</div></div>
        <div class="stat" style="--_c:var(--brand-500)"><div class="stat__label">答对 / 总题数</div>
          <div class="stat__value">${r.correct ?? 0}<small>/${r.total ?? 0}</small></div>
          <div class="stat__hint">错题 ${r.wrong ?? 0} 道已归入错题本</div></div>
        <div class="stat" style="--_c:var(--info)"><div class="stat__label">总用时</div>
          <div class="stat__value">${Math.floor((r.durationSeconds || 0) / 60)}<small>分${(r.durationSeconds || 0) % 60}秒</small></div>
          <div class="stat__hint">均每题 ${r.avgSeconds ?? 0} 秒</div></div>
        <div class="stat" style="--_c:var(--accent-500)"><div class="stat__label">能力目标增益</div>
          <div class="stat__value">+${r.scoreGain ?? 0}</div>
          <div class="stat__hint">已回写目标图谱达成度</div></div>
      </div>

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
          <div class="card__head"><h3>${icon('alert')} 错误类型分布</h3></div>
          <div class="card__body">
            ${errorTypes.length ? `<div class="chart chart--sm" id="errTypeChart"></div>` : `<p class="fz-12 t-dim">没有错题，继续保持！</p>`}
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
      if (errorTypes.length) {
        Charts.bar('#errTypeChart', errorTypes.map(e => ({ name: e.type, value: e.count })),
          { horizontal: true, showLabel: true, labelFmt: '{c} 题' });
      }

      U.$('#againBtn').addEventListener('click', () => API.practice.modes().then(ms => this.start(this.mode || 'weak', ms, this._lastKpIds)));
      U.$('#toWrong').addEventListener('click', () => {
        U.$$('#pTabs button').forEach(x => x.classList.toggle('is-active', x.dataset.t === 'wrong'));
        this.renderWrong();
      });
      U.$('#toMastery').addEventListener('click', () => Router.go('mastery'));
      U.$('#backSelect').addEventListener('click', () => this.renderSelect());
    },

    /* --- 错题本 --- */
    renderWrong(filter) {
      const f = filter || 'false';
      this.lastWrongFilter = f;
      this.tab = 'wrong';
      API.practice.wrongBook({ mastered: f }).then(r => {
        U.$('#pBody').innerHTML = `
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
                  <span class="badge badge--warn">${U.esc(w.errorType)}</span>
                  <span class="spacer"></span>
                  <span class="fz-11 t-dim">${w.lastTime}</span>
                </div>
                <div class="wrong-item__stem">${U.esc(w.stem)}</div>
                <div class="wrong-item__tags">
                  <span class="badge badge--brand">${U.esc(w.kp)}</span>
                  <span class="badge badge--outline">难度 ${U.stars(w.difficulty)}</span>
                  <span class="fz-12 t-dim">我的答案 <b class="t-danger">${w.myAnswer}</b> · 正确答案 <b class="t-ok">${w.answer}</b></span>
                  <span class="spacer"></span>
                  ${w.mastered ? '<span class="badge badge--ok">已掌握</span>'
              : `<button class="btn btn--xs btn--outline" data-redo="${w.qId}">重做</button>
                     <button class="btn btn--xs btn--ghost" data-mastered="${w.qId}">标记已掌握</button>`}
                </div>
              </div>`).join('') : R.empty('太棒了，没有待攻克的错题', '继续保持，可以去做新的练习', 'award')}
          </div>
        </div>`;

        U.$$('#wFilter button').forEach(b => b.addEventListener('click', () => this.renderWrong(b.dataset.f)));
        U.$('#wPractice').addEventListener('click', () => API.practice.modes().then(ms => this.start('wrong', ms)));
        U.$$('[data-redo]').forEach(b => b.addEventListener('click', () => API.practice.modes().then(ms => this.start('wrong', ms))));
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
                <span class="badge badge--warn">${U.esc(d.errorType)}</span>
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
                API.practice.modes().then(ms => Practice.start('wrong', ms));
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

Router.register('practice', { title: '智能练习', mount: () => Practice.render() });
