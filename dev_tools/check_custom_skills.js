/* 运行实际技能菜单逻辑；重点检查动态权限列表、过期请求和不可信名称转义。 */
'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('assets/js/shared/agent-chat.js', 'utf8');
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let root = { querySelector: () => list }, list = { innerHTML: '' };
const pending = [];
const api = { config: { activeCourseId: 'A' }, ai: {}, skills: { list: courseId => new Promise((resolve, reject) => pending.push({courseId, resolve, reject})) } };
const context = vm.createContext({window:{}, API:api, console, icon:()=>'', U:{$:()=>root,esc}, document:{}, setTimeout,clearTimeout});
vm.runInContext(source, context);
context.configuration = { containerId:'#view-ai',customSkills:'student',skills:[{id:'course_qa',label:'课程答疑'}] };
const chat = vm.runInContext('window.AgentChatView.create(configuration)', context);
chat._isWorking = () => false;
chat._paintSkill = () => {};
chat._filterPlusMenu = () => {};
chat._positionPlusMenu = () => {};
chat._plusMenu = () => null;
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
(async()=>{
  chat._loadCourseSkills(root);
  pending.shift().resolve({list:[{id:'CS1',label:'<img src=x onerror=alert(1)>',desc:'循序渐进'}]});
  await flush();
  assert.equal(chat._availableSkills().length,2);
  assert(list.innerHTML.includes('&lt;img')&&!list.innerHTML.includes('<img'));
  chat.activeSkillId='CS1';
  assert.equal(chat._activeSkill().id,'CS1');
  chat._loadCourseSkills(root);pending.shift().resolve({list:[]});await flush();
  assert.equal(chat.activeSkillId,null);
  assert.equal(chat._availableSkills().length,1);
  console.log('[ok] 加载课程技能、保留内置技能、名称转义、停用后移除列表和已选标签');

  chat._loadCourseSkills(root);const old=pending.shift();
  api.config.activeCourseId='B';chat._loadCourseSkills(root);const current=pending.shift();
  current.resolve({list:[{id:'CSB',label:'课程 B'}]});await flush();
  old.resolve({list:[{id:'CSA',label:'课程 A'}]});await flush();
  assert.equal(chat._availableSkills().at(-1).id,'CSB');
  chat._loadCourseSkills(root);const stale=pending.shift();
  root={querySelector:()=>list};stale.resolve({list:[{id:'CSOLD',label:'旧页面'}]});await flush();
  assert.equal(chat._availableSkills().at(-1).id,'CSB');
  console.log('[ok] 切换课程及重新挂载时，旧请求不覆盖当前技能列表');

  chat._loadCourseSkills(root);pending.shift().reject(new Error('网络错误'));await flush();
  assert.equal(chat._availableSkills().length,1);
  assert(list.innerHTML.includes('加载失败'));
  assert.equal(chat._activeSkill(),null);
  console.log('[ok] 加载失败时保留内置技能并显示重试提示');
})().catch(error=>{console.error(error);process.exitCode=1;});
