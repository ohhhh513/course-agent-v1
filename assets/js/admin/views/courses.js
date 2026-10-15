'use strict';

/* ================================================================
   视图 · 课程管理（管理员端）
   课程的新建 / 编辑 / 删除空课，以及按班级或选课名单把学生绑进课程。
   ================================================================ */

const AdminCourses = {
  rows: [],

  filtered() {
    const key = (U.$('#fCourse').value || '').trim().toLowerCase();
    if (!key) return AdminCourses.rows;
    return AdminCourses.rows.filter(c =>
      [c.name, c.code, c.classNo, c.term, c.teacher, c.ownerUsername, c.courseId, c.inviteCode]
        .some(v => String(v || '').toLowerCase().indexOf(key) >= 0));
  },

  load() {
    return API.admin.listCourses().then(r => {
      AdminCourses.rows = (r && r.list) || [];
      AdminCourses.render();
    }).catch(err => {
      U.$('#courseTable tbody').innerHTML =
        `<tr><td colspan="5" class="t-danger">${U.esc(err.message || '加载失败')}</td></tr>`;
    });
  },

  render() {
    const list = AdminCourses.filtered();
    const tb = U.$('#courseTable tbody');
    if (!list.length) {
      tb.innerHTML = `<tr><td colspan="5" class="t-dim" style="padding:20px;text-align:center">${
        AdminCourses.rows.length ? '没有匹配的课程' : '还没有课程。点右上角「新建课程」，并指定一位教师作为负责人。'
      }</td></tr>`;
      return;
    }
    tb.innerHTML = list.map(c => {
      const bits = [c.code, c.classNo || '未填教学班', c.term].filter(Boolean);
      const content = (c.chapters || c.knowledgePoints || c.resources || c.questions)
        ? `${c.chapters || 0} 章 · ${c.knowledgePoints || 0} 知识点<br>${c.resources || 0} 资源 · ${c.questions || 0} 题`
        : '空课程';
      return `<tr>
        <td>
          <b>${U.esc(c.name)}</b>
          <div class="fz-12 t-dim">${U.esc(bits.join(' · '))}</div>
          <div class="mono fz-11 t-dim">${U.esc(c.courseId)}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
            <button class="btn btn--xs" type="button" data-act="members" data-course="${U.esc(c.courseId)}">学生</button>
            <button class="btn btn--xs" type="button" data-act="edit" data-course="${U.esc(c.courseId)}">编辑</button>
            <button class="btn btn--xs btn--danger" type="button" data-act="del" data-course="${U.esc(c.courseId)}">删除</button>
          </div>
        </td>
        <td style="white-space:nowrap">${U.esc(c.teacher || '—')}<div class="mono fz-11 t-dim">${U.esc(c.ownerUsername || '')}</div></td>
        <td style="white-space:nowrap">学生 ${c.studentCount || 0}<div class="t-dim fz-12">教师 ${c.teacherCount || 0}</div></td>
        <td class="fz-12">${content}</td>
        <td style="white-space:nowrap"><span class="mono fz-11">${U.esc(c.inviteCode || '—')}</span>
          ${c.inviteCode ? `<div style="margin-top:6px"><button class="btn btn--xs" type="button" data-copy="${U.esc(c.inviteCode)}">复制</button></div>` : ''}</td>
      </tr>`;
    }).join('');
  },

  find(courseId) {
    return AdminCourses.rows.find(c => c.courseId === courseId) || null;
  },

  /** 近期学年学期，并带上库里已经用过、但不在这套名称里的学期。 */
  termChoices(current) {
    const now = new Date();
    const month = now.getMonth() + 1;
    let start = now.getFullYear();
    if (month < 8) start -= 1;
    const list = [];
    for (let year = start - 1; year <= start + 1; year += 1) {
      list.push(`${year}-${year + 1} 学年 第一学期`);
      list.push(`${year}-${year + 1} 学年 第二学期`);
    }
    AdminCourses.rows.forEach(c => {
      const term = (c.term || '').trim();
      if (term && list.indexOf(term) < 0) list.push(term);
    });
    const chosen = (current || '').trim();
    if (chosen && list.indexOf(chosen) < 0) list.unshift(chosen);
    return list;
  },

  currentTerm() {
    const now = new Date();
    const month = now.getMonth() + 1;
    let start = now.getFullYear();
    let half = '第一学期';
    if (month < 8) {
      start -= 1;
      if (month > 1) half = '第二学期';
    }
    return `${start}-${start + 1} 学年 ${half}`;
  },

  classChoices(students, current) {
    const list = [];
    const add = (name) => {
      const text = (name || '').trim();
      if (text && list.indexOf(text) < 0) list.push(text);
    };
    (students || []).forEach(s => add(s.className));
    AdminCourses.rows.forEach(c => add(c.classNo));
    add(current);
    list.sort((a, b) => a.localeCompare(b, 'zh'));
    return list;
  },

  openForm(course) {
    Promise.all([
      API.admin.listUsers({ role: 'teacher' }),
      API.admin.listUsers({ role: 'student' }),
    ]).then(([teachersRes, studentsRes]) => {
      const teachers = (teachersRes && teachersRes.list) || [];
      const students = (studentsRes && studentsRes.list) || [];
      if (!teachers.length) {
        Toast.warn('还没有教师账号', '请先在账号管理里新建一位教师，再创建课程。');
        return;
      }
      const isEdit = !!course;
      const options = teachers.map(t =>
        `<option value="${U.esc(t.userId)}"${course && course.ownerId === t.userId ? ' selected' : ''}>${U.esc(t.name)}（${U.esc(t.username)}）</option>`
      ).join('');
      const classValues = AdminCourses.classChoices(students, course && course.classNo);
      const selectedClass = (course && course.classNo) || '';
      const classOptions = [`<option value="">不指定</option>`].concat(classValues.map(name =>
        `<option value="${U.esc(name)}"${name === selectedClass ? ' selected' : ''}>${U.esc(name)}</option>`
      )).join('');
      const selectedTerm = isEdit ? ((course && course.term) || '') : AdminCourses.currentTerm();
      const termOptions = [`<option value="">不指定</option>`].concat(AdminCourses.termChoices(selectedTerm).map(term =>
        `<option value="${U.esc(term)}"${term === selectedTerm ? ' selected' : ''}>${U.esc(term)}</option>`
      )).join('');
      Modal.open({
        title: isEdit ? '编辑课程' : '新建课程',
        closeOnBackdrop: false,
        body: `
          <form class="stack" style="gap:12px" id="courseForm">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">课程名称</span>
              <input class="input" id="cName" value="${U.esc(course && course.name || '')}" placeholder="如：数据结构与算法"></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">课程代码（可选）</span>
              <input class="input" id="cCode" value="${U.esc(course && course.code || '')}" placeholder="如：CS20301"></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">教学班号（可选）</span>
              <select class="select" id="cClass">${classOptions}</select>
              <span class="fz-12 t-dim">来自学生账号上的班级。与这里一致时，可以一键把该班学生绑进课程。</span>
            </label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学期（可选）</span>
              <select class="select" id="cTerm">${termOptions}</select>
            </label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">课程负责人</span>
              <select class="select" id="cTeacher">${options}</select>
              <span class="fz-12 t-dim">负责人会成为这门课的授课教师，并在教师端看到它。更换负责人不会把原教师移出课程。</span>
            </label>
          </form>`,
        footer: `<button class="btn btn--primary" id="cGo" type="button">${isEdit ? '保存' : '创建'}</button><button class="btn" data-close>取消</button>`,
        onMount(ov, close) {
          U.$('#cGo', ov).addEventListener('click', () => {
            const payload = {
              name: U.$('#cName', ov).value.trim(),
              code: U.$('#cCode', ov).value.trim(),
              classNo: U.$('#cClass', ov).value.trim(),
              term: U.$('#cTerm', ov).value.trim(),
              teacherUserId: U.$('#cTeacher', ov).value,
            };
            if (!payload.name) {
              Toast.warn('请填写课程名称');
              return;
            }
            if (!payload.teacherUserId) {
              Toast.warn('请选择课程负责人');
              return;
            }
            const btn = U.$('#cGo', ov);
            btn.disabled = true;
            const req = isEdit
              ? API.admin.updateCourse(course.courseId, payload)
              : API.admin.createCourse(payload);
            req.then(saved => {
              close();
              Toast.ok(isEdit ? '课程已保存' : '课程已创建', (saved.name || payload.name) + (saved.inviteCode ? ' · 邀请码 ' + saved.inviteCode : ''));
              AdminCourses.load();
            }).catch(err => {
              btn.disabled = false;
              Toast.error(isEdit ? '保存失败' : '创建失败', (err && err.message) || '');
            });
          });
        }
      });
    }).catch(err => Toast.error('教师列表加载失败', (err && err.message) || ''));
  },

  confirmDelete(course) {
    const blocked = (course.chapters || 0) + (course.knowledgePoints || 0) + (course.resources || 0) + (course.questions || 0);
    Modal.open({
      title: '删除课程',
      closeOnBackdrop: false,
      body: `
        <div class="stack" style="gap:12px">
          <div class="callout ${blocked ? 'callout--warn' : 'callout--danger'}">${icon('alert')}
            <div>${blocked
              ? '这门课已经有章节、资源或题目。系统会拒绝删除，避免清掉教师和学生正在使用的内容。'
              : '只删除还没有教学内容的空课程，并同时移出全部成员。已有的练习、资源和题库不会被这步清掉；若库里仍有学习记录，删除会被拒绝。'}
            </div>
          </div>
          <label class="stack" style="gap:4px">
            <span class="fz-12 t-dim">请输入课程名称「${U.esc(course.name)}」以确认</span>
            <input class="input" id="cDelName" autocomplete="off">
          </label>
        </div>`,
      footer: `<button class="btn btn--danger" id="cDelGo" type="button">删除</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#cDelGo', ov).addEventListener('click', () => {
          if (U.$('#cDelName', ov).value.trim() !== course.name) {
            Toast.warn('课程名称不一致');
            return;
          }
          const btn = U.$('#cDelGo', ov);
          btn.disabled = true;
          API.admin.deleteCourse(course.courseId).then(() => {
            close();
            Toast.ok('课程已删除', course.name);
            AdminCourses.load();
          }).catch(err => {
            btn.disabled = false;
            Toast.error('不能删除', (err && err.message) || '');
          });
        });
      }
    });
  },

  openMembers(course) {
    let tab = 'class';
    let classes = [];
    let members = [];
    let preview = null;
    let rosterFile = null;
    let classNo = course.classNo || '';

    Modal.open({
      title: '课程学生 · ' + course.name,
      closeOnBackdrop: false,
      size: 'full',
      body: `
        <div class="stack" style="gap:14px">
          <div class="fz-12 t-dim" id="courseBindMeta"></div>
          <div class="tabs" id="courseBindTabs">
            <button type="button" data-tab="class">按班级绑定</button>
            <button type="button" data-tab="roster">选课名单</button>
            <button type="button" data-tab="members">当前成员</button>
          </div>
          <div id="courseBindPane"></div>
        </div>`,
      footer: `<button class="btn" data-close type="button">关闭</button>`,
      onMount(ov) {
        const meta = () => {
          const latest = AdminCourses.find(course.courseId) || course;
          classNo = latest.classNo || '';
          U.$('#courseBindMeta', ov).textContent =
            `${latest.name} · 学生 ${latest.studentCount || 0} 人 · 教师 ${latest.teacherCount || 0} 人` +
            (classNo ? ` · 教学班 ${classNo}` : ' · 未填教学班号') +
            (latest.inviteCode ? ` · 邀请码 ${latest.inviteCode}` : '');
        };
        const setTab = () => {
          U.$$('#courseBindTabs button', ov).forEach(btn => {
            btn.classList.toggle('is-active', btn.dataset.tab === tab);
          });
        };
        const render = () => {
          meta();
          setTab();
          const pane = U.$('#courseBindPane', ov);
          if (tab === 'class') pane.innerHTML = AdminCourses.classPane(classes, classNo);
          else if (tab === 'roster') pane.innerHTML = AdminCourses.rosterPane(preview, rosterFile);
          else pane.innerHTML = AdminCourses.membersPane(members);
        };
        const reload = () => Promise.all([
          API.admin.courseClasses(course.courseId),
          API.admin.courseMembers(course.courseId),
          AdminCourses.load(),
        ]).then(([c, m]) => {
          classes = (c && c.list) || [];
          classNo = (c && c.classNo) || classNo;
          members = (m && m.list) || [];
          render();
        }).catch(err => {
          U.$('#courseBindPane', ov).innerHTML = `<div class="t-danger">${U.esc(err.message || '加载失败')}</div>`;
        });

        ov.addEventListener('click', (e) => {
          const tabBtn = e.target.closest('[data-tab]');
          if (tabBtn && ov.contains(tabBtn)) {
            tab = tabBtn.dataset.tab;
            render();
            return;
          }
          const suggestedBtn = e.target.closest('#bindSuggested');
          if (suggestedBtn) {
            const keys = classes.filter(c => c.matchesCourseClass).map(c => c.classKey);
            AdminCourses.runClassBind(course.courseId, keys, reload, false, suggestedBtn);
            return;
          }
          const classBtn = e.target.closest('#bindChecked') || e.target.closest('#unbindChecked');
          if (classBtn) {
            const keys = U.$$('[data-class-key]', ov).filter(el => el.checked).map(el => el.dataset.classKey);
            const leaving = classBtn.id === 'unbindChecked';
            AdminCourses.runClassBind(course.courseId, keys, reload, leaving, classBtn);
            return;
          }
          if (e.target.closest('#rosterTpl')) {
            API.admin.rosterTemplate().then(({ blob, filename }) => {
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = filename || '选课名单模板.xlsx';
              document.body.appendChild(a);
              a.click();
              a.remove();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
            }).catch(err => Toast.error('模板下载失败', (err && err.message) || ''));
            return;
          }
          if (e.target.closest('#rosterPick')) {
            const input = U.$('#rosterFile', ov);
            if (input) input.click();
            return;
          }
          if (e.target.closest('#rosterGo')) {
            if (!rosterFile || !preview || !preview.ready) {
              Toast.warn('没有可绑定的学生', '请先上传名单并确认预览');
              return;
            }
            const btn = U.$('#rosterGo', ov);
            btn.disabled = true;
            const fd = new FormData();
            fd.append('file', rosterFile, rosterFile.name);
            API.admin.rosterCommit(course.courseId, fd).then(res => {
              Toast.ok('名单已绑定', `新绑定 ${res.bound || 0} 人` +
                (res.already ? ` · 已在课程 ${res.already}` : '') +
                (res.skipped ? ` · 跳过 ${res.skipped}` : ''));
              preview = null;
              rosterFile = null;
              reload();
            }).catch(err => {
              btn.disabled = false;
              Toast.error('绑定失败', (err && err.message) || '');
            });
            return;
          }
          const kick = e.target.closest('[data-unbind]');
          if (kick) {
            const userId = kick.dataset.unbind;
            const who = members.find(m => m.userId === userId);
            kick.disabled = true;
            API.admin.unbindMember(course.courseId, userId).then(() => {
              Toast.ok('已移出课程', who ? who.name : '');
              reload();
            }).catch(err => {
              kick.disabled = false;
              Toast.error('移出失败', (err && err.message) || '');
            });
          }
        });

        ov.addEventListener('change', (e) => {
          if (e.target.id !== 'rosterFile') return;
          const file = e.target.files && e.target.files[0];
          if (!file) return;
          rosterFile = file;
          preview = null;
          render();
          const fd = new FormData();
          fd.append('file', file, file.name);
          API.admin.rosterPreview(course.courseId, fd).then(res => {
            preview = res;
            render();
          }).catch(err => {
            rosterFile = null;
            preview = null;
            render();
            Toast.error('名单无法解析', (err && err.message) || '');
          });
        });

        reload();
      }
    });
  },

  runClassBind(courseId, keys, reload, leaving, btn) {
    if (!keys.length) {
      Toast.warn(leaving ? '请先勾选要移出的班级' : '请先勾选要绑定的班级');
      return;
    }
    if (btn) btn.disabled = true;
    const req = leaving
      ? API.admin.unbindClasses(courseId, { classKeys: keys })
      : API.admin.bindClasses(courseId, { classKeys: keys });
    req.then(res => {
      if (leaving) {
        Toast.ok('已按班级移出', `移出 ${res.removed || 0} 人` + (res.keptOwner ? ' · 负责人保留' : ''));
      } else {
        Toast.ok('已按班级绑定', `新绑定 ${res.bound || 0} 人` + (res.already ? ` · 已在课程 ${res.already}` : ''));
      }
      reload();
    }).catch(err => {
      if (btn) btn.disabled = false;
      Toast.error(leaving ? '移出失败' : '绑定失败', (err && err.message) || '');
    });
  },

  classPane(classes, classNo) {
    const suggested = classes.filter(c => c.matchesCourseClass);
    const suggestBtn = suggested.length
      ? `<button class="btn btn--primary btn--sm" id="bindSuggested" type="button">一键绑定教学班（${suggested.length} 个班）</button>`
      : '';
    const hint = classNo
      ? (suggested.length
        ? `教学班号「${U.esc(classNo)}」已对上下面标出的班级，可直接一键绑定。`
        : `教学班号「${U.esc(classNo)}」没有对上现有学生班级。请勾选班级，或改用选课名单。`)
      : '课程还没填教学班号。可以勾选下面的班级绑定，也可以先去编辑课程填上教学班号。';
    if (!classes.length) {
      return `<div class="callout callout--info">${icon('info')}<div>还没有学生填写班级。请先在账号管理里给学生填写班级，或改用「选课名单」。</div></div>`;
    }
    const rows = classes.map(c => `<tr>
      <td><input type="checkbox" data-class-key="${U.esc(c.classKey)}"></td>
      <td>${U.esc(c.className)}${c.matchesCourseClass ? ' <span class="badge badge--brand">教学班</span>' : ''}</td>
      <td>${c.studentCount || 0}</td>
      <td>${c.boundCount || 0}</td>
    </tr>`).join('');
    return `
      <div class="stack" style="gap:12px">
        <div class="callout callout--info">${icon('info')}<div>${hint}绑定后学生登录就能在自己的课程列表里看到这门课；课程已有知识点时，会同时补上该生的学习路径。移出只取消选课，不删除已有练习记录。</div></div>
        <div class="row" style="gap:8px;flex-wrap:wrap">
          ${suggestBtn}
          <button class="btn btn--sm" id="bindChecked" type="button">绑定勾选的班级</button>
          <button class="btn btn--sm" id="unbindChecked" type="button">移出勾选的班级</button>
        </div>
        <div style="max-height:46vh;overflow:auto;border:1px solid var(--border-soft);border-radius:var(--r-sm)">
          <table class="tbl">
            <thead><tr><th style="width:36px"></th><th>班级</th><th>学生</th><th>已在本课</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  },

  rosterPane(preview, file) {
    const statusName = { ready: '可绑定', already: '已在课程', skipped: '跳过' };
    const statusBadge = { ready: 'badge--ok', already: 'badge--outline', skipped: 'badge--warn' };
    let result = '';
    if (preview) {
      const shown = (preview.rows || []).slice(0, 80);
      const more = (preview.rows || []).length - shown.length;
      result = `
        <div class="fz-12">共 ${preview.total || 0} 行 · 可绑定 ${preview.ready || 0} · 已在课程 ${preview.already || 0} · 跳过 ${preview.skipped || 0}</div>
        <div style="max-height:40vh;overflow:auto;border:1px solid var(--border-soft);border-radius:var(--r-sm)">
          <table class="tbl">
            <thead><tr><th>#</th><th>用户名</th><th>姓名</th><th>学号</th><th>班级</th><th>结果</th></tr></thead>
            <tbody>${shown.map(row => `<tr>
              <td class="mono">${row.rowIndex}</td>
              <td class="mono fz-11">${U.esc(row.username || '—')}</td>
              <td>${U.esc(row.name || '—')}</td>
              <td class="mono fz-11">${U.esc(row.studentNo || '—')}</td>
              <td>${U.esc(row.className || '—')}</td>
              <td><span class="badge ${statusBadge[row.status] || 'badge--outline'}">${statusName[row.status] || row.status}</span>
                ${row.reason ? `<div class="fz-12 t-dim">${U.esc(row.reason)}</div>` : ''}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
        ${more > 0 ? `<div class="fz-12 t-dim">还有 ${more} 行未展开。确认绑定时会处理全部可绑定的行。</div>` : ''}`;
    }
    return `
      <div class="stack" style="gap:12px">
        <div class="callout callout--info">${icon('info')}<div>上传选课名单（.xlsx / .docx / .csv / .txt）。表头用「学号、姓名、用户名」，学号或用户名至少有一列。只写姓名时，必须能唯一对应到一名学生。已在课程里的学生会跳过，不会重复加入。</div></div>
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn btn--sm" id="rosterTpl" type="button">下载模板</button>
          <button class="btn btn--sm" id="rosterPick" type="button">选择名单</button>
          <input id="rosterFile" type="file" accept=".xlsx,.docx,.csv,.txt" hidden>
          <span class="fz-12 t-dim">${file ? U.esc(file.name) : '尚未选择文件'}</span>
          <span class="spacer"></span>
          <button class="btn btn--primary btn--sm" id="rosterGo" type="button" ${preview && preview.ready ? '' : 'disabled'}>确认绑定</button>
        </div>
        ${result}
      </div>`;
  },

  membersPane(members) {
    if (!members.length) {
      return `<div class="t-dim" style="padding:12px 0">这门课还没有成员。</div>`;
    }
    const roleName = { teacher: '教师', student: '学生' };
    return `
      <div style="max-height:52vh;overflow:auto;border:1px solid var(--border-soft);border-radius:var(--r-sm)">
        <table class="tbl">
          <thead><tr><th>用户名</th><th>姓名</th><th>角色</th><th>班级 / 学号</th><th>操作</th></tr></thead>
          <tbody>${members.map(m => `<tr>
            <td class="mono fz-11">${U.esc(m.username)}</td>
            <td>${U.esc(m.name)}</td>
            <td><span class="badge ${m.role === 'teacher' ? 'badge--brand' : 'badge--outline'}">${roleName[m.role] || U.esc(m.role)}</span>
              ${m.isOwner ? '<span class="badge badge--ok">负责人</span>' : ''}</td>
            <td>${U.esc(m.className || '—')}<div class="mono fz-11 t-dim">${U.esc(m.studentNo || '')}</div></td>
            <td>${m.isOwner ? '<span class="t-dim fz-12">不可移出</span>' : `<button class="btn btn--xs" type="button" data-unbind="${U.esc(m.userId)}">移出</button>`}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  },
};

Router.register('courses', {
  title: '课程管理',
  mount() {
    U.$('#btnCourseCreate').addEventListener('click', () => AdminCourses.openForm(null));
    let timer;
    U.$('#fCourse').addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => AdminCourses.render(), 200);
    });
    U.$('#courseTable').addEventListener('click', (e) => {
      const copy = e.target.closest('[data-copy]');
      if (copy) {
        const text = copy.dataset.copy || '';
        const done = () => Toast.ok('邀请码已复制', text);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(() => Toast.warn('复制失败', text));
        } else {
          Toast.warn('请手动复制', text);
        }
        return;
      }
      const btn = e.target.closest('[data-act]');
      if (!btn) return;
      const course = AdminCourses.find(btn.dataset.course);
      if (!course) return;
      if (btn.dataset.act === 'edit') AdminCourses.openForm(course);
      else if (btn.dataset.act === 'del') AdminCourses.confirmDelete(course);
      else if (btn.dataset.act === 'members') AdminCourses.openMembers(course);
    });
    AdminCourses.load();
  },
});
