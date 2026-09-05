'use strict';

  /* ================================================================
     视图 1 · 教学驾驶舱
     ================================================================ */
  const Dash = {
    render() {
      const el = U.$('#view-dashboard');
      el.innerHTML = U.skeleton(420);
      API.teacher.dashboard({ classId: state.classId }).then(d => {
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
          <div class="card">
            <div class="card__head"><h3>${icon('bell')} 待办事项</h3><span class="spacer"></span>
              <span class="badge badge--danger">${d.todos.length} 项</span></div>
            <div class="card__body stack" style="gap:10px">${d.todos.map(R.todo).join('')}</div>
          </div>
          <div class="card">
            <div class="card__head"><h3>${icon('trend')} 实时动态</h3><span class="spacer"></span>
              <span class="badge badge--ok">实时</span></div>
            <div class="card__body card__body--flush">
              <div class="list" style="max-height:360px;overflow:auto">
                ${d.liveFeed.map(f => `
                  <div class="list__item">
                    <span class="list__lead" style="color:${f.level === 'danger' ? 'var(--danger)' : f.level === 'warn' ? 'var(--warn)' : 'var(--ok)'}">
                      ${icon(f.type === 'submit' ? 'check' : f.type === 'alert' ? 'alert' : 'message')}</span>
                    <div class="list__main"><b>${U.esc(f.text)}</b><p>${U.esc(f.meta)}</p></div>
                    <span class="list__trail fz-11 t-dim">${f.time}</span>
                  </div>`).join('')}
              </div>
            </div>
          </div>
        </div>

        <div class="grid g-2">
          <div class="card">
            <div class="card__head"><h3>${icon('target')} 班级共性薄弱知识点排行</h3><span class="spacer"></span>
              <span class="badge badge--danger">Top 5</span></div>
            <div class="card__body">
              ${d.kpRanking.map(k => `
                <div style="margin-bottom:15px">
                  <div class="row fz-13" style="margin-bottom:5px"><b>${U.esc(k.name)}</b><span class="spacer"></span>
                    <span class="mono fz-12 ${k.mastery < 60 ? 't-danger' : 't-warn'}">${k.mastery}%</span></div>
                  ${U.bar(k.mastery, k.mastery < 60 ? 'weak' : 'fair', 'sm')}
                  <div class="fz-11 t-dim" style="margin-top:4px">${k.weakCount} / ${k.students} 名学生未达标</div>
                </div>`).join('')}
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
