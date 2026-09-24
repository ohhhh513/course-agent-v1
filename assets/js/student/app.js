/* ==========================================================================
   学生端 · 应用引导（路由守卫 / 顶栏 / 全局初始化）
   必须最先加载；视图模块随后各自 Router.register，最后由 start.js 启动路由。
   ========================================================================== */
(function () {
  'use strict';
    if (window.Auth && !Auth.requireAuth('student')) return;
  
    Theme.init();
    // 侧栏图标注入
    U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', icon(n.dataset.icon, 'nav-item__icon')));
    U.$('#msgBtn').innerHTML = icon('message') + '<span class="topbar-badge" id="msgBadge" hidden>0</span>';
    initTopbar();

    /* —— 私信未读角标（真实取自 messages 表中 read=false 的条数） —— */
    let msgList = [];
    function updateMsgBadge(count) {
      const badge = U.$('#msgBadge');
      if (!badge) return;
      if (count > 0) {
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }
    function loadMsgBadge() {
      return API.student.messages()
        .then(r => updateMsgBadge((r.list || []).filter(m => !m.read).length))
        .catch(() => {});
    }
    // 供其它视图（如「预警与提醒」页读完私信后）刷新顶栏消息角标
    window.refreshMsgBadge = loadMsgBadge;

    /* ================================================================
       课程切换器（多课程 · Step 6）
       数据源 = GET /course/my；切换即 setActiveCourse + 重绘当前视图
       ================================================================ */
    const courseSel = U.$('#courseSel');
    window.renderStudentNoCourse = function (el) {
      if (!el) return;
      el.innerHTML = `
        <div class="student-course-empty">
          <div class="card student-course-empty__card">
            <div class="card__body">
              <div class="empty">
                ${icon('book')}
                <b>尚未加入课程</b>
                <p>请先点击右上角的「+」加入课程，加入后即可查看学习内容。</p>
              </div>
            </div>
          </div>
        </div>`;
    };
    Router.emptyState = (key, el) => {
      if (API.config.activeCourseId) return false;
      window.renderStudentNoCourse(el);
      return true;
    };
    function refreshStudentViewsAfterCourseChange() {
      Object.values(Router.views).forEach(view => {
        if (typeof view.reset === 'function') view.reset();
        view._mounted = false;
      });
      const key = Router.current;
      if (key && Router.views[key]) Router.go(key);
      refreshStudentUpdatedAt();
    }
    function refreshStudentUpdatedAt() {
      const courseId = API.config.activeCourseId;
      if (!courseId) return;
      API.student.dashboard().then(d => {
        if (API.config.activeCourseId !== courseId) return;
        const tag = U.$('#updateTag');
        if (tag && d && d.coreMetrics) tag.textContent = '学情更新于 ' + d.coreMetrics.updatedAt;
      }).catch(() => {});
    }
    function refreshCourseSel(preferId) {
      return API.course.my().then(list => {
        const courses = Array.isArray(list) ? list : [];
        courseSel.innerHTML = '';
        if (!courses.length) {
          API.setActiveCourse('');
          const o = document.createElement('option');
          o.value = ''; o.textContent = '未加入课程 · 点 + 加入';
          courseSel.appendChild(o);
          return;
        }
        courses.forEach(c => {
          const o = document.createElement('option');
          o.value = c.courseId; o.textContent = c.name;
          courseSel.appendChild(o);
        });
        const cur = API.config.activeCourseId;
        const target = preferId || (courses.some(c => c.courseId === cur) ? cur : courses[0].courseId);
        API.setActiveCourse(target);
        courseSel.value = target;
        }).catch(() => {});
    }
    // 首屏课程上下文 Promise：路由启动前必须等它（见 start.js），
    // 否则首次登录（localStorage 里还没有 activeCourseId）时各视图会误判为「未加入课程」。
    window.__courseReady = refreshCourseSel();
    courseSel.addEventListener('change', () => {
      if (!courseSel.value) return;
      API.setActiveCourse(courseSel.value);
      Toast.info('已切换课程', courseSel.options[courseSel.selectedIndex].text);
      refreshStudentViewsAfterCourseChange();
    });

    /* —— 凭邀请码加入课程 —— */
    const joinBtn = U.$('#joinCourseBtn');
    if (joinBtn) {
      joinBtn.innerHTML = icon('plus');
      joinBtn.title = '加入新课程';
      joinBtn.addEventListener('click', () => {
        Modal.open({
          title: '加入新课程',
          body: `<div class="stack" style="gap:14px">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">课程邀请码</span><input class="input" id="jcCode" placeholder="向授课教师索取，8 位字符" style="text-transform:uppercase"></label>
          </div>`,
          footer: `<button class="btn btn--primary" id="jcGo" type="button">加入</button><button class="btn" data-close>取消</button>`,
          onMount(ov, close) {
            U.$('#jcGo', ov).addEventListener('click', () => {
              const code = U.$('#jcCode', ov).value.trim();
              if (!code) { Toast.warn('请输入邀请码'); return; }
              API.course.join({ inviteCode: code }).then(r => {
                close();
                Toast.ok(r.alreadyJoined ? '你已在该课程中' : '加入成功', r.name);
                refreshCourseSel(r.courseId).then(() => refreshStudentViewsAfterCourseChange());
              }).catch(err => Toast.error('加入失败', err && err.message || ''));
            });
          }
        });
      });
    }
  
    /* ================================================================
       顶栏：更新时间 + 消息
       ================================================================ */
    refreshStudentUpdatedAt();
    loadMsgBadge();

    /* ================================================================
       导航侧栏 · 预警徽标（动态绑定后端真实 red + yellow 数量）
       ================================================================ */
    // 侧栏「预警与提醒」角标 = 当前课程下「待处理」（status=open）的红 + 黄预警数。
    // 2026-09-24：由写死 0 改为读真实数据（与预警页同源）。
    window.refreshAlertBadge = function () {
      const b = document.getElementById('alertBadge');
      if (!b) return;
      const courseId = API.config.activeCourseId;
      if (!courseId) { b.style.display = 'none'; return; }
      API.student.alerts({})
        .then(r => {
          if (API.config.activeCourseId !== courseId) return;   // 切课后丢弃旧结果
          const os = (r && r.openStats) || {};
          const n = (os.red || 0) + (os.yellow || 0);
          if (n > 0) {
            b.textContent = n > 99 ? '99+' : String(n);
            b.style.display = '';
          } else {
            b.style.display = 'none';
          }
        })
        .catch(() => {});
    };
    window.refreshAlertBadge();
  
    U.$('#msgBtn').addEventListener('click', () => {
      API.student.messages().then(r => {
        const list = r.list || [];
        msgList = list;
        updateMsgBadge(list.filter(m => !m.read).length);
        const body = list.length
          ? `<div class="list" style="margin:-20px">${list.map((m, idx) => {
              const preview = (m.content || '').length > 48 ? (m.content.slice(0, 48) + '…') : (m.content || '');
              return `<div class="list__item list__item--clickable msg-item ${m.read ? 'is-read' : ''}" data-msg-id="${U.esc(m.msgId)}" data-idx="${idx}">
                <span class="list__lead">${icon(m.from === '系统' ? 'info' : 'user', '')}</span>
                <div class="list__main">
                  <b>${U.esc(m.title)} ${m.read ? '' : '<span class="badge badge--danger">未读</span>'}</b>
                  <p style="margin:5px 0;line-height:1.7;color:var(--text-2)">${U.esc(preview)}</p>
                  <p class="fz-11 t-dim">${U.esc(m.from)} · ${m.time}</p>
                </div>
              </div>`;
            }).join('')}</div>`
          : `<div class="empty" style="padding:30px 20px">${icon('message')}<b>暂无消息</b><p class="t-dim">教师私信和系统通知会显示在这里</p></div>`;
        Modal.open({
          title: '消息与通知',
          body,
          onMount() {
            U.$$('.msg-item').forEach(el => {
              el.addEventListener('click', () => {
                const idx = parseInt(el.dataset.idx, 10);
                const m = list[idx];
                if (!m) return;
                openMessageDetail(m, el);
              });
            });
          }
        });
      });
    });

    // 点击消息项 → 打开详情弹窗（含完整内容），未读则自动标记已读
    function openMessageDetail(m, listEl) {
      const detailBody = `<div class="msg-detail">
        <div class="msg-detail__meta">
          <span class="list__lead">${icon(m.from === '系统' ? 'info' : 'user', '')}</span>
          <div class="msg-detail__who">
            <b>${U.esc(m.title)}</b>
            <span class="fz-11 t-dim">${U.esc(m.from)} · ${U.esc(m.time)}</span>
          </div>
        </div>
        <div class="msg-detail__body">${U.esc(m.content)}</div>
      </div>`;
      Modal.open({
        title: '消息详情',
        body: detailBody,
        footer: null,
        onMount() {
          if (m.read || !listEl) return;
          API.student.readMessage({ msgId: m.msgId })
            .then(() => {
              m.read = true;
              listEl.classList.add('is-read');
              const badge = listEl.querySelector('.badge');
              if (badge) badge.remove();
              updateMsgBadge(msgList.filter(x => !x.read).length);
              if (window.refreshAlertBadge) window.refreshAlertBadge();
            })
            .catch(() => {});
        }
      });
    }
  window.__studentAuthed = true;
})();
