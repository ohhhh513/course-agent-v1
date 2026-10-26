'use strict';

/* 班级管理嵌入用户管理；复用账号导入向导，删除前展示服务器返回的实际范围。 */
const AdminClasses = {
  active: false,
  records: [],
  students: [],
  selected: '',
  init() {
    const host = U.$('#adminClassesPanel');
    host.innerHTML = `
      <div class="card__head">
        <h3>班级管理</h3><span class="spacer"></span>
        <div class="search admin-class-search"><input class="input" id="classSearch" placeholder="搜索班级"></div>
        <button class="btn btn--primary btn--sm" id="classCreate" type="button">新建班级</button>
      </div>
      <div class="admin-class-layout">
        <nav class="admin-class-list" id="classList" aria-label="班级列表"></nav>
        <section class="admin-class-members" id="classMembers" aria-label="班级学生"></section>
      </div>`;
    U.$$('[data-user-panel]').forEach(button => button.addEventListener('click', () => {
      this.active = button.dataset.userPanel === 'classes';
      U.$$('[data-user-panel]').forEach(tab => {
        const selected = tab === button;
        tab.classList.toggle('is-active', selected);
        tab.setAttribute('aria-selected', String(selected));
      });
      U.$('#adminAccountsPanel').hidden = this.active;
      host.hidden = !this.active;
      if (this.active) this.load();
      else AdminUsers.load();
    }));
    let timer;
    U.$('#classSearch').addEventListener('input', () => {
      clearTimeout(timer); timer = setTimeout(() => this.load(), 220);
    });
    U.$('#classCreate').addEventListener('click', () => this.create());
    window.addEventListener('focus', () => {
      if (this.active && Router.current === 'users' && !document.querySelector('.overlay')) this.load();
    });
  },
  async load() {
    const request = this.request = (this.request || 0) + 1;
    try {
      const result = await API.admin.classes.list({ keyword: U.$('#classSearch').value.trim() });
      if (request !== this.request) return;
      this.records = result.list || [];
      if (!this.records.some(row => row.classId === this.selected)) this.selected = this.records[0]?.classId || '';
      this.paintList();
      if (this.selected) await this.loadStudents();
      else U.$('#classMembers').innerHTML = '<div class="empty"><b>暂无班级</b><p>新建班级后可导入名单，或加入已有学生。</p></div>';
    } catch (error) { Toast.error('班级加载失败', error.message); }
  },
  paintList() {
    const box = U.$('#classList');
    box.innerHTML = this.records.length ? this.records.map(row => `
      <button class="admin-class-option ${row.classId === this.selected ? 'is-active' : ''}" type="button" data-class="${U.esc(row.classId)}" aria-pressed="${row.classId === this.selected}">
        <span>${U.esc(row.name)}</span><small>${row.studentCount} 名学生</small>
      </button>`).join('') : '<p class="admin-class-empty">没有匹配的班级</p>';
    box.querySelectorAll('[data-class]').forEach(button => button.addEventListener('click', () => {
      this.selected = button.dataset.class; this.paintList(); this.loadStudents();
    }));
  },
  async loadStudents() {
    const classId = this.selected;
    const request = this.memberRequest = (this.memberRequest || 0) + 1;
    const host = U.$('#classMembers');
    host.innerHTML = '<p class="admin-class-empty">正在加载学生…</p>';
    try {
      const result = await API.admin.classes.students(classId);
      if (classId !== this.selected || request !== this.memberRequest) return;
      this.students = result.list || [];
      const row = this.records.find(item => item.classId === classId);
      if (row) row.studentCount = result.studentCount;
      this.paintList();
      host.innerHTML = `
        <div class="admin-class-toolbar">
          <div><h3>${U.esc(result.name)}</h3><span class="t-dim fz-12">${result.studentCount} 名学生</span></div>
          <span class="spacer"></span>
          <button class="btn btn--sm" type="button" id="classImport">导入学生</button>
          <button class="btn btn--sm" type="button" id="classAssign">加入已有学生</button>
          <button class="btn btn--sm btn--danger" type="button" id="classDelete">删除班级</button>
        </div>
        <div class="admin-class-selection"><span class="fz-12 t-dim" id="classPickedCount">已选 0 人</span><button class="btn btn--xs btn--danger" id="classDeleteStudents" type="button" disabled>删除选中学生</button></div>
        <div class="admin-class-table-wrap"><table class="tbl tbl--compact" id="classStudentsTable">
          <thead><tr><th><input type="checkbox" id="classPickAll" aria-label="全选本班学生"></th><th>姓名</th><th>用户名</th><th>学号</th><th>操作</th></tr></thead>
          <tbody>${this.students.length ? this.students.map(user => `<tr>
            <td><input type="checkbox" data-class-student="${U.esc(user.userId)}" aria-label="选择${U.esc(user.name)}"></td>
            <td>${U.esc(user.name)}</td><td>${U.esc(user.username)}</td><td>${U.esc(user.studentNo || '—')}</td>
            <td><button class="btn btn--xs btn--danger" type="button" data-delete-student="${U.esc(user.userId)}">删除</button></td>
          </tr>`).join('') : '<tr><td colspan="5" class="t-dim">暂无学生，可导入名单或加入已有学生。</td></tr>'}</tbody>
        </table></div>`;
      const syncSelection = () => {
        const boxes = [...host.querySelectorAll('[data-class-student]')];
        const count = boxes.filter(box => box.checked).length;
        U.$('#classPickedCount').textContent = `已选 ${count} 人`;
        U.$('#classDeleteStudents').disabled = count === 0;
        const all = U.$('#classPickAll');
        all.checked = boxes.length > 0 && count === boxes.length;
        all.indeterminate = count > 0 && count < boxes.length;
      };
      host.querySelectorAll('[data-class-student]').forEach(box => box.addEventListener('change', syncSelection));
      U.$('#classPickAll').addEventListener('change', event => {
        host.querySelectorAll('[data-class-student]').forEach(box => { box.checked = event.target.checked; }); syncSelection();
      });
      U.$('#classDeleteStudents').addEventListener('click', () => this.removeStudents(classId,
        [...host.querySelectorAll('[data-class-student]:checked')].map(box => box.dataset.classStudent)));
      host.querySelectorAll('[data-delete-student]').forEach(button => button.addEventListener('click', () => this.removeStudents(classId, [button.dataset.deleteStudent])));
      U.$('#classImport').addEventListener('click', () => AdminUsers.openImport(result, () => this.load()));
      U.$('#classAssign').addEventListener('click', () => this.assign(result));
      U.$('#classDelete').addEventListener('click', () => this.removeClass(classId));
    } catch (error) {
      if (classId === this.selected && request === this.memberRequest) host.innerHTML = `<p class="admin-class-empty t-danger">${U.esc(error.message)}</p>`;
    }
  },
  create() {
    Modal.open({ title: '新建班级', closeOnBackdrop: false,
      body: '<label class="stack"><span>班级名称</span><input class="input" id="newClassName" maxlength="64" placeholder="如：计算机 2601 班"></label>',
      footer: '<button class="btn btn--primary" id="createClassConfirm" type="button">创建</button><button class="btn" data-close>取消</button>',
      onMount: (overlay, close) => {
        overlay.querySelector('#createClassConfirm').addEventListener('click', async event => {
          const name = overlay.querySelector('#newClassName').value.trim();
          if (!name) { Toast.warn('请输入班级名称'); return; }
          event.currentTarget.disabled = true;
          try {
            const result = await API.admin.classes.create({ name });
            this.selected = result.classId; U.$('#classSearch').value = ''; close(); this.load(); Toast.ok('班级已创建');
          } catch (error) { overlay.querySelector('#createClassConfirm').disabled = false; Toast.error('创建失败', error.message); }
        });
      },
    });
  },
  async assign(classMeta) {
    try {
      const result = await API.admin.listUsers({ role: 'student' });
      const key = name => String(name || '').replace(/\s+/g, '').toLowerCase();
      const candidates = (result.list || []).filter(user => key(user.className) !== key(classMeta.name));
      const picked = new Set();
      Modal.open({ title: `加入已有学生 · ${classMeta.name}`, closeOnBackdrop: false,
        body: '<div class="stack"><p class="t-dim">选中的学生会转入此班级，已有选课关系保留。</p><input class="input" id="classAssignSearch" placeholder="搜索姓名、用户名或班级"><div class="admin-class-candidates" id="classCandidates"></div></div>',
        footer: '<span class="t-dim fz-12" id="classAssignCount">已选 0 人</span><button class="btn btn--primary" id="classAssignConfirm" type="button" disabled>加入班级</button><button class="btn" data-close>取消</button>',
        onMount: (overlay, close) => {
          const box = overlay.querySelector('#classCandidates');
          const confirm = overlay.querySelector('#classAssignConfirm');
          const paint = () => {
            const query = overlay.querySelector('#classAssignSearch').value.trim().toLowerCase();
            const shown = candidates.filter(user => `${user.name} ${user.username} ${user.className || ''}`.toLowerCase().includes(query));
            box.innerHTML = shown.length ? shown.map(user => `<label class="admin-class-candidate"><input type="checkbox" data-candidate="${U.esc(user.userId)}" ${picked.has(user.userId) ? 'checked' : ''}><span><b>${U.esc(user.name)}</b><small>${U.esc(user.username)} · ${U.esc(user.className || '未分班')}</small></span></label>`).join('') : '<p class="t-dim">没有可加入的学生。</p>';
            box.querySelectorAll('[data-candidate]').forEach(input => input.addEventListener('change', () => {
              if (input.checked) picked.add(input.dataset.candidate); else picked.delete(input.dataset.candidate);
              confirm.disabled = !picked.size; overlay.querySelector('#classAssignCount').textContent = `已选 ${picked.size} 人`;
            }));
          };
          overlay.querySelector('#classAssignSearch').addEventListener('input', paint); paint();
          confirm.addEventListener('click', async () => {
            confirm.disabled = true;
            try { await API.admin.classes.assign(classMeta.classId, [...picked]); close(); this.load(); Toast.ok('已更新学生班级'); }
            catch (error) { confirm.disabled = !picked.size; Toast.error('加入失败', error.message); }
          });
        },
      });
    } catch (error) { Toast.error('学生加载失败', error.message); }
  },
  removeStudents(classId, ids) {
    const selected = this.students.filter(user => ids.includes(user.userId));
    if (!selected.length) return;
    Modal.open({ title: '删除学生账号', closeOnBackdrop: false,
      body: `<div class="stack"><div class="callout callout--danger">将删除 ${selected.length} 名学生的账号及其在所有课程中的个人学习数据，删除后不能登录，教师端也不再显示。课程内容保留。</div><div class="admin-class-delete-list">${selected.map(user => `<p>${U.esc(user.name)} · ${U.esc(user.username)}</p>`).join('')}</div></div>`,
      footer: '<button class="btn btn--danger" id="classStudentsDeleteConfirm" type="button">确认删除学生</button><button class="btn" data-close>取消</button>',
      onMount: (overlay, close) => {
        const button = overlay.querySelector('#classStudentsDeleteConfirm');
        button.addEventListener('click', async () => {
          button.disabled = true;
          try { await API.admin.classes.deleteStudents(classId, ids); close(); this.load(); Toast.ok('学生账号已删除'); }
          catch (error) { button.disabled = false; Toast.error('删除失败', error.message); }
        });
      },
    });
  },
  async removeClass(classId) {
    try {
      const preview = await API.admin.classes.deletePreview(classId);
      Modal.open({ title: `删除班级 · ${preview.name}`, closeOnBackdrop: false,
        body: `<div class="stack"><div class="callout callout--danger">将删除此班级及全部 <b>${preview.studentCount}</b> 名学生账号，并清理这些学生在所有课程中的个人学习数据。教师端将不再显示这些学生。课程、教材和题库保留。</div><p class="fz-12 t-dim">涉及课程：${U.esc(preview.courses.map(course => course.name).join('、') || '无选课关系')}</p><div class="admin-class-delete-list">${preview.students.map(user => `<p>${U.esc(user.name)} · ${U.esc(user.username)}</p>`).join('') || '<p>此班级没有学生。</p>'}</div></div>`,
        footer: `<button class="btn btn--danger" id="classDeleteConfirm" type="button">删除班级及 ${preview.studentCount} 名学生</button><button class="btn" data-close>取消</button>`,
        onMount: (overlay, close) => {
          const button = overlay.querySelector('#classDeleteConfirm');
          button.addEventListener('click', async () => {
            button.disabled = true;
            try { await API.admin.classes.remove(classId, preview.revision); close(); this.selected = ''; this.load(); Toast.ok('班级及对应学生已删除'); }
            catch (error) {
              button.disabled = false; Toast.error('删除失败', error.message);
              if (error.status === 409 || error.status === 404) { close(); this.load(); }
            }
          });
        },
      });
    } catch (error) { Toast.error('无法预览删除范围', error.message); }
  },
};
