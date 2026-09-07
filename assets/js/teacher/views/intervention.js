'use strict';

  /* ================================================================
     视图 5 · 教学干预与策略
     ================================================================ */
  const Intervention = {
    tab: 'list',
    filters: { status: 'all', scope: 'all', priority: 'all' },
    _currentData: { items: [], resources: [], heat: null, analysis: null },

    _dateTimeValue(date) {
      const p = n => String(n).padStart(2, '0');
      return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
    },

    _dateTimeText(value) {
      return String(value || '').replace('T', ' ');
    },

    _scheduleDefaults() {
      const resourceAt = new Date();
      resourceAt.setMinutes(0, 0, 0);
      resourceAt.setHours(resourceAt.getHours() + 1);
      const practiceAt = new Date(resourceAt);
      practiceAt.setDate(practiceAt.getDate() + 2);
      practiceAt.setHours(23, 59, 0, 0);
      const retestAt = new Date(resourceAt);
      retestAt.setDate(retestAt.getDate() + 5);
      retestAt.setHours(14, 0, 0, 0);
      return {
        resourceAt: this._dateTimeValue(resourceAt),
        practiceAt: this._dateTimeValue(practiceAt),
        retestAt: this._dateTimeValue(retestAt),
      };
    },

    _matchesResources(iv, resources) {
      const source = [iv.title, iv.target, iv.reason].concat(iv.steps || []).join(' ');
      const quoted = source.match(/「([^」]+)」/);
      const kpName = quoted ? quoted[1] : '';
      return (resources || []).filter(r => {
        const text = `${r.kp || ''} ${r.title || ''}`;
        return (kpName && text.includes(kpName)) || (!!r.kp && source.includes(r.kp));
      }).slice(0, 4);
    },

    _timedSteps(steps) {
      return (steps || []).filter(s => /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(String(s)));
    },

    _focusItems(heat, analysis, items, resources) {
      const weakest = heat && Array.isArray(heat.weakest) ? heat.weakest.slice(0, 3) : [];
      const wrongs = analysis && Array.isArray(analysis.topWrongQuestions) ? analysis.topWrongQuestions : [];
      if (weakest.length) {
        return weakest.map(w => {
          const linked = items.find(iv => [iv.title, iv.target, iv.reason].join(' ').includes(w.name));
          const virtual = linked || {
            ivId: '', title: `班级薄弱点「${w.name}」`, target: `${w.startedCount || 0} 名学生有学习记录`,
            reason: `当前平均掌握率 ${w.avg || 0}%`, steps: [], level: (w.avg || 0) < 40 ? 'danger' : 'warn',
          };
          const wrong = wrongs.find(q => q.kpId === w.kpId || q.kp === w.name);
          return {
            ...virtual,
            kpName: w.name,
            mastery: w.avg || 0,
            startedCount: w.startedCount || 0,
            wrong,
            resources: this._matchesResources(virtual, resources),
          };
        });
      }
      return (items || []).slice(0, 3).map(iv => ({
        ...iv,
        kpName: '待进一步定位',
        mastery: null,
        startedCount: null,
        resources: this._matchesResources(iv, resources),
      }));
    },

    render() {
      const el = U.$('#view-intervention');
      el.innerHTML = `
      <div style="height:calc(100vh - var(--topbar-h) - 44px);display:flex;flex-direction:column;min-height:0;overflow:hidden">
        <div class="tabs tabs--fill" id="ivTabs" style="margin-bottom:16px;flex:0 0 auto">
          <button class="is-active" data-t="list">${icon('route')} 干预建议</button>
          <button data-t="templates">${icon('book')} 策略库</button>
        </div>
        <div id="ivBody" style="flex:1;min-height:0;overflow:hidden"></div>
      </div>`;
      U.$$('#ivTabs button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#ivTabs button', el).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.tab = b.dataset.t;
        this.tab === 'list' ? this.renderList() : this.renderTemplates();
      }));
      this.renderList();
    },

    renderList() {
      const box = U.$('#ivBody');
      box.style.cssText = 'flex:1;min-height:0;overflow:hidden';
      box.innerHTML = U.skeleton(420);
      Promise.all([
        API.intervention.list({ classId: state.classId }).catch(() => ({ list: [] })),
        API.teacher.heatmap({ classId: state.classId, type: 'mastery' }).catch(() => null),
        API.analysis.errors({ classId: state.classId }).catch(() => null),
        API.teacher.resources({}).catch(() => ({ list: [] })),
      ]).then(([interventionData, heat, analysis, resourceData]) => {
        const allItems = Array.isArray(interventionData.list) ? interventionData.list : [];
        const resources = Array.isArray(resourceData.list) ? resourceData.list : [];
        this._currentData = { items: allItems, resources, heat, analysis };
        const items = allItems.filter(iv => {
          const statusOk = this.filters.status === 'all' || iv.status === this.filters.status;
          const scopeOk = this.filters.scope === 'all' || iv.scope === this.filters.scope;
          const priorityOk = this.filters.priority === 'all' || iv.level === this.filters.priority;
          return statusOk && scopeOk && priorityOk;
        });
        const stMap = {
          pending: ['待确认', 'badge--danger'], running: ['执行中', 'badge--warn'],
          done: ['已完成', 'badge--ok'], rejected: ['已忽略', 'badge--outline'],
        };
        const counts = {
          pending: allItems.filter(iv => iv.status === 'pending').length,
          high: allItems.filter(iv => iv.level === 'danger').length,
          running: allItems.filter(iv => iv.status === 'running').length,
          done: allItems.filter(iv => iv.status === 'done').length,
        };
        const focusItems = this._focusItems(heat, analysis, allItems, resources);
        this._focusItemsCache = focusItems;
        const nowText = new Date().toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-');
        box.innerHTML = `
        <div class="stack" style="height:100%;min-height:0;gap:14px;overflow:hidden">
        <div class="callout callout--brand" style="flex:0 0 auto">${icon('info')}
          <div><b>时间化干预工作台</b>：由预警、知识点掌握、错题归因和资源库共同生成建议。<br>
            <span class="fz-11 t-dim">使用方式：在下方“待确认”卡片点击“生成干预计划” → 设置时间与资源 → “生成并启动计划”。</span><br>
            <span class="fz-11 t-dim">数据更新时间：${U.esc(nowText)}；计划启动后会变为“执行中”。</span></div></div>

        <div class="grid g-4" style="margin:0;flex:0 0 auto">
          <div class="stat stat--sm" style="--_c:var(--danger)"><div class="stat__label">待确认干预</div><div class="stat__value">${counts.pending}</div><div class="stat__hint">需要安排明确执行时间</div></div>
          <div class="stat stat--sm" style="--_c:var(--warn)"><div class="stat__label">高优先级</div><div class="stat__value">${counts.high}</div><div class="stat__hint">红色预警或掌握率偏低</div></div>
          <div class="stat stat--sm" style="--_c:var(--brand-500)"><div class="stat__label">执行中</div><div class="stat__value">${counts.running}</div><div class="stat__hint">可随时查看复测效果</div></div>
          <div class="stat stat--sm" style="--_c:var(--ok)"><div class="stat__label">已完成</div><div class="stat__value">${counts.done}</div><div class="stat__hint">可沉淀为策略模板</div></div>
        </div>

        <div class="card" style="flex:0 0 286px;min-height:0;display:flex;flex-direction:column;overflow:hidden">
          <div class="card__head"><h3>${icon('target')} 当前干预重点</h3><span class="spacer"></span><span class="fz-11 t-dim">依据知识点掌握率、错题与预警实时排序</span></div>
          <div class="card__body" style="flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable">
            <div class="grid g-3">
              ${focusItems.map((f, index) => `
                <div class="card card--flat" style="padding:14px">
                  <div class="row" style="margin-bottom:7px"><b class="clamp-1">${U.esc(f.kpName)}</b><span class="spacer"></span>
                    <span class="badge ${f.level === 'danger' ? 'badge--danger' : 'badge--warn'}">${f.level === 'danger' ? '高优先' : '需关注'}</span></div>
                  <div class="row fz-12 t-dim" style="margin-bottom:8px"><span>平均掌握率</span><span class="spacer"></span><b class="mono ${f.mastery != null && f.mastery < 60 ? 't-danger' : ''}">${f.mastery != null ? f.mastery + '%' : '—'}</b></div>
                  <p class="fz-11 t-dim clamp-2" style="min-height:34px">${f.wrong ? `高频错题：${U.esc(f.wrong.stem)}` : U.esc(f.reason || '等待教师进一步确认干预原因')}</p>
                  <div class="chips" style="margin-top:9px">${f.resources.length ? f.resources.slice(0, 2).map(r => `<span class="badge badge--outline">${U.esc(r.type === 'video' ? '视频' : r.type === 'ppt' ? 'PPT' : r.type === 'quiz' ? '练习' : '文档')} · ${U.esc(r.title)}</span>`).join('') : '<span class="fz-11 t-dim">暂无直接匹配资源</span>'}</div>
                  <button class="btn btn--sm btn--outline" style="margin-top:10px" data-focus="${index}">${icon('eye')} 查看证据与资源</button>
                </div>`).join('') || '<div class="fz-12 t-dim">暂无可识别的干预重点</div>'}
            </div>
          </div>
        </div>

        <div class="grid g-21" style="flex:1;min-height:0;align-items:stretch">
          <div class="card" style="min-height:0;display:flex;flex-direction:column;overflow:hidden">
            <div class="card__head"><h3>${icon('route')} 干预执行队列</h3><span class="spacer"></span>
              <select class="select select--sm" id="ivStatus" style="width:96px"><option value="all">全部状态</option><option value="pending">待确认</option><option value="running">执行中</option><option value="done">已完成</option></select>
              <select class="select select--sm" id="ivScope" style="width:96px"><option value="all">全部对象</option><option value="common">班级共性</option><option value="individual">个体学生</option></select>
              <select class="select select--sm" id="ivPriority" style="width:124px"><option value="all">全部优先级</option><option value="danger">高优先</option><option value="warn">需关注</option></select>
              <button class="btn btn--sm btn--ghost" id="ivRefresh" title="刷新数据">${icon('refresh')}</button></div>
            <div class="card__body card__body--flush" style="flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable"><div class="stack" style="gap:12px;padding:14px">
              ${items.map(iv => {
                const [lbl, bd] = stMap[iv.status] || ['—', 'badge--outline'];
                const matched = this._matchesResources(iv, resources);
                const timedSteps = this._timedSteps(iv.steps);
                const execution = iv.execution || {};
                const hasEffect = Number(execution.retestDone || 0) > 0 || Number(execution.masteryAfter || 0) > 0;
                return `<div class="iv-card">
                  <div class="iv-card__head">
                    <div class="todo__ico todo__ico--${iv.level === 'danger' ? 'danger' : iv.level === 'warn' ? 'warn' : 'ok'}">${icon('route')}</div>
                    <div style="flex:1;min-width:0">
                      <div class="row row--wrap" style="margin-bottom:4px"><b style="font-size:14px;min-width:120px;flex:1">${U.esc(iv.title)}</b><span class="spacer"></span><span class="badge ${bd}">${lbl}</span><span class="badge badge--outline">${iv.scope === 'common' ? '共性' : '个体'}</span>${iv.status === 'pending' ? `<button class="btn btn--sm btn--primary" data-plan="${U.esc(iv.ivId)}">${icon('calendar')} 生成干预计划</button>` : ''}</div>
                      <div class="fz-12 t-dim">${U.esc(iv.target)}</div>
                    </div>
                  </div>
                  <div class="iv-card__body">
                    <p class="fz-12 t-2" style="margin-bottom:8px"><b>归因：</b>${U.esc(iv.reason)}</p>
                    ${timedSteps.length ? `<div class="callout callout--ok" style="margin-bottom:9px;padding:9px 11px">${icon('calendar')}<div><b>已安排时间</b><br>${timedSteps.map(s => U.esc(s)).join('<br>')}</div></div>` : `<div class="callout callout--brand" style="margin-bottom:9px;padding:9px 11px">${icon('calendar')}<div><b>尚未生成计划</b>：请点击卡片标题行的蓝色“生成干预计划”按钮。</div></div>`}
                    ${matched.length ? `<div class="row row--wrap" style="margin-bottom:9px"><span class="fz-11 t-dim">匹配资源</span>${matched.map(r => `<span class="badge badge--outline">${U.esc(r.type === 'video' ? '视频' : r.type === 'ppt' ? 'PPT' : r.type === 'quiz' ? '练习' : '文档')} · ${U.esc(r.title)}</span>`).join('')}</div>` : ''}
                    <div class="iv-steps">${(iv.steps || []).filter(s => !/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(String(s))).map(s => `<div class="iv-step"><span class="iv-step__n">•</span><span>${U.esc(s)}</span></div>`).join('')}</div>
                    ${hasEffect ? `<div class="divider"></div><div class="grid g-4" style="gap:10px"><div><b class="mono" style="color:var(--ok)">${execution.masteryAfter || 0}%</b><span class="fz-11 t-dim">复测完成率</span></div><div><b class="mono">${execution.completeRate || 0}%</b><span class="fz-11 t-dim">计划完成率</span></div><div><b class="mono">${execution.retestDone || 0}</b><span class="fz-11 t-dim">已复测</span></div><div><b class="mono t-brand">+${((execution.masteryAfter || 0) - (execution.masteryBefore || 0)).toFixed(1)}pp</b><span class="fz-11 t-dim">提升</span></div></div>` : `<div class="callout callout--brand" style="margin-top:10px;padding:9px 11px">${icon('bulb')}<div><b>预期效果：</b>${U.esc(iv.expectEffect || '完成资源学习和专项练习后，按计划组织复测。')}</div></div>`}
                  </div>
                  <div class="iv-card__foot"><button class="btn btn--sm" data-eff="${U.esc(iv.ivId)}">${icon('trend')} 干预效果</button><span class="spacer"></span>${iv.status === 'pending' ? `<button class="btn btn--sm btn--ghost" data-rej="${U.esc(iv.ivId)}">忽略</button>` : '<span class="fz-11 t-dim">已处理</span>'}</div>
                </div>`;
              }).join('') || '<div class="empty" style="padding:42px 20px"><b>当前筛选条件下暂无干预</b><p>可调整状态、对象或优先级筛选条件。</p></div>'}
            </div></div>
          </div>
          <div class="stack" style="gap:10px;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-right:2px">
            <div class="card"><div class="card__head" style="padding:10px 14px"><h3>${icon('calendar')} 时间安排原则</h3></div><div class="card__body" style="padding:9px 14px"><div class="iv-steps" style="gap:5px"><div class="iv-step" style="align-items:center"><span class="iv-step__n">1</span><span><b>资源学习时间</b><span class="fz-11 t-dim"> · 明确开始学习的时间</span></span></div><div class="iv-step" style="align-items:center"><span class="iv-step__n">2</span><span><b>专项练习截止</b><span class="fz-11 t-dim"> · 设置明确完成时点</span></span></div><div class="iv-step" style="align-items:center"><span class="iv-step__n">3</span><span><b>复测时间</b><span class="fz-11 t-dim"> · 以复测结果判断效果</span></span></div></div></div></div>
            <div class="grid g-2" style="gap:10px">
              <div class="card"><div class="card__head" style="padding:10px 14px"><h3>${icon('folder')} 资源使用说明</h3><span class="spacer"></span><span class="fz-11 t-dim">${resources.length} 个</span></div><div class="card__body" style="padding:11px 14px"><p class="fz-12 t-2" style="line-height:1.55">系统按标题、目标和归因匹配现有资源，可在“编排执行”中选择纳入计划。</p></div></div>
              <div class="card"><div class="card__head" style="padding:10px 14px"><h3>${icon('trend')} 效果判定</h3></div><div class="card__body" style="padding:11px 14px"><p class="fz-12 t-2" style="line-height:1.55">比较干预前后答题、资源完成与复测数据；没有新答题数据时不作结论。</p></div></div>
            </div>
          </div>
        </div>
        </div>`;

        const bindFilter = (selector, key) => {
          const input = U.$(selector, box);
          if (!input) return;
          input.value = this.filters[key];
          input.addEventListener('change', () => { this.filters[key] = input.value; this.renderList(); });
        };
        bindFilter('#ivStatus', 'status');
        bindFilter('#ivScope', 'scope');
        bindFilter('#ivPriority', 'priority');
        U.$('#ivRefresh', box).addEventListener('click', () => this.renderList());
        U.$$('[data-focus]', box).forEach(b => b.addEventListener('click', () => this.openFocus(this._focusItemsCache[Number(b.dataset.focus)])));
        U.$$('[data-eff]', box).forEach(b => b.addEventListener('click', () => this.showEffect(b.dataset.eff)));
        U.$$('[data-plan]', box).forEach(b => b.addEventListener('click', () => {
          const iv = allItems.find(item => item.ivId === b.dataset.plan);
          if (iv) this.openSchedule(iv);
        }));
        U.$$('[data-rej]', box).forEach(b => b.addEventListener('click', () =>
          API.intervention.reject({ ivId: b.dataset.rej }).then(() => { Toast.info('已忽略该建议'); this.renderList(); })));
      }).catch(err => {
        box.style.cssText = 'flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable';
        box.innerHTML = `<div class="card"><div class="card__body" style="padding:24px;text-align:center;color:var(--danger)">${icon('alert')}<h3 style="margin:0">干预数据加载失败</h3><p class="fz-12 t-dim">${U.esc(err.message || err)}</p></div></div>`;
      });
    },

    openFocus(focus) {
      if (!focus) return;
      const resources = focus.resources || [];
      const footer = `<button class="btn" data-close>关闭</button>${focus.ivId ? `<button class="btn btn--primary" id="focusPlan">${icon('calendar')} 生成干预计划</button>` : ''}`;
      Modal.open({
        title: `干预证据 · ${U.esc(focus.kpName || focus.title)}`,
        body: `<div class="stack" style="gap:14px"><div class="callout callout--brand">${icon('target')}<div><b>${U.esc(focus.kpName || '当前重点')}</b><br>平均掌握率：${focus.mastery != null ? U.esc(focus.mastery) + '%' : '—'}${focus.startedCount != null ? ` · ${U.esc(focus.startedCount)} 名学生有学习记录` : ''}</div></div>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">识别依据</p><div class="file-item">${icon('alert')}<b>${U.esc(focus.reason || '来自知识点掌握率、错题和预警的综合识别')}</b></div>${focus.wrong ? `<div class="file-item" style="margin-top:7px">${icon('quiz')}<b>${U.esc(focus.wrong.stem)}</b><span class="badge badge--warn">错 ${U.esc(focus.wrong.wrongRate)}%</span></div>` : ''}</div>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">可用匹配资源</p>${resources.length ? `<div class="stack" style="gap:7px">${resources.map(r => `<div class="file-item">${icon(r.type === 'video' ? 'play' : r.type === 'ppt' ? 'ppt' : r.type === 'quiz' ? 'quiz' : 'file')}<b>${U.esc(r.title)}</b><span class="fz-11 t-dim">${U.esc(r.kp || '')}</span></div>`).join('')}</div>` : '<p class="fz-12 t-dim">暂未找到直接匹配资源，可在资源管理中补充。</p>'}</div></div>`,
        footer,
        onMount: (ov, close) => {
          const planButton = U.$('#focusPlan', ov);
          if (planButton) planButton.addEventListener('click', () => {
            const iv = this._currentData.items.find(item => item.ivId === focus.ivId);
            close();
            if (iv) this.openSchedule(iv);
          });
        }
      });
    },

    openSchedule(iv) {
      const defaults = this._scheduleDefaults();
      const resources = this._matchesResources(iv, this._currentData.resources);
      const oldSteps = (iv.steps || []).filter(s => !/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(String(s))).join('\n');
      Modal.open({
        title: `生成干预计划 · ${U.esc(iv.title)}`,
        size: 'wide',
        body: `<div class="stack" style="gap:14px"><div class="callout callout--brand">${icon('info')}<div><b>干预对象：</b>${U.esc(iv.target)}<br><span class="fz-12">${U.esc(iv.reason)}</span></div></div>
          <div class="grid g-3" style="gap:10px"><label class="stack" style="gap:4px"><span class="fz-12 t-dim">资源学习安排</span><input class="input" type="datetime-local" id="ivResourceAt" value="${defaults.resourceAt}"></label><label class="stack" style="gap:4px"><span class="fz-12 t-dim">专项练习截止</span><input class="input" type="datetime-local" id="ivPracticeAt" value="${defaults.practiceAt}"></label><label class="stack" style="gap:4px"><span class="fz-12 t-dim">计划复测时间</span><input class="input" type="datetime-local" id="ivRetestAt" value="${defaults.retestAt}"></label></div>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">纳入计划的匹配资源（可多选）</p>${resources.length ? `<div class="stack" style="gap:7px">${resources.map(r => `<label class="file-item" style="cursor:pointer"><input type="checkbox" name="ivResource" value="${U.esc(r.resId)}" data-title="${U.esc(r.title)}" checked><span class="badge badge--outline">${U.esc(r.type === 'video' ? '视频' : r.type === 'ppt' ? 'PPT' : r.type === 'quiz' ? '练习' : '文档')}</span><b>${U.esc(r.title)}</b><span class="fz-11 t-dim">${U.esc(r.kp || '')}</span></label>`).join('')}</div>` : '<p class="fz-12 t-dim">没有自动匹配的资源；仍可保存时间安排，并在资源管理中另行补充。</p>'}</div>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">补充执行动作（每行一项）</span><textarea class="textarea" id="ivExtraSteps" placeholder="例如：2026-09-10 16:00 · 课上集中讲解易错点">${U.esc(oldSteps)}</textarea></label>
          <p class="fz-11 t-dim"><b>计划如何运作：</b>确认后系统会保存时间安排并将该项标为“执行中”；教师需按计划手动安排资源学习、专项练习和复测。当前不会自动向学生下发资源、发送提醒或自动结束计划。</p></div>`,
        footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="ivPlanConfirm">${icon('check')} 生成并启动计划</button>`,
        onMount: (ov, close) => {
          U.$('#ivPlanConfirm', ov).addEventListener('click', () => {
            const resourceAt = U.$('#ivResourceAt', ov).value;
            const practiceAt = U.$('#ivPracticeAt', ov).value;
            const retestAt = U.$('#ivRetestAt', ov).value;
            if (!resourceAt || !practiceAt || !retestAt) return Toast.warn('请填写完整的时间安排');
            if (resourceAt > practiceAt || practiceAt > retestAt) return Toast.warn('请按资源学习、练习截止、复测的时间顺序安排');
            const selectedResources = U.$$('input[name="ivResource"]:checked', ov);
            const resourceNames = selectedResources.map(input => input.dataset.title).filter(Boolean);
            const extraSteps = U.$('#ivExtraSteps', ov).value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
            const steps = [
              `${this._dateTimeText(resourceAt)} · 安排学习资源${resourceNames.length ? '：' + resourceNames.join('、') : ''}`,
              `${this._dateTimeText(practiceAt)} · 完成专项练习`,
              `${this._dateTimeText(retestAt)} · 组织复测并记录结果`,
              ...extraSteps,
            ];
            const button = U.$('#ivPlanConfirm', ov);
            button.disabled = true;
            button.textContent = '保存中…';
            API.intervention.confirm({
              ivId: iv.ivId,
              steps,
              resources: selectedResources.map(input => input.value),
            }).then(() => {
              Toast.ok('干预计划已确认', '已记录资源、练习截止与复测时间');
              close();
              this.renderList();
            }).catch(err => {
              button.disabled = false;
              button.innerHTML = `${icon('check')} 生成并启动计划`;
              Toast.warn('保存失败：' + (err.message || err));
            });
          });
        }
      });
    },

    showEffect(ivId) {
      API.intervention.effect({ ivId }).then(d => {
        const hasData = d.hasData !== false;
        const body = hasData
          ? `<div class="chart chart--lg" id="effChart"></div>
            <div class="callout callout--ok" style="margin-top:10px">${icon('checkCircle')}<div>${U.esc(d.summary)}</div></div>`
          : `<div class="empty" style="padding:40px 20px;text-align:center">
              ${icon('inbox', 48)}
              <p class="fz-13 t-2" style="margin-top:14px">${U.esc(d.summary)}</p>
            </div>`;
        Modal.open({
          title: '干预前后学情对比', size: 'wide',
          body: body,
          onMount(ov) {
            if (!hasData) return;
            Charts.line('#effChart', {
              xAxis: d.xAxis,
              series: [
                { name: d.series[0].name, data: d.series[0].data, color: d.series[0].color },
                { name: d.series[1].name, data: d.series[1].data, color: d.series[1].color }
              ]
            }, { area: true, max: 100, fmt: '{value}%' });
          }
        });
      });
    },

    renderTemplates() {
      const box = U.$('#ivBody');
      box.style.cssText = 'flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable';
      API.intervention.templates({}).then(list => {
        box.innerHTML = `
        <div class="callout callout--brand" style="margin-bottom:14px">${icon('book')}
          <div>策略库沉淀经实践验证有效的干预手段，可一键复用于同类学情场景，形成可复用模板。</div></div>
        <div class="grid g-3">
          ${list.map(t => `
            <div class="tpl">
              <h4>${U.esc(t.name)}</h4>
              <p>${U.esc(t.desc)}</p>
              <div class="chips" style="margin-bottom:10px">${t.tags.map(x => `<span class="badge badge--outline">${x}</span>`).join('')}</div>
              <div class="tpl__stats">
                <div><b>${t.useCount}</b><span>使用次数</span></div>
                <div><b class="t-ok">${t.successRate}%</b><span>成功率</span></div>
                <div><b class="t-brand">+${t.avgLift}</b><span>平均提升(pp)</span></div>
              </div>
              <div class="row" style="margin-top:12px"><span class="fz-11 t-dim">适用场景：${U.esc(t.scene)}</span>
                <span class="spacer"></span><button class="btn btn--sm btn--outline" data-use="${t.tplId}">复用</button></div>
            </div>`).join('')}
        </div>`;
        U.$$('[data-use]', box).forEach(b => b.addEventListener('click', () =>
          API.intervention.saveTemplate({ name: list.find(t => t.tplId === b.dataset.use).name }).then(r =>
            Toast.ok('已复用策略模板', '可在干预建议中一键套用'))));
      });
    }
  };

Router.register('intervention', { title: '教学干预与策略', mount: () => Intervention.render() });
