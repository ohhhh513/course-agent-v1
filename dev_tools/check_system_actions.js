/* Node 自检：运行实际三端配置和共享历史按钮绑定；DOM 用内存替身，不算浏览器实测。 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');

for (const [role, file, objectName] of [
  ['student', 'chat.js', 'Chat'],
  ['teacher', 'chat.js', 'TeacherChat'],
  ['admin', 'assistant.js', 'AdminChat'],
]) {
  let configuration;
  const calls = [];
  const context = vm.createContext({
    window: {}, icon: () => '', API: { ai: {}, adminAgent: {} },
    AgentChatView: { create: cfg => { configuration = cfg; return {}; } },
    Router: { register: () => {}, go: view => calls.push(view) },
    Practice: {}, console, setTimeout, clearTimeout,
  });
  vm.runInContext(read(`assets/js/${role}/views/${file}`), context);
  assert(vm.runInContext(`typeof ${objectName} === 'object'`, context));
  const views = Array.from(read(`${role}.html`).matchAll(/data-view="([^"]+)"/g), m => m[1]);
  for (const view of views) {
    const action = { kind: 'navigate', label: `打开${view}`, view };
    assert.equal(configuration.applyAction(action), true);
    assert.equal(calls.at(-1), view);
  }
  for (const view of ['users', 'structure', 'practice', 'assistant', 'chat', 'ai'].filter(v => !views.includes(v))) {
    const before = calls.length;
    assert.equal(configuration.applyAction({ kind: 'navigate', label: '越权页面', view }), false);
    assert.equal(calls.length, before);
  }
  assert.equal(configuration.applyAction({ kind: 'delete', view: views[0] }), false);
  if (role !== 'student') assert.equal(configuration.applyAction({ kind: 'practice', kpId: 'KP001' }), false);

  // 使用真实共享工厂重建刷新后 toolLog 中的导航，绑定点击，再调用实际角色配置。
  vm.runInContext(read('assets/js/shared/agent-chat.js'), context);
  const view = role === 'admin' ? 'users' : role === 'teacher' ? 'structure' : 'practice';
  const action = { kind: 'navigate', label: '打开页面', view };
  const message = { toolLog: [{ kind: 'tool', name: 'suggest_action', ok: true, args: action }] };
  context.configuration = configuration;
  const chat = vm.runInContext('window.AgentChatView.create(configuration)', context);
  const restored = chat.suggestCardsOf(JSON.parse(JSON.stringify(message)));
  assert.equal(restored.length, 1);
  assert.equal(restored[0].view, view);
  assert.equal(chat.suggestCardsOf({ toolLog: [{ ...message.toolLog[0], ok: false }] }).length, 0);
  const listeners = [];
  const button = {
    dataset: { agentAction: JSON.stringify(restored[0]) },
    addEventListener: (name, handler) => { if (name === 'click') listeners.push(handler); },
  };
  const log = { querySelectorAll: () => [] };
  context.U = { $: () => log, $$: selector => selector === '[data-agent-action]' ? [button] : [] };
  context.Toast = { warn: () => { throw new Error('合法历史按钮被拒绝'); } };
  chat.bindCites();
  chat.bindCites();
  assert.equal(listeners.length, 1, '重复绑定不增加点击处理器');
  listeners[0]();
  assert.equal(calls.at(-1), view);
  console.log(`[ok] ${role} 实际跳转配置、跨角色拦截、历史按钮重建和点击绑定`);
}
console.log('前端逻辑检查全部通过（非浏览器实测）');
