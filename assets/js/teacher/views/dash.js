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

    /** 指标环配色：与学生端五级色阶同源（≥85 优秀 / ≥60 达标 / ≥40 待加强 / 其余薄弱） */
    ringTone(v) {
      const t = Charts.tokens();
      const n = Number(v) || 0;
      if (n >= 85) return t.ok;
      if (n >= 60) return t.brand;
      if (n >= 40) return t.warn;
      return t.danger;
    },

    render() {
      const el = U.$('#view-dashboard');
      el.innerHTML = U.skeleton(420);
      if (!API.config.activeCourseId) {
        el.innerHTML = `
        <div class="card"><div class="card__body">
          <div class="empty" style="padding:48px 20px;text-align:center">
            <b>尚未创建或选择课程</b>
            <p class="fz-12 t-dim" style="margin-top:8px">请先在顶栏「+ 新建课程」，再查看教学驾驶舱。</p>
          </div>
        </div></div>`;
        return;
      }
      const studentsReq = API.teacher.students({
        alertLevel: 'all',
        page: 1,
        size: 10000
      }).catch(() => ({ list: [] }));
      Promise.all([
        API.teacher.dashboard(),
        studentsReq
      ]).then(([d, studentsData]) => {
        const classStudents = Array.isArray(studentsData) ? studentsData : ((studentsData && studentsData.list) || []);
        const allFeed = Array.isArray(d.liveFeed) ? d.liveFeed : [];
        const ov = d.classOverview;
        const courseName = ov.courseName || ov.className || '当前课程';
        el.innerHTML = `
        <div class="hero" style="margin-bottom:16px">
          <div class="hero__main">
            <div class="row" style="margin-bottom:6px">
              ${R.lamp(ov.alertRatio >= 20 ? 'red' : 'yellow', '预警占比 ' + ov.alertRatio + '%')}
              <span class="badge badge--outline">${ov.studentCount} 名学生</span>
              <span class="badge badge--brand">${U.esc(courseName)}</span>
            </div>
            <h2>${U.esc(courseName)} · 教学驾驶舱</h2>
            <p>数据更新于 <b class="t-brand">${ov.updatedAt}</b> · 今日活跃 <b>${ov.activeToday}</b> 人
              · 提交 <b>${ov.submitToday}</b> 次</p>
          </div>
          <div class="hero__rings">
            <div class="hero__ring">
              <div class="chart chart--ring" id="dashRingMastery"></div>
              <b>平均学习完成率</b>
              <span class="fz-11 t-dim">全班知识点掌握率均值</span>
            </div>
            <div class="hero__ring">
              <div class="chart chart--ring" id="dashRingCompletion"></div>
              <b>平均完成率</b>
              <span class="fz-11 t-dim">每个学生已完成知识点占比的均值</span>
            </div>
            <div class="hero__ring">
              <div class="chart chart--ring" id="dashRingGoal"></div>
              <b>目标达成度</b>
              <span class="fz-11 t-dim">掌握率 ≥60% 的知识点占比</span>
            </div>
          </div>
        </div>

        <div class="grid g-21" style="margin-bottom:16px">
          <div class="card dash-todo-card">
            <div class="card__head"><h3>${icon('bell')} 待办事项</h3><span class="spacer"></span>
              <span class="badge badge--danger" id="dashTodoCount">${d.todos.length} 项</span></div>
            <div class="card__body stack dash-todo-card__body" style="gap:10px" id="dashTodos"></div>
          </div>
          <div class="card dash-live-card">
            <div class="card__head"><h3>${icon('trend')} 实时动态</h3>
              <span class="badge badge--outline">仅今天</span>
              <span class="spacer"></span>
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
            </div>
          </div>
        </div>`;

        // ---- 顶部三指标：环状图（口径见标签下的说明）----
        Charts.gauge('#dashRingMastery', ov.avgMasteryRate || 0, { name: '', color: Dash.ringTone(ov.avgMasteryRate) });
        Charts.gauge('#dashRingCompletion', ov.avgCompletionRate || 0, { name: '', color: Dash.ringTone(ov.avgCompletionRate) });
        Charts.gauge('#dashRingGoal', ov.avgGoalAchieve || 0, { name: '', color: Dash.ringTone(ov.avgGoalAchieve) });

        Charts.donut('#dashDonut', [
          { name: '预警学生', value: ov.alertStudentCount, color: Charts.tokens().danger },
          { name: '正常学生', value: Math.max(0, ov.studentCount - ov.alertStudentCount), color: Charts.tokens().ok }
        ], { centerValue: ov.alertStudentCount, centerLabel: '预警学生' });

        // ================= 待办：可忽略（仅当日生效，次日自动恢复） =================
        // 存储结构 {date:'YYYY-MM-DD', ids:[...]}：跨天自动失效——同一条待办
        // 若问题仍在（预警未处理/完成率仍低），第二天会重新出现。
        const todoKey = 'ca_dash_todos_ignored::' + (ov.courseId || 'default');
        const todayStr = (ov.updatedAt || '').slice(0, 10) || new Date().toISOString().slice(0, 10);
        const readIgnored = () => {
          try {
            const v = JSON.parse(localStorage.getItem(todoKey) || 'null');
            return (v && v.date === todayStr && Array.isArray(v.ids)) ? v.ids : [];
          } catch (e) { return []; }
        };
        const saveIgnored = ids => {
          try { localStorage.setItem(todoKey, JSON.stringify({ date: todayStr, ids })); } catch (e) {}
        };
        let ignored = readIgnored();

        const renderTodos = () => {
          const box = U.$('#dashTodos', el);
          if (!box) return;
          const list = d.todos.filter(t => !ignored.includes(t.id));
          const cnt = U.$('#dashTodoCount', el);
          if (cnt) cnt.textContent = list.length + ' 项';
          box.innerHTML = list.length
            ? list.map(R.todo).join('')
            : `<div class="dash-live-empty">${d.todos.length ? '今日待办已全部忽略，次日恢复显示' : '暂无待办，班级运行良好'}</div>`;

          U.$$('.todo', box).forEach(t => {
            // 「忽略」：仅当日隐藏该条待办（不改变预警/学情状态），次日自动恢复
            const ign = document.createElement('button');
            ign.type = 'button';
            ign.className = 'btn btn--sm btn--ghost dash-todo-ignore';
            ign.textContent = '忽略';
            ign.title = '仅今日不再显示该待办，次日自动恢复';
            ign.addEventListener('click', e => {
              e.stopPropagation();
              if (t.dataset.todoId && !ignored.includes(t.dataset.todoId)) {
                ignored.push(t.dataset.todoId);
                saveIgnored(ignored);
              }
              Toast.info('已忽略该待办', '仅今日生效，次日自动恢复');
              renderTodos();
            });
            t.appendChild(ign);

            const btn = t.querySelector('.btn');
            // 低正确率待办直接查看错题；进度滞后待办保留发送私信。
            if (t.dataset.action === '查看详情' && t.dataset.userId) {
              t.addEventListener('click', e => {
                if (e.target.closest('.dash-todo-ignore')) return;
                Dash.openWrongQuestions(t.dataset.userId, t.dataset.userName);
              });
            } else if (t.dataset.action === '发消息' && btn) {
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
              t.addEventListener('click', e => {
                if (e.target.closest('.dash-todo-ignore')) return;
                if (t.dataset.target) Router.go(t.dataset.target);
              });
            }
          });
        };
        renderTodos();

        // ================= 实时动态（仅当天；练习按场次汇总 + 资源学习 + 预警） =================
        let liveStudentId = 'all';
        const studentById = new Map(classStudents.map(s => [String(s.userId), s]));
        const livePanel = U.$('#dashLivePanel', el);
        const livePickerBtn = U.$('#dashLiveStudentPicker', el);
        const liveStudentLabel = U.$('#dashLiveStudentLabel', el);

        const feedIcon = f => f.type === 'practice' ? 'checkCircle'
          : f.type === 'alert' ? 'alert'
            : f.resType === 'video' ? 'play'
              : f.resType === 'ppt' ? 'ppt'
                : f.resType === 'doc' ? 'file' : 'message';
        const feedColor = l => l === 'danger' ? 'var(--danger)' : l === 'warn' ? 'var(--warn)' : 'var(--ok)';

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
                <span class="list__lead" style="color:${feedColor(f.level)}">${icon(feedIcon(f))}</span>
                <div class="list__main"><b>${U.esc(f.text)}</b><p>${U.esc(f.meta)}</p></div>
                <span class="list__trail fz-11 t-dim">${U.esc(f.time || '')}</span>
              </div>`).join('')}
          </div>` : `<div class="dash-live-empty">${liveStudentId === 'all' ? '今天暂无学习动态' : '该学生今天暂无学习动态'}</div>`;
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
      }).catch(err => {
        el.innerHTML = `<div class="card card--pad"><div class="callout callout--danger">${icon('alert')}<div>教学驾驶舱加载失败：${U.esc(err.message || err)}</div></div></div>`;
      });
    },

    openWrongQuestions(userId, userName, initialKpIds = null) {
      const courseId = API.config.activeCourseId;
      let generation = 0, selected = initialKpIds ? new Set(initialKpIds) : null, points = [], currentPage = 1;
      const types = { single: '单选题', multi: '多选题', judge: '判断题', blank: '填空题', code: '编程题' };
      const answerText = (value, type) => {
        if (type === 'blank') {
          try {
            const parsed = JSON.parse(value);
            if (Array.isArray(parsed)) return parsed.map((v, i) => `第 ${i + 1} 空：${v || '未作答'}`).join('；');
          } catch (e) { /* 旧记录以分号分隔，直接展示。 */ }
        }
        return value || '未作答';
      };
      Modal.open({
        title: `${U.esc(userName || '学生')} · 错题详情`, size: 'wide',
        body: `<div class="dash-wrong-detail">
          <div class="dash-wrong-filter">
            <div class="row row--wrap"><b>高频错误知识点</b><span class="spacer"></span>
              <button type="button" class="btn btn--sm btn--ghost" data-wrong-all disabled>全选</button>
              <button type="button" class="btn btn--sm btn--ghost" data-wrong-clear disabled>清空</button></div>
            <p class="fz-12 t-dim">按累计答错次数排序，可多选；下方按题合并展示历史错题，最近已答对的题会标注。</p>
            <div class="dash-wrong-kps" data-wrong-kps></div>
          </div>
          <div class="fz-12 t-dim" data-wrong-count aria-live="polite"></div>
          <div class="stack" style="gap:14px" data-wrong-list></div>
          <div class="row row--wrap" data-wrong-pages></div>
        </div>`,
        onMount: ov => {
          const kpBox = ov.querySelector('[data-wrong-kps]');
          const listBox = ov.querySelector('[data-wrong-list]');
          const countBox = ov.querySelector('[data-wrong-count]');
          const pageBox = ov.querySelector('[data-wrong-pages]');
          const allButton = ov.querySelector('[data-wrong-all]');
          const clearButton = ov.querySelector('[data-wrong-clear]');
          const valid = () => ov.isConnected && API.config.activeCourseId === courseId;
          const paintFilters = () => {
            kpBox.innerHTML = points.map(k => `<label class="dash-wrong-kp ${selected.has(k.kpId) ? 'is-selected' : ''}">
              <input type="checkbox" value="${U.esc(k.kpId)}" ${selected.has(k.kpId) ? 'checked' : ''}>
              <span>${U.esc(k.name)}<small>${k.questionCount} 道错题 · 答错 ${k.wrongCount} 次</small></span></label>`).join('')
              || '<span class="fz-12 t-dim">暂无错题知识点</span>';
            allButton.disabled = !points.length;
            clearButton.disabled = !points.length;
          };
          const load = async (page = 1) => {
            const ticket = ++generation;
            pageBox.innerHTML = '';
            if (selected && !selected.size) {
              countBox.textContent = '已选择 0 个知识点';
              listBox.innerHTML = '<div class="empty">请选择上方知识点查看错题</div>';
              return;
            }
            listBox.innerHTML = U.skeleton(160);
            countBox.textContent = '正在读取错题…';
            try {
              const data = await API.teacher.studentWrongQuestions({ userId,
                kpIds: selected ? [...selected].join(',') : '', page, size: 10 });
              if (!valid() || ticket !== generation) return;
              points = data.knowledgePoints || [];
              if (selected === null) selected = new Set(points.map(k => k.kpId));
              paintFilters();
              currentPage = data.page;
              countBox.textContent = `已选择 ${selected.size} 个知识点 · 共 ${data.total} 道错题`;
              listBox.innerHTML = (data.list || []).map((q, index) => {
                const options = q.type === 'blank' ? '' : (q.options || []).map(o => `<div class="opt ${o.right ? 'is-right' : ''}">
                  <span class="opt__key">${U.esc(o.key || '')}</span><span style="flex:1;white-space:pre-wrap">${U.esc(o.text || '')}</span>
                  ${o.right ? '<span class="badge badge--ok">正确答案</span>' : ''}</div>`).join('');
                return `<article class="card dash-wrong-question">
                  <div class="card__body stack" style="gap:12px">
                    <div class="row row--wrap"><b>第 ${(data.page - 1) * data.size + index + 1} 题</b>
                      <span class="badge badge--outline">${U.esc(types[q.type] || '题目')}</span>
                      <span class="badge badge--outline">${U.esc(q.chapter || '未分章')}</span>
                      <span class="spacer"></span><span class="badge badge--danger">累计答错 ${q.wrongCount} 次</span>
                      <span class="badge ${q.latestCorrect ? 'badge--ok' : 'badge--warn'}">${q.latestCorrect ? '最近已答对' : '最近仍答错'}</span></div>
                    <div class="row row--wrap">${(q.knowledgePoints || []).map(k => `<span class="badge badge--brand">${U.esc(k.name)}</span>`).join('')}</div>
                    <div class="dash-wrong-text">${U.esc(q.stem)}</div>
                    <div data-wrong-figure="${index}"></div>
                    ${options ? `<div class="opts opts--readonly">${options}</div>` : ''}
                    <div class="dash-wrong-answers">
                      <div>最近一次错误作答：<b class="t-danger">${U.esc(answerText(q.myAnswer, q.type))}</b></div>
                      <div>正确答案：<b class="t-ok">${U.esc(q.answer || '暂无答案')}</b></div>
                      ${q.latestCorrect ? `<div>最近作答：<b class="t-ok">${U.esc(answerText(q.latestAnswer, q.type))}</b></div>` : ''}
                    </div>
                    <div><b class="fz-12">题目解析</b><div class="dash-wrong-text fz-13" style="margin-top:6px">${U.esc(q.analysis || '暂无解析')}</div></div>
                    <div class="fz-11 t-dim">最近答错：${U.esc(q.lastWrongAt || '暂无时间')} · 最近作答：${U.esc(q.latestAt || '暂无时间')}</div>
                  </div></article>`;
              }).join('') || '<div class="empty">暂无对应错题</div>';
              (data.list || []).forEach((q, index) => {
                const figure = q.figureJson, box = listBox.querySelector(`[data-wrong-figure="${index}"]`);
                if (!figure || !box) return;
                if (figure.imageUrl || figure.image_url) U.mountQuestionImage(box, figure.imageUrl || figure.image_url);
                else if (window.DsFigure) {
                  if (figure.graph) DsFigure.mount(box, figure.graph);
                  if (figure.options_graph) DsFigure.mountOptions(box, figure.options_graph);
                }
              });
              const pages = Math.max(1, Math.ceil(data.total / data.size));
              if (pages > 1) pageBox.innerHTML = `<button type="button" class="btn btn--sm" data-wrong-prev ${data.page <= 1 ? 'disabled' : ''}>上一页</button>
                <span class="fz-12 t-dim">第 ${data.page} / ${pages} 页</span>
                <button type="button" class="btn btn--sm" data-wrong-next ${data.page >= pages ? 'disabled' : ''}>下一页</button>`;
            } catch (err) {
              if (!valid() || ticket !== generation) return;
              countBox.textContent = '';
              listBox.innerHTML = `<div class="callout callout--danger">错题加载失败：${U.esc(err.message || err)}</div>
                <button type="button" class="btn btn--sm" data-wrong-retry>重试</button>`;
            }
          };
          kpBox.addEventListener('change', e => {
            if (e.target.type !== 'checkbox') return;
            if (e.target.checked) selected.add(e.target.value); else selected.delete(e.target.value);
            paintFilters(); load(1);
          });
          allButton.addEventListener('click', () => { selected = new Set(points.map(k => k.kpId)); paintFilters(); load(1); });
          clearButton.addEventListener('click', () => { selected = new Set(); paintFilters(); load(1); });
          pageBox.addEventListener('click', e => {
            if (e.target.closest('[data-wrong-prev]')) load(currentPage - 1);
            if (e.target.closest('[data-wrong-next]')) load(currentPage + 1);
          });
          listBox.addEventListener('click', e => { if (e.target.closest('[data-wrong-retry]')) load(currentPage); });
          load();
        }
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
        closeOnBackdrop: false,
        body,
        footer: '<button class="btn" data-close>取消</button><button class="btn btn--primary" id="sendMsgBtn">发送</button>',
        onMount(ov, close) {
          const btn = U.$('#sendMsgBtn', ov);
          const ta = U.$('#msgContent', ov);
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
                Toast.err('发送失败：' + (err.message || err));
              });
          });
        }
      });
    }
  };

Router.register('dashboard', { title: '教学驾驶舱', mount: () => Dash.render() });
