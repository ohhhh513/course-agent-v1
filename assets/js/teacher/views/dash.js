'use strict';

  /* ================================================================
     视图 1 · 教学驾驶舱
     ================================================================ */
  const Dash = {
    rankingTone(value) {
      const mastery = Number(value) || 0;
      if (mastery <= 25) return { bar: 'dashRed', text: 't-dash-red' };
      if (mastery < 50) return { bar: 'dashBrown', text: 't-dash-brown' };
      if (mastery < 75) return { bar: 'dashLightGreen', text: 't-dash-light-green' };
      return { bar: 'dashGreen', text: 't-dash-green' };
    },

    render() {
      const el = U.$('#view-dashboard');
      el.innerHTML = U.skeleton(420);
      const classId = state.classId;
      const studentsReq = API.teacher.students({
        classId,
        alertLevel: 'all',
        page: 1,
        size: 10000
      }).catch(() => ({ list: [] }));
      Promise.all([
        API.teacher.dashboard({ classId }),
        studentsReq
      ]).then(([d, studentsData]) => {
        const classStudents = Array.isArray(studentsData) ? studentsData : ((studentsData && studentsData.list) || []);
        const allFeed = Array.isArray(d.liveFeed) ? d.liveFeed : [];
        const ov = d.classOverview;
        el.innerHTML = `
        <div class="hero">
          <div class="hero__main">
            <div class="row" style="margin-bottom:6px">
              ${R.lamp(ov.alertRatio >= 20 ? 'red' : 'yellow', '预警占比 ' + ov.alertRatio + '%')}
              <span class="badge badge--outline">${ov.studentCount} 名学生</span>
              <span class="badge badge--brand">${ov.className}</span>
            </div>
            <h2>${ov.className} · 教学驾驶舱</h2>
            <p>数据更新于 <b class="t-brand">${ov.updatedAt}</b> · 今日活跃 <b>${ov.activeToday}</b> 人 · 提交 <b>${ov.submitToday}</b> 次</p>
          </div>
          <div class="hero__stats">
            <div class="hero__stat"><b class="mono">${ov.avgMasteryRate}%</b><span>平均学习完成率</span>${U.delta(ov.deltaMastery)}</div>
            <div class="hero__stat"><b class="mono">${ov.avgCompletionRate}%</b><span>平均完成率</span>${U.delta(ov.deltaCompletion)}</div>
            <div class="hero__stat"><b class="mono">${ov.avgGoalAchieve}%</b><span>目标达成度</span>${U.delta(ov.deltaGoal)}</div>
          </div>
        </div>

        <div class="grid g-21" style="margin-bottom:16px">
          <div class="card dash-todo-card">
            <div class="card__head"><h3>${icon('bell')} 待办事项</h3><span class="spacer"></span>
              <span class="badge badge--danger">${d.todos.length} 项</span></div>
            <div class="card__body stack dash-todo-card__body" style="gap:10px">${d.todos.map(R.todo).join('')}</div>
          </div>
          <div class="card dash-live-card">
            <div class="card__head"><h3>${icon('trend')} 实时动态</h3><span class="spacer"></span>
              <button class="btn btn--outline btn--sm dash-live-filter" id="dashLiveStudentPicker" type="button" aria-expanded="false">
                <span id="dashLiveStudentLabel">全部学生</span>${icon('chevronDown')}
              </button></div>
            <div class="card__body card__body--flush dash-live-card__body">
              <div class="dash-live-panel" id="dashLivePanel">
                <div class="dash-live-feed" id="dashLiveFeed"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="grid g-2">
          <div class="card dash-kp-ranking-card">
            <div class="card__head"><h3>${icon('target')} 班级共性薄弱知识点排行</h3><span class="spacer"></span>
              <span class="badge badge--danger">Top 5</span></div>
            <div class="card__body dash-kp-ranking-card__body">
              ${d.kpRanking.map(k => {
                const mastery = Math.max(0, Math.min(100, Number(k.mastery) || 0));
                const tone = Dash.rankingTone(mastery);
                return `
                <div style="margin-bottom:15px">
                  <div class="row fz-13" style="margin-bottom:5px"><b>${U.esc(k.name)}</b><span class="spacer"></span>
                    <span class="mono fz-12 ${tone.text}">${mastery}%</span></div>
                  ${U.bar(mastery, tone.bar, 'sm')}
                  <div class="fz-11 t-dim" style="margin-top:4px">${k.weakCount} / ${k.students} 名学生未达标</div>
                </div>`;
              }).join('')}
            </div>
          </div>
          <div class="card">
            <div class="card__head"><h3>${icon('grid')} 班级学情总览</h3></div>
            <div class="card__body">
              <div class="chart" id="dashDonut"></div>
              <div class="callout callout--brand" style="margin-top:4px">${icon('info')}
                <div>红色预警学生 <b>${ov.alertStudentCount}</b> 名（占比 ${ov.alertRatio}%），建议优先处理驾驶舱待办中的干预建议。</div></div>
            </div>
          </div>
        </div>`;

        Charts.donut('#dashDonut', [
          { name: '预警学生', value: ov.alertStudentCount, color: Charts.tokens().danger },
          { name: '正常学生', value: Math.max(0, ov.studentCount - ov.alertStudentCount), color: Charts.tokens().ok }
        ], { centerValue: ov.alertStudentCount, centerLabel: '预警学生' });

        let liveStudentId = 'all';
        const studentById = new Map(classStudents.map(s => [String(s.userId), s]));
        const livePanel = U.$('#dashLivePanel', el);
        const livePickerBtn = U.$('#dashLiveStudentPicker', el);
        const liveStudentLabel = U.$('#dashLiveStudentLabel', el);

        const renderLiveFeed = () => {
          if (!livePanel) return;
          livePanel.innerHTML = '<div class="dash-live-feed" id="dashLiveFeed"></div>';
          const feedEl = U.$('#dashLiveFeed', livePanel);
          const feed = liveStudentId === 'all'
            ? allFeed
            : allFeed.filter(f => String(f.userId) === String(liveStudentId));
          feedEl.innerHTML = feed.length ? `<div class="list">
            ${feed.map(f => `
              <div class="list__item">
                <span class="list__lead" style="color:${f.level === 'danger' ? 'var(--danger)' : f.level === 'warn' ? 'var(--warn)' : 'var(--ok)'}">
                  ${icon(f.type === 'submit' ? 'check' : f.type === 'alert' ? 'alert' : 'message')}</span>
                <div class="list__main"><b>${U.esc(f.text)}</b><p>${U.esc(f.meta)}</p></div>
                <span class="list__trail fz-11 t-dim">${U.esc(f.time || '')}</span>
              </div>`).join('')}
          </div>` : `<div class="dash-live-empty">${liveStudentId === 'all' ? '当前班级暂无动态' : '该学生暂无动态'}</div>`;
          if (livePickerBtn) livePickerBtn.setAttribute('aria-expanded', 'false');
        };

        const openLivePicker = () => {
          if (!livePanel) return;
          if (livePickerBtn && livePickerBtn.getAttribute('aria-expanded') === 'true') {
            renderLiveFeed();
            return;
          }
          livePanel.innerHTML = `
            <div class="dash-live-picker">
              <div class="dash-live-picker__options">
                <button class="dash-live-student-option ${liveStudentId === 'all' ? 'is-active' : ''}" type="button" data-live-student-id="all">
                  <b>全部学生</b>
                </button>
                ${classStudents.map(s => {
                  const id = String(s.userId || '');
                  return `<button class="dash-live-student-option ${liveStudentId === id ? 'is-active' : ''}" type="button" data-live-student-id="${U.esc(id)}">
                    <b>${U.esc(s.name || id)}</b>
                  </button>`;
                }).join('')}
                ${classStudents.length ? '' : '<div class="dash-live-picker__empty">暂无可选学生</div>'}
              </div>
            </div>`;
          if (livePickerBtn) livePickerBtn.setAttribute('aria-expanded', 'true');

          U.$$('.dash-live-student-option', livePanel).forEach(option => {
            option.addEventListener('click', () => {
              liveStudentId = option.dataset.liveStudentId || 'all';
              const selected = studentById.get(String(liveStudentId));
              if (liveStudentLabel) liveStudentLabel.textContent = liveStudentId === 'all' ? '全部学生' : (selected ? selected.name : '全部学生');
              renderLiveFeed();
            });
          });
        };

        if (liveStudentLabel) liveStudentLabel.textContent = '全部学生';
        renderLiveFeed();
        if (livePickerBtn) livePickerBtn.addEventListener('click', openLivePicker);

        U.$$('.todo', el).forEach(t => {
          const btn = t.querySelector('.btn');
          // 「发消息」按钮：单独阻止冒泡并打开发送私信弹窗
          if (t.dataset.action === '发消息' && btn) {
            btn.addEventListener('click', e => {
              e.stopPropagation();
              Dash.openMessageModal(t.dataset.userId, t.dataset.userName);
            });
            // 点击 todo 非按钮区域仍按原 target 跳转
            t.addEventListener('click', e => {
              if (e.target === t || e.target.closest('.todo__main') || e.target.closest('.todo__ico')) {
                if (t.dataset.target) Router.go(t.dataset.target);
              }
            });
          } else {
            t.addEventListener('click', () => { if (t.dataset.target) Router.go(t.dataset.target); });
          }
        });
      }).catch(err => {
        el.innerHTML = `<div class="card card--pad"><div class="callout callout--danger">${icon('alert')}<div>教学驾驶舱加载失败：${U.esc(err.message || err)}</div></div></div>`;
      });
    },

    openMessageModal(userId, userName) {
      const body = `
        <div class="stack" style="gap:12px;min-width:360px">
          <div class="kv"><div class="kv__row"><span>收件人</span><span>${U.esc(userName || userId || '')}</span></div></div>
          <textarea id="msgContent" class="input" rows="5" placeholder="请输入私信内容，例如：同学你好，最近完成率较低，建议课后找时间补学第2章线性表相关内容。"></textarea>
          <div class="fz-12 t-dim">发送后将出现在学生的「消息与通知」中。</div>
        </div>`;
        Modal.open({
        title: '发送私信',
        body,
        footer: '<button class="btn" data-close>取消</button><button class="btn btn--primary" id="sendMsgBtn">发送</button>',
        onMount(ov, close) {
          const btn = U.$('#sendMsgBtn');
          const ta = U.$('#msgContent');
          if (btn) btn.addEventListener('click', () => {
            const content = ta ? ta.value.trim() : '';
            if (!content) { Toast.warn('请输入私信内容'); return; }
            btn.disabled = true; btn.textContent = '发送中…';
            API.teacher.sendMessage({ userId, content })
              .then(() => {
                Toast.ok('私信发送成功');
                close();
              })
              .catch(err => {
                btn.disabled = false; btn.textContent = '发送';
                Toast.warn('发送失败：' + (err.message || err));
              });
          });
        }
      });
    }
  };

Router.register('dashboard', { title: '教学驾驶舱', mount: () => Dash.render() });
