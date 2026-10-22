'use strict';

  /* ================================================================
     视图 2 · 学情监测看板（热力图 / 个体详情 / 预警复核）
     ================================================================ */
  /** 时长统一按 分'秒'' 展示（如 3'22''；实现集中在 U.dur） */
  function formatAnswerDuration(value) {
    return U.dur(value);
  }

  const Monitor = {
    stuLevel: 'all', stuKeyword: '', level: 'all', heatType: 'completion',
    heatMode: 'heatmap', heatKeyword: '',
    _heatData: null, _heatIndex: 0, _heatTimer: null, _heatPaused: false,
    HEAT_BAR_ROTATE_MS: 5000,
    render() {
      this.stopHeatRotate();
      const el = U.$('#view-monitor');
      if (!API.config.activeCourseId) {
        el.innerHTML = `
        <div class="card"><div class="card__body">
          <div class="empty" style="padding:48px 20px;text-align:center">
            <b>尚未创建或选择课程</b>
            <p class="fz-12 t-dim" style="margin-top:8px">学情监测按当前课程成员实时计算。请先创建课程并让学生加入。</p>
          </div>
        </div></div>`;
        return;
      }
      el.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="card__head card__head--heat">
          <h3 id="heatTitle">${icon('grid')} 知识点 × 学生 学习完成热力图</h3>
          <span class="spacer"></span>
          <div class="search heat-stu-search" id="heatStuSearchWrap" hidden style="width:188px">${icon('search2')}<input class="input" id="heatStuSearch" placeholder="搜索学生姓名 / 学号"></div>
          <div class="seg" id="heatModeSeg">
            <button type="button" data-mode="heatmap" class="is-active">热力图</button>
            <button type="button" data-mode="bar">单人柱形图</button>
          </div>
          <select class="input select select--sm" id="heatType" style="width:164px">
            <option value="completion">学习完成热力图</option>
            <option value="mastery">知识点掌握热力图</option>
          </select>
          <div class="hm-legend" style="margin-left:4px"><span>低</span><div class="hm-legend__bar"></div><span>高</span></div>
        </div>
        <div class="card__body">
          <div class="heat-bar-meta" id="heatBarMeta" hidden>
            <b class="heat-bar-meta__name" id="heatBarName"></b>
            <span class="fz-12 t-dim" id="heatBarNo"></span>
            <span class="badge badge--outline" id="heatBarIdx"></span>
            <span class="spacer"></span>
            <span class="fz-12 t-dim" id="heatBarStatus"></span>
          </div>
          <div class="heat-bar-stage" id="heatBarStage">
            <button type="button" class="heat-bar-nav heat-bar-nav--prev" id="heatBarPrev" hidden title="上一个学生" aria-label="上一个学生">${icon('chevronLeft')}</button>
            <div class="chart" id="heatChart" style="height:520px"></div>
            <button type="button" class="heat-bar-nav heat-bar-nav--next" id="heatBarNext" hidden title="下一个学生" aria-label="下一个学生">${icon('chevronRight')}</button>
          </div>
          <div class="divider"></div>
          <p class="fz-12 t-dim" style="margin-bottom:8px" id="heatWeakLabel">共性薄弱识别（班级平均学习完成率最低的 3 个知识点）</p>
          <div class="chips" id="weakChips"></div>
        </div>
      </div>

      <div class="grid g-12 monitor-student-grid">
        <div class="card monitor-student-card">
          <div class="card__head"><h3>${icon('users')} 学生学情列表</h3><span class="spacer"></span>
            <div class="search" style="width:160px">${icon('search2')}<input class="input" id="stuSearch" placeholder="姓名 / 学号"></div>
            <div class="seg" id="stuSeg"><button data-l="all" class="is-active">全部</button><button data-l="red">红</button><button data-l="yellow">黄</button><button data-l="green">绿</button></div>
          </div>
          <div class="card__body card__body--flush"><div class="list" id="stuList">${U.skeleton(300)}</div></div>
        </div>

        <div class="card card--alerts">
          <div class="card__head"><h3>${icon('bell')} 异常预警列表</h3><span class="spacer"></span>
            <span class="badge badge--outline" id="alCount"></span>
            <div class="seg" id="alSeg"><button data-l="all" class="is-active">全部</button><button data-l="red">红</button><button data-l="yellow">黄</button></div>
          </div>
          <div class="card__body stack" id="alList" style="min-height:0;overflow-x:hidden;overflow-y:auto">${U.skeleton(300)}</div>
        </div>
      </div>`;

      /* 重绘时把筛选状态回写到 DOM：
         模板里的 is-active 与搜索框是写死的「全部 / 空」，而 stuLevel / level /
         stuKeyword 是跨重绘保留的。视图一旦因课程切换或首屏课程上下文就绪而二次渲染
         （见 teacher/app.js 的 Router.mount 只跑一次 + __courseReady 补渲染），
         就会出现「高亮回到全部、列表却仍是上次的筛选结果」的错位，
         表现就是切换分类后选项框自己跳回去。这里统一按状态回写。 */
      U.$$('#stuSeg button', el).forEach(b => b.classList.toggle('is-active', b.dataset.l === this.stuLevel));
      U.$$('#alSeg button', el).forEach(b => b.classList.toggle('is-active', b.dataset.l === this.level));
      U.$('#stuSearch').value = this.stuKeyword || '';

      U.$$('#stuSeg button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#stuSeg button', el).forEach(x => x.classList.remove('is-active')); b.classList.add('is-active');
        this.stuLevel = b.dataset.l; this.loadStudents();
      }));
      U.$('#stuSearch').addEventListener('input', e => { this.stuKeyword = e.target.value.trim(); this.loadStudents(); });
      U.$$('#alSeg button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#alSeg button', el).forEach(x => x.classList.remove('is-active')); b.classList.add('is-active');
        this.level = b.dataset.l; this.loadAlerts();
      }));

      const typeSel = U.$('#heatType');
      if (typeSel) typeSel.value = this.heatType;
      U.$('#heatType').addEventListener('change', e => {
        this.heatType = e.target.value;
        this.updateHeatLabels();
        this.loadHeat();
      });

      U.$$('#heatModeSeg button', el).forEach(b => {
        b.classList.toggle('is-active', b.dataset.mode === this.heatMode);
        b.addEventListener('click', () => {
          if (this.heatMode === b.dataset.mode) return;
          this.heatMode = b.dataset.mode;
          U.$$('#heatModeSeg button', el).forEach(x => x.classList.toggle('is-active', x.dataset.mode === this.heatMode));
          this._heatPaused = false;
          this.updateHeatLabels();
          this.syncHeatChrome();
          this.paintHeat();
        });
      });

      const heatSearch = U.$('#heatStuSearch');
      if (heatSearch) {
        heatSearch.value = this.heatKeyword || '';
        heatSearch.addEventListener('input', e => {
          this.heatKeyword = e.target.value.trim();
          this._heatIndex = 0;
          if (this.heatMode === 'bar') {
            this.paintStudentBar();
            this.startHeatRotate();
          }
        });
      }

      const heatStage = U.$('#heatBarStage');
      if (heatStage) {
        heatStage.addEventListener('mouseenter', () => {
          if (this.heatMode !== 'bar') return;
          this._heatPaused = true;
          this.syncHeatBarMeta();
        });
        heatStage.addEventListener('mouseleave', () => {
          if (this.heatMode !== 'bar') return;
          this._heatPaused = false;
          this.syncHeatBarMeta();
        });
      }
      const prevBtn = U.$('#heatBarPrev');
      const nextBtn = U.$('#heatBarNext');
      if (prevBtn) prevBtn.addEventListener('click', () => this.stepHeatStudent(-1));
      if (nextBtn) nextBtn.addEventListener('click', () => this.stepHeatStudent(1));

      // 初次渲染即同步标题/标签，避免静态 HTML 文案与当前 heatType 不一致
      this.updateHeatLabels();
      this.syncHeatChrome();

      this.loadHeat(); this.loadStudents(); this.loadAlerts();
    },

    updateHeatLabels() {
      const isMastery = this.heatType === 'mastery';
      const isBar = this.heatMode === 'bar';
      const title = U.$('#heatTitle');
      if (title) {
        title.innerHTML = isBar
          ? `${icon('chart')} 单人学习情况柱形图 · ${isMastery ? '知识掌握' : '学习完成'}`
          : `${icon('grid')} 知识点 × 学生 ${isMastery ? '知识掌握' : '学习完成'}热力图`;
      }
      const weak = U.$('#heatWeakLabel');
      if (weak) {
        weak.textContent = isMastery
          ? '共性薄弱识别（班级平均知识掌握率低于 80% 的知识点）'
          : '共性薄弱识别（班级平均学习完成率低于 80% 的知识点）';
      }
    },

    syncHeatChrome() {
      const isBar = this.heatMode === 'bar';
      const searchWrap = U.$('#heatStuSearchWrap');
      const meta = U.$('#heatBarMeta');
      if (searchWrap) searchWrap.hidden = !isBar;
      if (meta) meta.hidden = !isBar;
      this.syncHeatNav();
      if (!isBar) this.stopHeatRotate();
    },

    syncHeatNav() {
      const list = this._filteredHeatStudents();
      const show = this.heatMode === 'bar' && list.length > 1;
      const prev = U.$('#heatBarPrev');
      const next = U.$('#heatBarNext');
      if (prev) prev.hidden = !show;
      if (next) next.hidden = !show;
    },

    stepHeatStudent(delta) {
      if (this.heatMode !== 'bar') return;
      const list = this._filteredHeatStudents();
      if (list.length <= 1) return;
      this._heatIndex = (this._heatIndex + delta + list.length) % list.length;
      this.paintStudentBar();
      this.startHeatRotate();
    },

    stuLabel(s) {
      return typeof s === 'object' ? (s.name || '') : (s || '');
    },

    _filteredHeatStudents() {
      const axis = (this._heatData && this._heatData.studentAxis) || [];
      const kw = (this.heatKeyword || '').trim().toLowerCase();
      const rows = axis.map((s, i) => ({ s, i }));
      if (!kw) return rows;
      return rows.filter(({ s }) => {
        const name = this.stuLabel(s).toLowerCase();
        const no = String((s && s.no) || '').toLowerCase();
        const id = String((s && s.userId) || '').toLowerCase();
        return name.includes(kw) || no.includes(kw) || id.includes(kw);
      });
    },

    stopHeatRotate() {
      if (this._heatTimer) {
        clearInterval(this._heatTimer);
        this._heatTimer = null;
      }
    },

    startHeatRotate() {
      this.stopHeatRotate();
      if (this.heatMode !== 'bar') return;
      const list = this._filteredHeatStudents();
      if (list.length <= 1) return;
      this._heatTimer = setInterval(() => {
        if (this._heatPaused || this.heatMode !== 'bar') return;
        const next = this._filteredHeatStudents();
        if (next.length <= 1) return;
        this._heatIndex = (this._heatIndex + 1) % next.length;
        this.paintStudentBar();
      }, this.HEAT_BAR_ROTATE_MS);
    },

    syncHeatBarMeta() {
      const meta = U.$('#heatBarMeta');
      if (!meta) return;
      const isBar = this.heatMode === 'bar';
      meta.hidden = !isBar;
      if (!isBar) return;
      const list = this._filteredHeatStudents();
      const nameEl = U.$('#heatBarName');
      const noEl = U.$('#heatBarNo');
      const idxEl = U.$('#heatBarIdx');
      const stEl = U.$('#heatBarStatus');
      if (!list.length) {
        if (nameEl) nameEl.textContent = this.heatKeyword ? '没有匹配的学生' : '暂无学生数据';
        if (noEl) noEl.textContent = '';
        if (idxEl) idxEl.textContent = '';
        if (stEl) stEl.textContent = this.heatKeyword ? '请换个姓名或学号试试' : '';
        return;
      }
      if (this._heatIndex >= list.length) this._heatIndex = 0;
      const stu = list[this._heatIndex].s;
      if (nameEl) nameEl.textContent = this.stuLabel(stu) || '未命名';
      if (noEl) noEl.textContent = (stu && stu.no) ? `学号 ${stu.no}` : '';
      if (idxEl) idxEl.textContent = `${this._heatIndex + 1} / ${list.length}`;
      let status = '自动轮播 · 悬停可暂停';
      if (list.length <= 1) status = this.heatKeyword ? '已定位到该学生' : '仅 1 名学生';
      else if (this.heatKeyword) status = this._heatPaused ? '搜索匹配轮播已暂停' : '正在轮播搜索匹配 · 悬停可暂停';
      else if (this._heatPaused) status = '悬停暂停';
      if (stEl) stEl.textContent = status;
    },

    paintStudentBar() {
      const h = this._heatData;
      const chart = U.$('#heatChart');
      if (!h || !chart) return;
      const list = this._filteredHeatStudents();
      this.syncHeatBarMeta();
      this.syncHeatNav();
      if (!list.length) {
        this.stopHeatRotate();
        const inst = window.echarts && echarts.getInstanceByDom(chart);
        if (inst && !(inst.isDisposed && inst.isDisposed())) inst.dispose();
        chart.innerHTML = `<div class="empty" style="padding:48px 20px;text-align:center">没有匹配的学生</div>`;
        return;
      }
      if (this._heatIndex >= list.length) this._heatIndex = 0;
      const item = list[this._heatIndex];
      const stu = item.s;
      const row = item.i;
      const label = h.label || (this.heatType === 'mastery' ? '知识掌握率' : '学习完成率');
      Charts.studentKpBar('#heatChart', {
        student: stu,
        kpAxis: h.kpAxis || [],
        values: (h.data && h.data[row]) || [],
        started: (h.startedMask && h.startedMask[row]) || [],
        label
      }, () => {
        if (stu && stu.userId) this.openProfile(stu.userId);
      });
    },

    paintHeat() {
      const h = this._heatData;
      if (!h) return;
      if (this.heatMode === 'bar') {
        this.paintStudentBar();
        this.startHeatRotate();
        return;
      }
      this.stopHeatRotate();
      this.syncHeatChrome();
      Charts.heatmap('#heatChart', h, (val, data) => {
        if (val[2] == null) return; // 灰色格子不可点
        const stu = data.studentAxis[val[1]];
        if (stu && stu.userId) this.openProfile(stu.userId);
      });
    },

    loadHeat() {
      const keepId = (() => {
        const list = this._filteredHeatStudents();
        const cur = list[this._heatIndex];
        return cur && cur.s && cur.s.userId;
      })();
      API.teacher.heatmap({ type: this.heatType }).then(h => {
        this._heatData = h;
        if (keepId) {
          const next = this._filteredHeatStudents();
          const found = next.findIndex(x => x.s && x.s.userId === keepId);
          this._heatIndex = found >= 0 ? found : 0;
        } else {
          this._heatIndex = 0;
        }
        this.paintHeat();
        U.$('#weakChips').innerHTML = (h.weakest && h.weakest.length)
          ? h.weakest.map(w =>
              `<span class="chip">${icon('alert')} ${U.esc(w.name)} <b class="mono">${w.avg}%</b></span>`).join('')
          : `<span class="empty" style="padding:14px 0">暂无低于 80% 的知识点${this.heatType === 'mastery' ? '（题库未导入时无答题记录，暂不展示）' : ''}</span>`;
      });
    },

    loadStudents() {
      API.teacher.students({ alertLevel: this.stuLevel, keyword: this.stuKeyword }).then(r => {
        const box = U.$('#stuList'); if (!box) return;
        box.innerHTML = r.list.map(s => `
          <div class="list__item list__item--clickable" data-uid="${s.userId}">
            <div class="stu-row" style="flex:1;min-width:0">
              <span class="avatar" style="width:34px;height:34px;flex:0 0 34px;font-size:14px">${Auth.avatarHtml(s)}</span>
              <div class="stu-row__info"><b>${U.esc(s.name)}</b></div>
            </div>
            <div style="width:140px">
              <div class="row fz-11 t-dim" style="margin-bottom:2px"><span>完成率</span><span class="spacer"></span><span class="mono">${Math.round(s.completion || 0)}%</span></div>
              ${U.bar(s.completion != null ? s.completion : s.mastery, null, 'sm')}
            </div>
            <span class="badge ${U.alertBadge[s.alertLevel]}">${s.alertCount} 预警</span>
            <i class="dot dot--${s.alertLevel}"></i>
          </div>`).join('') || R.empty('没有匹配的学生', '', 'users');
        U.$$('#stuList [data-uid]').forEach(row => row.addEventListener('click', () => this.openProfile(row.dataset.uid)));
      });
    },

    openProfile(userId) {
      const courseId = API.config.activeCourseId;
      API.teacher.studentProfile({ userId }).then(p => {
        if (API.config.activeCourseId !== courseId) return;
        Modal.drawer({
          title: '个体学情详情 · ' + p.name,
          body: `
          <div class="node-detail__hero">
            <div class="row" style="gap:9px;margin-bottom:8px">
              <span class="badge badge--brand">${p.className}</span>
             
              <span class="badge badge--outline">课程第 ${p.metrics.rank}/${p.metrics.totalStudents} 名</span>
            </div>
            <div class="grid g-4" style="gap:10px;margin:4px 0 0">
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:21px;display:block">${p.metrics.completion}%</b><span class="fz-11 t-dim">完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:21px;display:block;color:var(--brand-400)">${p.metrics.mastery}%</b><span class="fz-11 t-dim">学习完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:21px;display:block;color:var(--accent-500)">${p.metrics.goal}%</b><span class="fz-11 t-dim">目标达成</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:21px;display:block;color:var(--ok)">${p.metrics.accuracy}%</b><span class="fz-11 t-dim">练习正确率</span></div>
            </div>
          </div>
          <div style="padding:18px">
            <p class="fz-12 t-dim" style="margin-bottom:8px">学习时长趋势</p>
            <div class="chart chart--sm" id="stuStudyTrendChart"></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">AI 提问次数趋势</p>
            <div class="chart chart--sm" id="stuAiTrendChart"></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">知识点答题明细</p>
            <div class="tbl-wrap"><table class="tbl tbl--compact" id="stuKpTbl"></table></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">高频错题 Top 5</p>
            <div class="stack" style="gap:8px" data-profile-wrong>${U.skeleton(80)}</div>
          </div>`,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="prMsg">${icon('message')} 发送私信</button>
            <button class="btn btn--primary" id="prReport">${icon('file')} 学情报告</button>`,
          onMount(ov, close) {
            const wrongBox = ov.querySelector('[data-profile-wrong]');
            const loadWrongPoints = async () => {
              wrongBox.innerHTML = U.skeleton(80);
              try {
                const data = await API.teacher.studentWrongQuestions({ userId, size: 1 });
                if (!ov.isConnected || API.config.activeCourseId !== courseId) return;
                // 接口已按累计答错次数降序排列，看板仅展示前五项。
                wrongBox.innerHTML = (data.knowledgePoints || []).slice(0, 5).map(k => `
                  <button type="button" class="file-item profile-wrong-link" data-profile-wrong-kp="${U.esc(k.kpId)}">
                    ${icon('alert')}<b>${U.esc(k.name)}</b>
                    <span class="fz-11 t-dim">${k.questionCount} 道题 · 错 ${k.wrongCount} 次</span>
                    <span class="fz-12 t-brand nowrap">查看错题</span>${icon('chevronRight')}
                  </button>`).join('') || '<span class="fz-12 t-dim">暂无高频错题</span>';
              } catch (err) {
                if (!ov.isConnected || API.config.activeCourseId !== courseId) return;
                wrongBox.innerHTML = `<div class="callout callout--danger">高频错题加载失败：${U.esc(err.message || err)}</div>
                  <button type="button" class="btn btn--sm" data-profile-wrong-retry>重试</button>`;
              }
            };
            wrongBox.addEventListener('click', e => {
              const button = e.target.closest('[data-profile-wrong-kp]');
              if (button) Dash.openWrongQuestions(userId, p.name, [button.dataset.profileWrongKp]);
              else if (e.target.closest('[data-profile-wrong-retry]')) loadWrongPoints();
            });
            loadWrongPoints();
            const studyMinutes = (p.activityTrend.minutes || []).map(v => Number(v) || 0);
            const minutePeak = Math.max(...studyMinutes, 0);
            let minuteInterval = 20;
            while (minutePeak > minuteInterval * 4) minuteInterval *= 2;
            const minuteMax = minuteInterval * 4;

            const aiQuestions = (p.activityTrend.questions || []).map(v => Number(v) || 0);
            const aiPeak = Math.max(...aiQuestions, 0);
            let aiInterval = 1;
            while (aiPeak > aiInterval * 4) aiInterval *= 2;
            const aiMax = aiInterval * 4;
            Charts.line('#stuStudyTrendChart', {
              xAxis: p.activityTrend.xAxis,
              series: [
                // 学习时长：接口单位为分钟，提示框按 分'秒'' 展示（与表格口径一致）
                { name: '学习时长', data: studyMinutes, color: Charts.tokens().brand,
                  valueFormatter: (v) => U.durMin(v) }
              ]
            }, {
              yAxes: [
                { name: '分钟', min: 0, max: minuteMax, interval: minuteInterval, color: Charts.tokens().brand }
              ]
            });
            Charts.line('#stuAiTrendChart', {
              xAxis: p.activityTrend.xAxis,
              series: [
                { name: 'AI 提问次数', data: aiQuestions, color: Charts.tokens().warn }
              ]
            }, {
              yAxes: [
                { name: '次', min: 0, max: aiMax, interval: aiInterval, color: Charts.tokens().warn }
              ]
            });
            U.$('#stuKpTbl').innerHTML = `
              <thead><tr><th>知识点</th><th class="t-right">学习完成率</th><th class="t-right">练习</th><th class="t-right">错题</th><th class="t-right">时长</th></tr></thead>
              <tbody>${p.kpDetail.map(k => `
                <tr><td>${U.esc(k.name)}</td>
                  <td class="t-right num" style="color:${U.levelColor[k.level]}">${k.mastery}%</td>
                  <td class="t-right num t-dim">${k.questions}</td>
                  <td class="t-right num t-danger">${k.wrong}</td>
                  <td class="t-right num t-dim">${formatAnswerDuration(k.durationSeconds != null ? k.durationSeconds : (Number(k.minutes) || 0) * 60)}</td></tr>`).join('')}</tbody>`;
            U.$('#prMsg', ov).addEventListener('click', () => {
              Modal.open({
                title: '向学生发送私信',
                closeOnBackdrop: false,
                body: `<div class="kv" style="margin-bottom:12px">
                    <div class="kv__row"><span>收件人</span><span>${U.esc(p.name)}（${p.no}）</span></div></div>
                  <textarea class="code-edit" id="msgBody" placeholder="输入改进建议 / 提醒内容…"></textarea>`,
                footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="msgSend">发送</button>`,
                onMount(o2, c2) {
                  U.$('#msgSend', o2).addEventListener('click', () => {
                    const txt = U.$('#msgBody', o2).value.trim();
                    if (!txt) return Toast.warn('请输入内容');
                    API.teacher.sendMessage({ userId: p.userId, content: txt }).then(() => {
                      Toast.ok('私信已发送', p.name + ' 将收到你的改进建议'); c2(); close();
                    });
                  });
                }
              });
            });
            U.$('#prReport', ov).addEventListener('click', () => { close(); Router.go('report'); });
          }
        });
      });
    },

    /**
     * 异常预警卡内滚动：可见高度固定为 4 张卡片，其余靠容器自身滚动条查看。
     * 高度不写死像素 —— 按首张卡片的真实高度 + 列表 gap + 容器上下内边距算出来，
     * 这样卡片内容（标题行数、描述换行）变化时仍然正好是 4 条。
     * 不足 4 条时把高度交还给内容，避免卡片底部留一大片空白。
     */
    _clampAlertList(box) {
      if (!box) return;
      const cards = U.$$('.alert-card', box);
      if (cards.length <= 4) {
        box.style.height = 'auto';
        box.style.maxHeight = '';
        box.classList.remove('alert-list--scroll');
        return;
      }
      const cs = getComputedStyle(box);
      const cardH = cards[0].getBoundingClientRect().height;
      const gap = parseFloat(cs.rowGap) || 16;
      const pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
      box.style.height = 'auto';
      box.style.maxHeight = Math.ceil(cardH * 4 + gap * 3 + pad + 2) + 'px';
      box.classList.add('alert-list--scroll');
    },

    loadAlerts() {
      const self = this;
      API.teacher.alerts({ level: this.level }).then(r => {
        const box = U.$('#alList'); if (!box) return;
        box.innerHTML = r.list.map(a => `
          <div class="alert-card ${a.status === 'ignored' ? 'alert-card--ignored' : U.alertCard[a.level]}">
            <div class="alert-card__head">
              <div class="alert-card__ico">${icon(a.level === 'red' ? 'alert' : 'info')}</div>
              <div class="alert-card__body">
                <div class="row" style="margin-bottom:3px">
                  <span class="badge ${a.status === 'ignored' ? 'badge--ignored' : U.alertBadge[a.level]}">${a.status === 'ignored' ? '已忽视' : U.alertName[a.level]}</span>
                  <span class="spacer"></span><span class="fz-11 t-dim">${a.createdAt}</span>
                </div>
                <h4>${U.esc(a.student)} · ${U.esc(a.typeLabel || a.type)}</h4>
                <p>${U.esc(a.desc)} · 知识点：${U.esc(a.kp)}</p>
              </div>
            </div>
            <div class="alert-card__foot">
              <span class="badge ${a.status === 'ignored' ? 'badge--ignored' : a.status === 'reviewed' ? U.alertBadge[a.level] : a.status === 'open' ? 'badge--danger' : 'badge--outline'}">
                ${a.status === 'open' ? '待处理' : a.status === 'reviewed' ? '已复核' : a.status === 'ignored' ? '已忽视' : '已解除'}</span>
              <span class="spacer"></span>
              <button class="btn btn--sm" data-detail="${a.alertId}">查看</button>
              ${a.status === 'open' || a.status === 'reviewed' || a.status === 'ignored' ? `<button class="btn btn--sm btn--primary" data-review="${a.alertId}">${a.status === 'open' ? '复核' : '重新复核'}</button>` : ''}
            </div>
          </div>`).join('') || R.empty('暂无该级别预警', '', 'checkCircle');

        // 列表只展示 4 条，其余在卡内滚动（2026-09-24 需求）。
        const cnt = U.$('#alCount');
        if (cnt) cnt.textContent = (r.total || r.list.length) ? `共 ${r.total || r.list.length} 条` : '';
        this._clampAlertList(box);

        U.$$('#alList [data-detail]').forEach(b => b.addEventListener('click', () => {
          const a = r.list.find(x => x.alertId === b.dataset.detail);
          // 历史正确率（按天累计）：后端给的 trendData 是近 14 天「截至当天」的累计正确率，
          // 当天没做题则沿用前一天的值；第一次作答之前的日期为 null（图上留空）。
          const series = a.trendData || [];
          const known = series.filter(v => v !== null && v !== undefined);
          const lastAcc = known.length ? known[known.length - 1] : null;
          // 最后两个有值的点：用于显示"较上一天 ±x.xpp"
          const lastIdx = series.reduce((acc, v, i) => (v !== null && v !== undefined ? i : acc), -1);
          const prevAcc = known.length > 1 ? known[known.length - 2] : null;
          const diffAcc = (lastAcc !== null && prevAcc !== null) ? Math.round((lastAcc - prevAcc) * 10) / 10 : null;
          const diffText = diffAcc === null ? '' : (diffAcc > 0 ? `较上一天 +${diffAcc}pp` : diffAcc < 0 ? `较上一天 ${diffAcc}pp` : '与上一天持平');
          const labels = a.trendXAxis || [];
          const mainColor = a.level === 'red' ? Charts.tokens().danger : (a.level === 'yellow' ? Charts.tokens().warn : Charts.tokens().ok);
          Modal.open({
            title: '预警详情 · ' + a.student, size: 'wide',
            body: `<p class="fz-12 t-dim" style="margin-bottom:10px">触发规则：<b>${U.esc(a.trigger)}</b></p>
              <div class="row" style="gap:10px;align-items:baseline;flex-wrap:wrap;margin:0 0 4px">
                <span class="fz-13">「${U.esc(a.kp || a.kpId || '该知识点')}」历史正确率</span>
                <b class="mono" style="font-size:23px;color:${lastAcc === null ? 'var(--text-3)' : mainColor}">${lastAcc === null ? '—' : lastAcc + '%'}</b>
                <span class="fz-11 t-dim">今日为止（近 ${a.trendDays || 14} 天累计）</span>
                ${diffText ? `<span class="badge ${diffAcc > 0 ? 'badge--ok' : diffAcc < 0 ? 'badge--danger' : 'badge--outline'}">${diffText}</span>` : ''}
              </div>
              <div class="chart chart--sm" id="alTrend"></div>`,
            footer: `<button class="btn" data-close>关闭</button>`,
            onMount(ov) {
              Charts.line('#alTrend', {
                xAxis: labels,
                series: [
                  {
                    name: '累计正确率', data: series, color: mainColor,
                    // 把"今天/最新"的取值直接标在图上，避免右端数据点看不出数值
                    markPoint: (lastIdx < 0) ? undefined : {
                      symbol: 'circle', symbolSize: 9,
                      itemStyle: { color: mainColor, borderColor: '#fff', borderWidth: 2 },
                      data: [{
                        coord: [labels[lastIdx], series[lastIdx]],
                        value: series[lastIdx] + '%',
                        label: {
                          // 取值接近顶部时把标签放到点下方，避免压到图例
                          show: true, position: series[lastIdx] >= 80 ? 'bottom' : 'top', distance: 8,
                          formatter: p => (lastIdx === labels.length - 1 ? '今天 ' : '最新 ') + p.value,
                          color: mainColor, fontSize: 11.5, fontWeight: 600,
                          backgroundColor: 'rgba(255,255,255,.92)', padding: [2, 5], borderRadius: 4,
                          borderColor: mainColor, borderWidth: 1,
                        },
                      }],
                    },
                  },
                  { name: '达标线 60%', data: labels.map(() => 60), color: Charts.tokens().dim, dashed: true },
                ],
              }, { max: 100, fmt: '{value}%', right: 46, top: 44 });
            }
          });
        }));

        U.$$('#alList [data-review]').forEach(b => b.addEventListener('click', () => {
          const a = r.list.find(x => x.alertId === b.dataset.review);
          Modal.open({
            title: '复核预警 · ' + a.student,
            closeOnBackdrop: false,
            body: `<div class="kv" style="margin-bottom:12px">
                <div class="kv__row"><span>预警类型</span><span>${U.esc(a.type)}</span></div>
                <div class="kv__row"><span>关联知识点</span><span>${U.esc(a.kp)}</span></div>
                <div class="kv__row"><span>触发规则</span><span>${U.esc(a.trigger)}</span></div>
              </div>
              <label class="fz-12 t-dim" style="display:block;margin-bottom:6px">复核意见（可选）</label>
              <textarea class="code-edit" id="rvNote" placeholder="补充教师判断，将随复核记录留存…">${U.esc(a.note || '')}</textarea>`,
            footer: `<button class="btn btn--ghost" id="ig">忽略</button><button class="btn btn--primary" id="cf">确认预警</button>`,
            onMount(ov, close) {
              const note = () => U.$('#rvNote', ov).value.trim();
              const after = (msg) => { Toast.ok(msg); close(); self.loadAlerts(); };
              U.$('#cf', ov).addEventListener('click', () => API.teacher.reviewAlert({ alertId: a.alertId, action: 'confirm', note: note() }).then(() => after('已确认预警，进入处理流程')));
              U.$('#ig', ov).addEventListener('click', () => API.teacher.reviewAlert({ alertId: a.alertId, action: 'ignore', note: note() }).then(() => after('已忽略该预警')));
            }
          });
        }));
      });
    }
  };

Router.register('monitor', { title: '学情监测看板', mount: () => Monitor.render() });
