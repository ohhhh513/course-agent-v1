'use strict';

/* 教师端课程消息推送：复用课程学生列表与现有教师私信接口。 */
(function () {
  const trigger = U.$('#studentMessagePushBtn');
  if (!trigger) return;

  trigger.innerHTML = `${icon('message')}<span>给学生发消息</span>`;
  trigger.title = '给当前课程学生推送消息';
  trigger.setAttribute('aria-label', '给学生推送信息');
  trigger.addEventListener('click', openComposer);

  const PAGE_SIZE = 100;
  const SEND_CONCURRENCY = 4;

  async function getCourseStudents() {
    const first = await API.teacher.students({ page: 1, size: PAGE_SIZE });
    const rows = Array.isArray(first && first.list) ? first.list.slice() : [];
    const total = Math.max(rows.length, Number(first && first.total) || 0);
    const pages = Math.ceil(total / PAGE_SIZE);
    if (pages > 1) {
      const rest = await Promise.all(Array.from({ length: pages - 1 }, (_, i) =>
        API.teacher.students({ page: i + 2, size: PAGE_SIZE })
      ));
      rest.forEach(result => {
        if (Array.isArray(result && result.list)) rows.push(...result.list);
      });
    }
    const seen = new Set();
    return rows.filter(student => {
      const id = String(student && student.userId || '');
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }

  function openComposer() {
    const courseId = String(API.config.activeCourseId || '');
    if (!courseId) {
      Toast.warn('请先选择课程', '推送范围为当前课程的学生');
      return;
    }

    const courseSel = U.$('#courseSel');
    const courseName = courseSel && courseSel.selectedOptions[0]
      ? courseSel.selectedOptions[0].textContent
      : '当前课程';
    let students = [];
    let selected = new Set();
    let mode = 'selected';
    let loading = true;
    let sending = false;

    const modal = Modal.open({
      title: '给学生推送信息',
      size: 'wide',
      closeOnBackdrop: false,
      body: `
        <div class="teacher-message-push">
          <div class="teacher-message-push__course">
            <span class="fz-12 t-dim">推送课程</span>
            <b>${U.esc(courseName)}</b>
            <span class="teacher-message-push__course-count" id="teacherMessageStudentCount">正在加载学生…</span>
          </div>
          <div class="teacher-message-push__modes" role="group" aria-label="选择推送范围">
            <button type="button" class="btn btn--sm is-active" data-recipient-mode="selected" aria-pressed="true">选择学生</button>
            <button type="button" class="btn btn--sm" data-recipient-mode="all" aria-pressed="false">全员通知</button>
          </div>
          <section class="teacher-message-push__recipients" id="teacherMessageRecipients">
            <div class="teacher-message-push__list-tools">
              <label class="search teacher-message-push__search">${icon('search2')}<input class="input" id="teacherMessageSearch" type="search" placeholder="搜索学生姓名或学号" autocomplete="off"></label>
              <label class="teacher-message-push__select-visible"><input type="checkbox" id="teacherMessageSelectVisible" disabled> 选择当前列表</label>
            </div>
            <div class="teacher-message-push__list" id="teacherMessageStudentList" aria-live="polite">
              <div class="teacher-message-push__empty">正在加载本课程学生…</div>
            </div>
            <div class="teacher-message-push__selection" id="teacherMessageSelection">已选择 0 名学生</div>
          </section>
          <div class="teacher-message-push__compose">
            <label for="teacherMessageContent"><b>推送内容</b></label>
            <textarea class="input" id="teacherMessageContent" rows="5" maxlength="4000" placeholder="输入要发送给学生的信息…"></textarea>
            <div class="teacher-message-push__hint">消息会显示在学生端的消息列表中。</div>
          </div>
          <div class="teacher-message-push__feedback" id="teacherMessageFeedback" role="status" hidden></div>
        </div>`,
      footer: `<button class="btn" type="button" data-close>取消</button><button class="btn btn--primary" type="button" id="teacherMessageSend" disabled>发送信息</button>`,
      onMount(overlay) {
        const listEl = U.$('#teacherMessageStudentList', overlay);
        const searchEl = U.$('#teacherMessageSearch', overlay);
        const selectVisibleEl = U.$('#teacherMessageSelectVisible', overlay);
        const selectionEl = U.$('#teacherMessageSelection', overlay);
        const countEl = U.$('#teacherMessageStudentCount', overlay);
        const recipientsEl = U.$('#teacherMessageRecipients', overlay);
        const contentEl = U.$('#teacherMessageContent', overlay);
        const sendEl = U.$('#teacherMessageSend', overlay);
        const feedbackEl = U.$('#teacherMessageFeedback', overlay);
        const modeButtons = U.$$('[data-recipient-mode]', overlay);

        function visibleStudents() {
          const keyword = String(searchEl.value || '').trim().toLocaleLowerCase();
          if (!keyword) return students;
          return students.filter(student =>
            `${student.name || ''} ${student.no || ''}`.toLocaleLowerCase().includes(keyword)
          );
        }

        function updateSendButton() {
          const recipientCount = mode === 'all' ? students.length : selected.size;
          sendEl.disabled = loading || sending || !String(contentEl.value || '').trim() || recipientCount === 0;
          sendEl.textContent = sending
            ? `发送中…`
            : mode === 'all'
              ? `发送给全课程学生（${students.length}）`
              : `发送信息（${selected.size}）`;
        }

        function updateRecipientState() {
          const visible = visibleStudents();
          const everyVisibleSelected = visible.length > 0 && visible.every(s => selected.has(String(s.userId)));
          selectVisibleEl.checked = everyVisibleSelected;
          selectVisibleEl.disabled = loading || sending || visible.length === 0 || mode === 'all';
          selectionEl.textContent = mode === 'all'
            ? `将通知本课程全部 ${students.length} 名学生`
            : `已选择 ${selected.size} 名学生`;
          countEl.textContent = loading ? '正在加载学生…' : `共 ${students.length} 名学生`;
          recipientsEl.hidden = mode === 'all';
          updateSendButton();
        }

        function renderStudents() {
          const visible = visibleStudents();
          if (!students.length && !loading) {
            listEl.innerHTML = '<div class="teacher-message-push__empty">当前课程还没有学生</div>';
          } else if (!visible.length && !loading) {
            listEl.innerHTML = '<div class="teacher-message-push__empty">没有匹配的学生</div>';
          } else if (!loading) {
            listEl.innerHTML = visible.map(student => {
              const id = String(student.userId);
              return `<label class="teacher-message-push__student">
                <input type="checkbox" data-student-id="${U.esc(id)}"${selected.has(id) ? ' checked' : ''}>
                <span class="teacher-message-push__avatar">${U.esc(Auth.defaultAvatarText(student.name))}</span>
                <span class="teacher-message-push__student-name">${U.esc(student.name || id)}</span>
                <span class="teacher-message-push__student-no">${student.no ? `学号 ${U.esc(student.no)}` : ''}</span>
              </label>`;
            }).join('');
          }

          updateRecipientState();
        }

        function showFeedback(message, type) {
          feedbackEl.hidden = !message;
          feedbackEl.className = `teacher-message-push__feedback${type ? ` is-${type}` : ''}`;
          feedbackEl.textContent = message || '';
        }

        modeButtons.forEach(button => button.addEventListener('click', () => {
          if (sending) return;
          mode = button.dataset.recipientMode;
          modeButtons.forEach(item => {
            const active = item === button;
            item.classList.toggle('is-active', active);
            item.setAttribute('aria-pressed', String(active));
          });
          showFeedback('', '');
          renderStudents();
        }));

        searchEl.addEventListener('input', renderStudents);
        listEl.addEventListener('change', event => {
          const checkbox = event.target.closest('[data-student-id]');
          if (!checkbox) return;
          const id = checkbox.dataset.studentId;
          if (checkbox.checked) selected.add(id);
          else selected.delete(id);
          updateRecipientState();
        });
        selectVisibleEl.addEventListener('change', () => {
          const visible = visibleStudents();
          visible.forEach(student => {
            const id = String(student.userId);
            if (selectVisibleEl.checked) selected.add(id);
            else selected.delete(id);
          });
          U.$$('[data-student-id]', listEl).forEach(checkbox => {
            checkbox.checked = selected.has(checkbox.dataset.studentId);
          });
          updateRecipientState();
        });
        contentEl.addEventListener('input', updateSendButton);

        sendEl.addEventListener('click', async () => {
          const content = String(contentEl.value || '').trim();
          const targets = mode === 'all'
            ? students.slice()
            : students.filter(student => selected.has(String(student.userId)));
          if (!content || !targets.length || sending) return;
          if (String(API.config.activeCourseId || '') !== courseId) {
            showFeedback('课程已切换，请关闭窗口后重新打开。', 'error');
            return;
          }

          sending = true;
          showFeedback('', '');
          renderStudents();
          let sent = 0;
          const failures = [];
          for (let start = 0; start < targets.length; start += SEND_CONCURRENCY) {
            if (String(API.config.activeCourseId || '') !== courseId) {
              targets.slice(start).forEach(student => failures.push({ student, message: '课程已切换' }));
              break;
            }
            const batch = targets.slice(start, start + SEND_CONCURRENCY);
            const results = await Promise.all(batch.map(async student => {
              try {
                await API.teacher.sendMessage({ userId: student.userId, content });
                return { student, ok: true };
              } catch (error) {
                return { student, ok: false, message: error && error.message || '发送失败' };
              }
            }));
            results.forEach(result => {
              if (result.ok) sent += 1;
              else failures.push({ student: result.student, message: result.message });
            });
            sendEl.textContent = `发送中…（${Math.min(start + batch.length, targets.length)}/${targets.length}）`;
          }
          sending = false;

          if (!failures.length) {
            modal.close();
            Toast.ok('推送完成', `已发送给 ${sent} 名学生`);
            return;
          }

          selected = new Set(failures.map(item => String(item.student.userId)));
          mode = 'selected';
          modeButtons.forEach(button => {
            const active = button.dataset.recipientMode === mode;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
          });
          renderStudents();
          const names = failures.slice(0, 4).map(item => item.student.name || item.student.userId).join('、');
          const extra = failures.length > 4 ? `等 ${failures.length} 人` : names;
          showFeedback(`已发送 ${sent} 人，${failures.length} 人未成功${extra ? `：${extra}` : ''}。名单已切换为未成功学生，可检查后重试。`, 'error');
          if (sent) Toast.warn('部分推送未完成', `成功 ${sent} 人，未成功 ${failures.length} 人`);
        });

        getCourseStudents().then(result => {
          if (!overlay.isConnected) return;
          if (String(API.config.activeCourseId || '') !== courseId) {
            loading = false;
            renderStudents();
            listEl.innerHTML = '<div class="teacher-message-push__empty">课程已切换，请关闭窗口后重新打开</div>';
            countEl.textContent = '课程已变化';
            return;
          }
          students = result;
          loading = false;
          renderStudents();
        }).catch(error => {
          if (!overlay.isConnected) return;
          loading = false;
          renderStudents();
          listEl.innerHTML = `<div class="teacher-message-push__empty">学生名单加载失败：${U.esc(error && error.message || '请稍后重试')}</div>`;
          countEl.textContent = '加载失败';
        });
      },
    });
  }
})();
