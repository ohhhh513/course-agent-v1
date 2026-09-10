'use strict';

  /* ================================================================
     视图 2 · 学情监测看板（热力图 / 个体详情 / 预警复核）
     ================================================================ */
  function formatAnswerDuration(value) {
    const totalSeconds = Math.max(0, Math.floor(Number(value) || 0));
    return `${totalSeconds}″`;
  }

  const Monitor = {
    stuLevel: 'all', stuKeyword: '', level: 'all', heatType: 'completion',
    render() {
      const el = U.$('#view-monitor');
      el.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="card__head">
          <h3 id="heatTitle">${icon('grid')} 知识点 × 学生 学习完成热力图</h3>
          <span class="spacer"></span>
          <select class="input select select--sm" id="heatType" style="width:164px">
            <option value="completion">学习完成热力图</option>
            <option value="mastery">知识点掌握热力图</option>
          </select>
          <div class="hm-legend" style="margin-left:12px"><span>低</span><div class="hm-legend__bar"></div><span>高</span></div>
        </div>
        <div class="card__body">
          <div class="chart" id="heatChart" style="height:520px"></div>
          <div class="divider"></div>
          <p class="fz-12 t-dim" style="margin-bottom:8px" id="heatWeakLabel">共性薄弱识别（班级平均学习完成率最低的 3 个知识点）</p>
          <div class="chips" id="weakChips"></div>
        </div>
      </div>

      <div class="grid g-12">
        <div class="card">
          <div class="card__head"><h3>${icon('users')} 学生学情列表</h3><span class="spacer"></span>
            <div class="search" style="width:160px">${icon('search2')}<input class="input" id="stuSearch" placeholder="姓名 / 学号"></div>
            <div class="seg" id="stuSeg"><button data-l="all" class="is-active">全部</button><button data-l="red">红</button><button data-l="yellow">黄</button><button data-l="green">绿</button></div>
          </div>
          <div class="card__body card__body--flush"><div class="list" id="stuList" style="max-height:calc(100vh - 184px);overflow:auto">${U.skeleton(300)}</div></div>
        </div>

        <div class="card">
          <div class="card__head"><h3>${icon('bell')} 异常预警列表</h3><span class="spacer"></span>
            <div class="seg" id="alSeg"><button data-l="all" class="is-active">全部</button><button data-l="red">红</button><button data-l="yellow">黄</button></div>
          </div>
          <div class="card__body stack" id="alList" style="max-height:calc(100vh - 220px);overflow:auto;min-height:240px">${U.skeleton(300)}</div>
        </div>
      </div>`;

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

      // 初次渲染即同步标题/标签，避免静态 HTML 文案与当前 heatType 不一致
      this.updateHeatLabels();

      this.loadHeat(); this.loadStudents(); this.loadAlerts();
    },

    updateHeatLabels() {
      const isMastery = this.heatType === 'mastery';
      U.$('#heatTitle').innerHTML = `${icon('grid')} 知识点 × 学生 ${isMastery ? '知识掌握' : '学习完成'}热力图`;
      U.$('#heatWeakLabel').textContent = isMastery
        ? '共性薄弱识别（班级平均知识掌握率低于 80% 的知识点）'
        : '共性薄弱识别（班级平均学习完成率低于 80% 的知识点）';
    },

    loadHeat() {
      API.teacher.heatmap({ classId: state.classId, type: this.heatType }).then(h => {
        Charts.heatmap('#heatChart', h, (val, data) => {
          if (val[2] == null) return; // 灰色格子不可点
          const stu = data.studentAxis[val[1]];
          if (stu && stu.userId) this.openProfile(stu.userId);
        });
        U.$('#weakChips').innerHTML = (h.weakest && h.weakest.length)
          ? h.weakest.map(w =>
              `<span class="chip">${icon('alert')} ${U.esc(w.name)} <b class="mono">${w.avg}%</b></span>`).join('')
          : `<span class="empty" style="padding:14px 0">暂无低于 80% 的知识点${this.heatType === 'mastery' ? '（题库未导入时无答题记录，暂不展示）' : ''}</span>`;
      });
    },

    loadStudents() {
      API.teacher.students({ classId: state.classId, alertLevel: this.stuLevel, keyword: this.stuKeyword }).then(r => {
        const box = U.$('#stuList'); if (!box) return;
        box.innerHTML = r.list.map(s => `
          <div class="list__item list__item--clickable" data-uid="${s.userId}">
            <div class="stu-row" style="flex:1;min-width:0">
              <span class="avatar" style="width:34px;height:34px;flex:0 0 34px;font-size:13px">${s.avatar}</span>
              <div class="stu-row__info"><b>${U.esc(s.name)}</b><span>${s.no} · ${s.lastActive}</span></div>
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
      API.teacher.studentProfile({ userId }).then(p => {
        Modal.drawer({
          title: '个体学情详情 · ' + p.name,
          body: `
          <div class="node-detail__hero">
            <div class="row" style="gap:9px;margin-bottom:8px">
              <span class="badge badge--brand">${p.className}</span>
              <span class="badge badge--outline mono">${p.no}</span>
              <span class="badge badge--outline">班级第 ${p.metrics.rank}/${p.metrics.totalStudents} 名</span>
            </div>
            <div class="grid g-4" style="gap:10px;margin:4px 0 0">
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:20px;display:block">${p.metrics.completion}%</b><span class="fz-11 t-dim">完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:20px;display:block;color:var(--brand-400)">${p.metrics.mastery}%</b><span class="fz-11 t-dim">学习完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:20px;display:block;color:var(--accent-500)">${p.metrics.goal}%</b><span class="fz-11 t-dim">目标达成</span></div>
              <div class="card card--flat card--pad" style="text-align:center"><b class="mono" style="font-size:20px;display:block;color:var(--ok)">${p.metrics.accuracy}%</b><span class="fz-11 t-dim">练习正确率</span></div>
            </div>
          </div>
          <div style="padding:18px">
            <p class="fz-12 t-dim" style="margin-bottom:8px">学习时间表（本周各时段活跃度）</p>
            <div class="chart chart--sm" id="stuTimeChart"></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">学习活跃度趋势（学习时长 / AI 提问）</p>
            <div class="chart chart--sm" id="stuTrendChart"></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">知识点答题明细</p>
            <div class="tbl-wrap"><table class="tbl tbl--compact" id="stuKpTbl"></table></div>
            <p class="fz-12 t-dim" style="margin:14px 0 8px">高频错题</p>
            <div class="stack" style="gap:8px">${(p.wrongDetail || []).map(w => `
              <div class="file-item">${icon('alert')}<b>${U.esc(w.kp)}</b>
                <span class="fz-11 t-dim nowrap">错 ${w.count} 次</span></div>`).join('') || '<span class="fz-12 t-dim">暂无高频错题</span>'}</div>
          </div>`,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="prMsg">${icon('message')} 发送私信</button>
            <button class="btn btn--primary" id="prReport">${icon('file')} 学情报告</button>`,
          onMount(ov, close) {
            Charts.bar('#stuTimeChart', p.studyTimeDist.data.map((v, i) => ({ name: p.studyTimeDist.xAxis[i], value: v })), { color: Charts.tokens().brand });
            const studyMinutes = (p.activityTrend.minutes || []).map(v => Number(v) || 0);
            const minutePeak = Math.max(...studyMinutes, 0);
            let minuteInterval = 1;
            while (minutePeak > minuteInterval * 4) minuteInterval *= 2;
            const minuteMax = minuteInterval * 4;

            const aiQuestions = (p.activityTrend.questions || []).map(v => Number(v) || 0);
            const aiPeak = Math.max(...aiQuestions, 0);
            let aiInterval = 1;
            while (aiPeak > aiInterval * 4) aiInterval *= 2;
            const aiMax = aiInterval * 4;
            Charts.line('#stuTrendChart', {
              xAxis: p.activityTrend.xAxis,
              series: [
                { name: '学习时长', data: studyMinutes, color: Charts.tokens().brand, yAxisIndex: 0 },
                { name: 'AI 提问', data: aiQuestions, color: Charts.tokens().warn, yAxisIndex: 1 }
              ]
            }, {
              yAxes: [
                { name: '分钟', min: 0, max: minuteMax, interval: minuteInterval, color: Charts.tokens().brand },
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

    loadAlerts() {
      const self = this;
      API.teacher.alerts({ classId: state.classId, level: this.level }).then(r => {
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

        U.$$('#alList [data-detail]').forEach(b => b.addEventListener('click', () => {
          const a = r.list.find(x => x.alertId === b.dataset.detail);
          Modal.open({
            title: '预警详情 · ' + a.student, size: 'wide',
            body: `<p class="fz-12 t-dim" style="margin-bottom:10px">触发规则：<b>${U.esc(a.trigger)}</b></p>
              <div class="chart chart--sm" id="alTrend"></div>
              <div class="divider"></div>
              <div class="callout callout--brand">${icon('bulb')}
                <div>建议：${a.level === 'red' ? '立即人工介入 / 推送补救资源' : '持续监控并安排一次靶向练习'}</div></div>`,
            footer: `<button class="btn" data-close>关闭</button>
              <button class="btn btn--outline" id="aIv">${icon('route')} 生成干预</button>`,
            onMount(ov, close) {
              Charts.line('#alTrend', { xAxis: ['4步前', '3步前', '2步前', '前次', '当前'], series: [{ name: '学习完成率', data: a.trendData, color: a.level === 'red' ? Charts.tokens().danger : Charts.tokens().warn }] }, { max: 100, fmt: '{value}%' });
              U.$('#aIv', ov).addEventListener('click', () => { close(); Router.go('intervention'); });
            }
          });
        }));

        U.$$('#alList [data-review]').forEach(b => b.addEventListener('click', () => {
          const a = r.list.find(x => x.alertId === b.dataset.review);
          Modal.open({
            title: '复核预警 · ' + a.student,
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
