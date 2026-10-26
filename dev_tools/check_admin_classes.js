/* 执行真实班级管理与导入向导代码，验证确认与请求范围；DOM 替身不代替浏览器实测。 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { File } = require('node:buffer');

class Element {
  constructor() {
    this.hidden = false; this.disabled = false; this.value = ''; this.innerHTML = ''; this.textContent = '';
    this.checked = false; this.dataset = {}; this.events = {}; this.attributes = {};
    const values = new Set();
    this.classList = { toggle(name, on) { if (on) values.add(name); else values.delete(name); }, contains(name) { return values.has(name); } };
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(type, fn) { (this.events[type] ||= []).push(fn); }
  async emit(type) { for (const fn of this.events[type] || []) await fn({ target: this, currentTarget: this, preventDefault() {} }); }
  querySelector(selector) { return get(selector); }
  querySelectorAll() { return []; }
}
const nodes = new Map();
function get(selector) { if (!nodes.has(selector)) nodes.set(selector, new Element()); return nodes.get(selector); }
const accountsTab = get('#accountsTab'), classesTab = get('#classesTab');
accountsTab.dataset.userPanel = 'accounts'; classesTab.dataset.userPanel = 'classes';
const modals = [], calls = [], notices = [];
let currentStudents = [{ userId: 'S1', name: '甲', username: 'one', studentNo: '1' }, { userId: 'S2', name: '乙', username: 'two', studentNo: '2' }];
const api = { admin: {
  listUsers: async () => ({ list: [] }),
  classes: {
    list: async () => { calls.push(['list']); return { list: [{ classId: 'A', name: '测试班', studentCount: 2 }] }; },
    students: async id => { calls.push(['students', id]); return { classId: id, name: '测试班', studentCount: currentStudents.length, list: currentStudents }; },
    deleteStudents: async (id, ids) => { calls.push(['deleteStudents', id, ids]); return {}; },
    deletePreview: async id => { calls.push(['preview', id]); return { classId: id, name: '测试班', studentCount: 2, students: currentStudents, courses: [{ name: '课程甲' }], revision: 'a'.repeat(64) }; },
    remove: async (id, revision) => { calls.push(['deleteClass', id, revision]); return {}; },
  },
  importPreview: async form => { calls.push(['importPreview', form]); return { total: 1, valid: 1, dup: 0, error: 0, rows: [{ rowIndex: 1, username: 'new', name: '新生', status: 'valid' }] }; },
  importCommit: async form => { calls.push(['importCommit', form]); return { created: 1, skipped: 0, failed: 0, errors: [] }; },
} };
const context = vm.createContext({ console, FormData, File, Blob, URL, setTimeout, clearTimeout,
  window: { addEventListener() {} }, document: { querySelector() { return null; } }, API: api,
  U: { $: (selector, parent) => parent ? parent.querySelector(selector) : get(selector), $$: selector => selector === '[data-user-panel]' ? [accountsTab, classesTab] : [],
    esc: text => String(text ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])) },
  Toast: Object.fromEntries(['ok', 'warn', 'error'].map(key => [key, (...values) => notices.push([key, ...values])])),
  Router: { current: 'users', views: {}, register(key, value) { this.views[key] = value; } },
  Auth: { avatarHtml() { return ''; } }, icon() { return ''; },
  Modal: { open(options) {
    const controls = new Map();
    const overlay = new Element();
    overlay.querySelector = selector => { if (!controls.has(selector)) controls.set(selector, new Element()); return controls.get(selector); };
    let closed = false;
    modals.push({ options, overlay, controls, get closed() { return closed; } });
    options.onMount?.(overlay, () => { closed = true; });
  } },
});
vm.runInContext(fs.readFileSync('assets/js/admin/views/classes.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('assets/js/admin/views/users.js', 'utf8'), context);
const classes = vm.runInContext('AdminClasses', context), users = vm.runInContext('AdminUsers', context);
const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  classes.init();
  assert.equal(calls.length, 0);
  await classesTab.emit('click'); await tick();
  assert.equal(get('#adminAccountsPanel').hidden, true);
  assert.equal(get('#adminClassesPanel').hidden, false);
  assert.equal(classesTab.attributes['aria-selected'], 'true');
  assert(get('#classMembers').innerHTML.includes('加入已有学生'));
  assert(get('#classMembers').innerHTML.includes('classDeleteStudents'));
  await accountsTab.emit('click'); await tick();
  assert.equal(get('#adminAccountsPanel').hidden, false);
  assert.equal(get('#adminClassesPanel').hidden, true);
  console.log('[ok] 用户管理页签切换与班级学生入口');

  classes.students = currentStudents;
  classes.removeStudents('A', ['S1']);
  assert.equal(calls.filter(call => call[0] === 'deleteStudents').length, 0);
  let modal = modals.at(-1);
  assert(modal.options.body.includes('所有课程'));
  await modal.overlay.querySelector('#classStudentsDeleteConfirm').emit('click'); await tick();
  const removal = calls.find(call => call[0] === 'deleteStudents');
  assert.deepEqual(JSON.parse(JSON.stringify(removal)), ['deleteStudents', 'A', ['S1']]);
  console.log('[ok] 删除学生只在确认后发请求，班级与学生范围正确');

  await classes.removeClass('A');
  assert.equal(calls.filter(call => call[0] === 'deleteClass').length, 0);
  modal = modals.at(-1);
  assert(modal.options.body.includes('课程甲'));
  assert(modal.options.footer.includes('删除班级及 2 名学生'));
  await modal.overlay.querySelector('#classDeleteConfirm').emit('click'); await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(call => call[0] === 'deleteClass'))), ['deleteClass', 'A', 'a'.repeat(64)]);
  console.log('[ok] 删班先预览再确认，提交服务器返回的名单版本');

  let imported = 0;
  users.openImport({ classId: 'A', name: '测试班' }, () => imported++);
  modal = modals.at(-1);
  assert(modal.options.title.includes('上传文件'));
  assert.equal(modal.overlay.querySelector('#back1').hidden, true);
  assert(modal.options.body.includes('测试班'));
  modal.overlay.querySelector('#impFile').files = [new File(['用户名,姓名\nnew,新生'], 'students.csv', { type: 'text/csv' })];
  modal.overlay.querySelector('#impPwd').value = 'Check123';
  await modal.overlay.querySelector('#parse').emit('click'); await tick();
  assert.equal(calls.find(call => call[0] === 'importPreview')[1].get('classId'), 'A');
  modal = modals.at(-1);
  assert(modal.options.title.includes('预览确认'));
  assert.equal(calls.filter(call => call[0] === 'importCommit').length, 0);
  await modal.overlay.querySelector('#go').emit('click'); await tick();
  assert.equal(calls.find(call => call[0] === 'importCommit')[1].get('classId'), 'A');
  assert.equal(imported, 1);
  console.log('[ok] 指定班级导入复用预览向导，确认前不写入，完成后刷新名单');
  console.log('全部逻辑检查通过；DOM 替身不作为浏览器显示与硬刷新验收。');
})().catch(error => { console.error(error); process.exitCode = 1; });
