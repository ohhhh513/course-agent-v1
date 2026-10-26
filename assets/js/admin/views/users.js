'use strict';

/* ================================================================
   视图 · 账号管理（管理员端）
   由原 admin.html 单页内联脚本整体迁入，交互与行为保持不变；
   挂到 Router 的 users 视图（Router 的 mount 只执行一次，
   切走再切回不会重复绑定事件）。
   ================================================================ */

const AdminUsers = {
  refreshProfiles() {
    if (Router.current === 'users' && !document.querySelector('.overlay') && !this.pickedIds().length) this.load();
  },
  load() {
    const request = this._request = (this._request || 0) + 1;
    const role = U.$('#fRole').value;
    const keyword = U.$('#fKey').value.trim();
    API.admin.listUsers({ role, keyword }).then(r => {
      if (request !== this._request) return;
      const list = (r && r.list) || [];
      const tb = U.$('#userTable tbody');
      if (!list.length) {
        tb.innerHTML = `<tr><td colspan="7" class="t-dim" style="padding:20px;text-align:center">暂无账号，点右上角「新建账号」</td></tr>`;
        AdminUsers.syncPickAll();
        return;
      }
      tb.innerHTML = list.map(u => `
        <tr data-uid="${U.esc(u.userId)}" data-user="${U.esc(u.username)}">
          <td><input type="checkbox" data-pick="${U.esc(u.userId)}" title="勾选后可批量删除"></td>
          <td><b>${U.esc(u.username)}</b></td>
          <td><div class="account-person"><span class="avatar avatar--sm">${Auth.avatarHtml(u)}</span><div><b data-account-name>${U.esc(u.name)}</b>${u.signature ? `<span class="account-person__signature" title="${U.esc(u.signature)}">${U.esc(u.signature)}</span>` : ''}</div></div></td>
          <td><span class="badge ${u.role === 'teacher' ? 'badge--brand' : 'badge--outline'}">${u.role === 'teacher' ? '教师' : '学生'}</span></td>
          <td>${U.esc(u.className || u.dept || '—')}</td>
          <td class="mono fz-11">${U.esc(u.userId)}</td>
          <td>
            <button class="btn btn--xs" type="button" data-edit="${U.esc(u.userId)}">编辑</button>
            <button class="btn btn--xs btn--danger" type="button" data-del="${U.esc(u.userId)}" data-user="${U.esc(u.username)}">删除</button>
          </td>
        </tr>`).join('');
      // 列表重渲染 → 勾选状态归零（否则"全选"与可见行对不上）
      AdminUsers.syncPickAll();
      U.$$('#userTable [data-pick]', document).forEach(c => {
        c.addEventListener('change', () => AdminUsers.syncPickAll());
      });
      U.$$('#userTable [data-del]', document).forEach(btn => {
        btn.addEventListener('click', () => AdminUsers.confirmDelete(btn.dataset.del, btn.dataset.user));
      });
      U.$$('#userTable [data-edit]', document).forEach(btn => {
        btn.addEventListener('click', () => {
          const u = list.find(x => x.userId === btn.dataset.edit);
          if (u) AdminUsers.openEdit(u);
        });
      });
    }).catch(err => {
      if (request !== this._request) return;
      U.$('#userTable tbody').innerHTML = `<tr><td colspan="7" class="t-danger">${U.esc(err.message || '加载失败')}</td></tr>`;
      AdminUsers.syncPickAll();
    });
  },

  /** 当前勾选的账号 userId 列表 */
  pickedIds() {
    return U.$$('#userTable [data-pick]').filter(c => c.checked).map(c => c.dataset.pick);
  },

  /** 同步「全选」框状态（全选 / 半选 / 未选），并在每次重渲染后复位 */
  syncPickAll() {
    const all = U.$$('#userTable [data-pick]');
    const on = all.filter(c => c.checked).length;
    const box = U.$('#pickAll');
    if (!box) return;
    box.checked = all.length > 0 && on === all.length;
    box.indeterminate = on > 0 && on < all.length;
  },

  /** 批量删除：先勾选 → 二次确认（输入数量）→ 逐行结果（成功/被拒/失败） */
  openBatchDelete() {
    const ids = AdminUsers.pickedIds();
    if (!ids.length) {
      Toast.warn('请先勾选要删除的账号');
      return;
    }
    const rows = U.$$('#userTable tbody tr[data-uid]').filter(tr => ids.indexOf(tr.dataset.uid) >= 0);
    const brief = rows.map(tr => {
      const tds = tr.querySelectorAll('td');
      return `<tr><td class="mono fz-11">${U.esc(tr.dataset.user)}</td>
        <td>${U.esc(tds[2]?.querySelector('[data-account-name]')?.textContent || '')}</td>
        <td class="t-dim">${U.esc(tds[4] ? tds[4].innerText : '')}</td></tr>`;
    }).join('');

    Modal.open({
      title: '批量删除账号',
      closeOnBackdrop: false,
      body: `
        <div class="stack" style="gap:12px">
          <div class="callout callout--danger">${icon('alert')}
            <div>将删除以下 <b>${ids.length}</b> 个账号，并级联清理其练习、进度、AI 会话、预警消息、草稿与课程成员关系。<br>
            <b>不会</b>删除课程本身、资源文件与题库；管理员账号、你自己、以及课程创建者（owner）会被拒绝并列入结果。</div>
          </div>
          <div style="max-height:180px;overflow-x:hidden;overflow-y:auto;border:1px solid var(--border-soft);border-radius:var(--r-sm)">
            <table class="tbl"><thead><tr><th>用户名</th><th>姓名</th><th>班级/部门</th></tr></thead>
              <tbody>${brief}</tbody></table>
          </div>
          <label class="stack" style="gap:4px">
            <span class="fz-12 t-dim">请输入要删除的账号数量（${ids.length}）以确认</span>
            <input class="input" id="bdConfirm" placeholder="${ids.length}" autocomplete="off">
          </label>
        </div>`,
      footer: `<button class="btn btn--danger" id="bdGo" type="button">确认删除</button>
               <button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#bdGo', ov).addEventListener('click', () => {
          if (U.$('#bdConfirm', ov).value.trim() !== String(ids.length)) {
            Toast.warn('确认数量不一致', '请输入 ' + ids.length);
            return;
          }
          const btn = U.$('#bdGo', ov);
          btn.disabled = true;
          API.admin.batchDeleteUsers({ userIds: ids }).then(r => {
            close();
            Toast.ok('批量删除完成',
              `成功 ${r.deleted} 个` + (r.refused ? ` · 被拒 ${r.refused}` : '') + (r.failed ? ` · 失败 ${r.failed}` : ''));
            AdminUsers.load();
            const bad = (r.items || []).filter(x => x.status !== 'deleted');
            if (bad.length) AdminUsers.showBatchResult(bad);
          }).catch(err => {
            btn.disabled = false;
            Toast.error('批量删除失败', (err && err.message) || '');
          });
        });
      }
    });
  },

  /** 批量删除后列出没有被删掉的账号（被拒 / 失败）与原因 */
  showBatchResult(bad) {
    Modal.open({
      title: '未删除的账号',
      body: `<div class="stack" style="gap:8px">
          <p class="fz-12 t-dim" style="margin:0">以下账号没有被删除（被拒或失败），其余已成功删除。</p>
          <table class="tbl"><thead><tr><th>用户名</th><th>结果</th><th>原因</th></tr></thead>
            <tbody>${bad.map(x => `<tr>
              <td class="mono fz-11">${U.esc(x.username || x.userId)}</td>
              <td>${x.status === 'refused' ? '已拒绝' : '失败'}</td>
              <td class="t-dim">${U.esc(x.reason || '')}</td></tr>`).join('')}</tbody></table>
        </div>`,
      footer: `<button class="btn btn--primary" data-close type="button">知道了</button>`,
    });
  },

  openEdit(u) {
    const isTeacher = u.role === 'teacher';
    Modal.open({
      title: '编辑账号',
      closeOnBackdrop: false,
      body: `
        <form class="stack" style="gap:12px" id="euForm">
          <div class="stack" style="gap:4px"><span class="fz-12 t-dim">角色（不可修改）</span>
            <div><span class="badge ${isTeacher ? 'badge--brand' : 'badge--outline'}">${isTeacher ? '教师' : '学生'}</span>
            <span class="mono fz-11 t-dim" style="margin-left:6px">${U.esc(u.userId)}</span></div></div>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">用户名</span>
            <input class="input" id="euUser" value="${U.esc(u.username)}" autocomplete="off"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">姓名</span>
            <input class="input" id="euName" value="${U.esc(u.name || '')}"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">重置密码（留空 = 不修改）</span>
            <input class="input" id="euPwd" type="password" placeholder="至少 6 位" autocomplete="new-password"></label>
          <label class="stack" style="gap:4px" id="euClassWrap"><span class="fz-12 t-dim">班级（学生）</span>
            <input class="input" id="euClass" value="${U.esc(u.className || '')}" placeholder="如：计算机 2301 班"></label>
          <label class="stack" style="gap:4px" id="euNoWrap"><span class="fz-12 t-dim">学号（学生，可选）</span>
            <input class="input" id="euNo" value="${U.esc(u.no || '')}"></label>
          <label class="stack" style="gap:4px;display:none" id="euDeptWrap"><span class="fz-12 t-dim">部门（教师，可选）</span>
            <input class="input" id="euDept" value="${U.esc(u.dept || '')}" placeholder="如：计算机学院"></label>
          <label class="stack" style="gap:4px;display:none" id="euTitleWrap"><span class="fz-12 t-dim">职称（教师，可选）</span>
            <input class="input" id="euTitle" value="${U.esc(u.title || '')}" placeholder="如：副教授"></label>
        </form>`,
      footer: `<button class="btn btn--primary" id="euGo" type="button">保存</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#euClassWrap', ov).style.display = isTeacher ? 'none' : '';
        U.$('#euNoWrap', ov).style.display = isTeacher ? 'none' : '';
        U.$('#euDeptWrap', ov).style.display = isTeacher ? '' : 'none';
        U.$('#euTitleWrap', ov).style.display = isTeacher ? '' : 'none';
        U.$('#euGo', ov).addEventListener('click', () => {
          const payload = {
            username: U.$('#euUser', ov).value.trim(),
            name: U.$('#euName', ov).value.trim(),
            password: U.$('#euPwd', ov).value,
            className: isTeacher ? '' : U.$('#euClass', ov).value.trim(),
            studentNo: isTeacher ? '' : U.$('#euNo', ov).value.trim(),
            dept: isTeacher ? U.$('#euDept', ov).value.trim() : '',
            title: isTeacher ? U.$('#euTitle', ov).value.trim() : '',
          };
          if (!payload.username || !payload.name) {
            Toast.warn('用户名与姓名不能为空');
            return;
          }
          if (payload.password && payload.password.length < 6) {
            Toast.warn('密码至少 6 位');
            return;
          }
          const btn = U.$('#euGo', ov);
          btn.disabled = true;
          API.admin.updateUser(u.userId, payload).then(r => {
            close();
            Toast.ok('账号已更新', (r.username || payload.username) + ' · ' + (r.role === 'teacher' ? '教师' : '学生'));
            AdminUsers.load();
          }).catch(err => {
            btn.disabled = false;
            Toast.error('保存失败', (err && err.message) || '');
          });
        });
      }
    });
  },

  confirmDelete(userId, username) {
    Modal.open({
      title: '删除账号',
      closeOnBackdrop: false,
      body: `
        <div class="stack" style="gap:12px">
          <div class="callout callout--danger">${icon('alert')}
            <div>将删除教师/学生账号 <b>${U.esc(username)}</b>，并级联清理其练习、进度、AI 会话、预警消息、草稿与课程成员关系。<br>
            <b>不会</b>删除课程本身、资源文件与题库；若该教师是课程创建者（owner）会被拒绝。</div>
          </div>
          <label class="stack" style="gap:4px">
            <span class="fz-12 t-dim">请输入用户名以确认：${U.esc(username)}</span>
            <input class="input" id="delConfirmUser" placeholder="${U.esc(username)}" autocomplete="off">
          </label>
        </div>`,
      footer: `<button class="btn btn--danger" id="delGo" type="button">确认删除</button>
               <button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#delGo', ov).addEventListener('click', () => {
          const typed = U.$('#delConfirmUser', ov).value.trim();
          if (typed !== username) {
            Toast.warn('用户名不一致');
            return;
          }
          const btn = U.$('#delGo', ov);
          btn.disabled = true;
          API.admin.deleteUser(userId, { confirmUsername: username }).then(r => {
            close();
            Toast.ok('账号已删除', r.username || username);
            AdminUsers.load();
          }).catch(err => {
            btn.disabled = false;
            Toast.error('删除失败', (err && err.message) || '');
          });
        });
      }
    });
  },

  /* ---------- 批量导入（xlsx / docx）---------- */
  openImport(classMeta = null, onImported = null) {
    const S = { role: 'student', file: null, defaultPassword: '', preview: null };

    const _badge = (st) => st === 'valid'
      ? '<span class="badge badge--outline">待导入</span>'
      : st === 'dup'
        ? '<span class="badge badge--warn">重复</span>'
        : '<span class="badge badge--danger">错误</span>';

    const _download = (format) => {
      API.admin.importTemplate({ role: S.role, format }).then(({ blob, filename }) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename || ('template.' + format);
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }).catch(err => Toast.error('模板下载失败', (err && err.message) || ''));
    };

    const step1 = () => {
      Modal.open({
        title: '批量导入 · 第 1 步 / 选角色与模板',
        closeOnBackdrop: false,
        body: `
          <div class="stack" style="gap:14px">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">导入角色</span>
              <select class="select" id="impRole">
                <option value="student">学生</option>
                <option value="teacher">教师</option>
              </select></label>
            <div class="callout">请先下载模板，按表头（首行）填写；每行一人。支持 .xlsx 与 .docx（旧版 .doc 请另存为 .docx）。</div>
            <div class="row" style="gap:8px">
              <button class="btn btn--sm" id="dlXlsx" type="button">下载 Excel 模板</button>
              <button class="btn btn--sm" id="dlDocx" type="button">下载 Word 模板</button>
            </div>
          </div>`,
        footer: `<button class="btn btn--primary" id="next1" type="button">下一步</button><button class="btn" data-close>取消</button>`,
        onMount(ov, close) {
          U.$('#impRole', ov).value = S.role;
          U.$('#dlXlsx', ov).addEventListener('click', () => _download('xlsx'));
          U.$('#dlDocx', ov).addEventListener('click', () => _download('docx'));
          U.$('#next1', ov).addEventListener('click', () => {
            S.role = U.$('#impRole', ov).value;
            close(); step2();
          });
        }
      });
    };

    const step2 = () => {
      Modal.open({
        title: '批量导入 · 第 2 步 / 上传文件',
        closeOnBackdrop: false,
        body: `
          <div class="stack" style="gap:14px">
            <div class="callout callout--info">当前角色：<b>${S.role === 'student' ? '学生' : '教师'}</b>。${classMeta ? `学生将导入「${U.esc(classMeta.name)}」，文件中的班级列以此为准。` : ''}将解析文件并预览，不会立即写入。</div>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">选择文件（.xlsx / .docx / .csv / .txt）</span>
              <input class="input" id="impFile" type="file" accept=".xlsx,.docx,.csv,.txt"></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">统一初始密码（可选；填写后覆盖文件中的密码列，至少 6 位）</span>
              <input class="input" id="impPwd" type="text" placeholder="留空则使用文件密码列" autocomplete="new-password"></label>
          </div>`,
        footer: `<button class="btn btn--primary" id="parse" type="button">解析预览</button><button class="btn" id="back1" type="button">上一步</button><button class="btn" data-close>取消</button>`,
        onMount(ov, close) {
          if (classMeta) U.$('#back1', ov).hidden = true;
          U.$('#back1', ov).addEventListener('click', () => { close(); step1(); });
          U.$('#parse', ov).addEventListener('click', () => {
            const f = U.$('#impFile', ov).files[0];
            if (!f) { Toast.warn('请先选择文件'); return; }
            S.file = f;
            S.defaultPassword = U.$('#impPwd', ov).value;
            const fd = new FormData();
            fd.append('file', f);
            fd.append('role', S.role);
            fd.append('defaultPassword', S.defaultPassword);
            if (classMeta) fd.append('classId', classMeta.classId);
            const btn = U.$('#parse', ov); btn.disabled = true; btn.textContent = '解析中…';
            API.admin.importPreview(fd).then(r => {
              S.preview = r; close(); step3();
            }).catch(err => {
              btn.disabled = false; btn.textContent = '解析预览';
              Toast.error('解析失败', (err && err.message) || '');
            });
          });
        }
      });
    };

    const step3 = () => {
      const p = S.preview || {};
      const rows = p.rows || [];
      const LIMIT = 300;
      const shown = rows.slice(0, LIMIT);
      const bodyHtml = `
        <div class="stack" style="gap:12px">
          <div class="row" style="gap:8px;flex-wrap:wrap">
            <span class="badge">共 ${p.total || 0} 行</span>
            <span class="badge badge--outline">待导入 ${p.valid || 0}</span>
            <span class="badge badge--warn">重复 ${p.dup || 0}</span>
            <span class="badge badge--danger">错误 ${p.error || 0}</span>
          </div>
          <div style="max-height:46vh;overflow-x:hidden;overflow-y:auto">
            <table class="tbl" style="font-size:13px">
              <thead><tr><th>#</th><th>用户名</th><th>姓名</th><th>状态</th><th>说明</th></tr></thead>
              <tbody>${shown.map(r => `
                <tr>
                  <td class="mono">${r.rowIndex}</td>
                  <td>${U.esc(r.username)}</td>
                  <td>${U.esc(r.name)}</td>
                  <td>${_badge(r.status)}</td>
                  <td class="t-dim">${U.esc(r.error || '')}</td>
                </tr>`).join('')}</tbody>
            </table>
          </div>
          ${rows.length > LIMIT ? `<div class="t-dim fz-12">仅显示前 ${LIMIT} 行，全部 ${rows.length} 行将一并处理。</div>` : ''}
        </div>`;
      Modal.open({
        title: '批量导入 · 第 3 步 / 预览确认',
        closeOnBackdrop: false,
        body: bodyHtml,
        footer: `<button class="btn btn--primary" id="go" type="button">导入 ${p.valid || 0} 条</button><button class="btn" id="back2" type="button">上一步</button><button class="btn" data-close>取消</button>`,
        onMount(ov, close) {
          U.$('#back2', ov).addEventListener('click', () => { close(); step2(); });
          U.$('#go', ov).addEventListener('click', () => {
            if (!S.preview || S.preview.valid === 0) { Toast.warn('没有可导入的行'); return; }
            const fd = new FormData();
            fd.append('file', S.file);
            fd.append('role', S.role);
            fd.append('defaultPassword', S.defaultPassword);
            if (classMeta) fd.append('classId', classMeta.classId);
            const btn = U.$('#go', ov); btn.disabled = true; btn.textContent = '导入中…';
            API.admin.importCommit(fd).then(r => { close(); if (onImported) onImported(); step4(r); })
              .catch(err => {
                btn.disabled = false; btn.textContent = '导入 ' + (S.preview.valid || 0) + ' 条';
                Toast.error('导入失败', (err && err.message) || '');
              });
          });
        }
      });
    };

    const step4 = (r) => {
      const failed = (r && r.errors) || [];
      Modal.open({
        title: '批量导入 · 完成',
        body: `
          <div class="stack" style="gap:12px">
            <div class="row" style="gap:8px;flex-wrap:wrap">
              <span class="badge badge--outline">成功 ${r.created}</span>
              <span class="badge badge--warn">跳过 ${r.skipped}</span>
              <span class="badge badge--danger">失败 ${r.failed}</span>
            </div>
            ${failed.length ? `<div style="max-height:40vh;overflow-x:hidden;overflow-y:auto">
              <div class="t-dim fz-12" style="margin-bottom:6px">失败明细：</div>
              <table class="tbl" style="font-size:13px">
                <thead><tr><th>#</th><th>用户名</th><th>原因</th></tr></thead>
                <tbody>${failed.map(e => `<tr><td class="mono">${e.rowIndex}</td><td>${U.esc(e.username)}</td><td class="t-dim">${U.esc(e.reason)}</td></tr>`).join('')}</tbody>
              </table></div>` : '<div class="callout callout--info">全部有效行已成功导入。</div>'}
          </div>`,
        footer: `<button class="btn btn--primary" id="done" type="button">返回账号列表</button>`,
        onMount(ov, close) {
          U.$('#done', ov).addEventListener('click', () => { close(); AdminUsers.load(); });
        }
      });
    };

    if (classMeta) step2();
    else step1();
  },
};

window.addEventListener('focus', () => AdminUsers.refreshProfiles());
window.addEventListener('profileupdated', () => AdminUsers.refreshProfiles());

Router.register('users', {
  update: () => { AdminUsers.load(); if (AdminClasses.active) AdminClasses.load(); },
  title: '用户管理',
  mount() {
    AdminClasses.init();
    // 筛选与新建按钮：mount 只执行一次，事件不会重复绑定
    U.$('#fRole').addEventListener('change', () => AdminUsers.load());
    let tm;
    U.$('#fKey').addEventListener('input', () => {
      clearTimeout(tm);
      tm = setTimeout(() => AdminUsers.load(), 250);
    });
    U.$('#btnImport').addEventListener('click', () => AdminUsers.openImport());
    U.$('#btnBatchDel').addEventListener('click', () => AdminUsers.openBatchDelete());
    U.$('#pickAll').addEventListener('change', () => {
      const on = U.$('#pickAll').checked;
      U.$$('#userTable [data-pick]').forEach(c => { c.checked = on; });
      AdminUsers.syncPickAll();
    });
    U.$('#btnCreate').addEventListener('click', () => {
      Modal.open({
        title: '新建账号',
        closeOnBackdrop: false,
        body: `
          <form class="stack" style="gap:12px" id="cuForm">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">角色</span>
              <select class="select" id="cuRole">
                <option value="teacher">教师</option>
                <option value="student">学生</option>
              </select></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">用户名</span>
              <input class="input" id="cuUser" placeholder="登录用，如 t_wang / s_li" autocomplete="off"></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">姓名</span>
              <input class="input" id="cuName" placeholder="真实姓名"></label>
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">密码</span>
              <input class="input" id="cuPwd" type="password" placeholder="至少 6 位" value="123456"></label>
            <label class="stack" style="gap:4px" id="cuClassWrap"><span class="fz-12 t-dim">班级（学生）</span>
              <input class="input" id="cuClass" placeholder="如：计算机 2301 班"></label>
            <label class="stack" style="gap:4px;display:none" id="cuDeptWrap"><span class="fz-12 t-dim">部门（教师，可选）</span>
              <input class="input" id="cuDept" placeholder="如：计算机学院"></label>
          </form>`,
        footer: `<button class="btn btn--primary" id="cuGo" type="button">创建</button><button class="btn" data-close>取消</button>`,
        onMount(ov, close) {
          const sync = () => {
            const role = U.$('#cuRole', ov).value;
            U.$('#cuClassWrap', ov).style.display = role === 'student' ? '' : 'none';
            U.$('#cuDeptWrap', ov).style.display = role === 'teacher' ? '' : 'none';
          };
          U.$('#cuRole', ov).addEventListener('change', sync);
          sync();
          U.$('#cuGo', ov).addEventListener('click', () => {
            const role = U.$('#cuRole', ov).value;
            const payload = {
              role,
              username: U.$('#cuUser', ov).value.trim(),
              name: U.$('#cuName', ov).value.trim(),
              password: U.$('#cuPwd', ov).value,
              className: role === 'student' ? U.$('#cuClass', ov).value.trim() : '',
              dept: role === 'teacher' ? U.$('#cuDept', ov).value.trim() : '',
            };
            API.admin.createUser(payload).then(r => {
              close();
              Toast.ok('账号已创建', r.username + ' · ' + (r.role === 'teacher' ? '教师' : '学生'));
              AdminUsers.load();
            }).catch(err => Toast.error('创建失败', (err && err.message) || ''));
          });
        }
      });
    });
    AdminUsers.load();
  },
});
