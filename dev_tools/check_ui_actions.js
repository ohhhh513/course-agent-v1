/* 实际执行器与共享聊天的 Node 验收。DOM 为内存替身，不冒充浏览器实测。 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const catalogue = JSON.parse(read('assets/agent-ui-actions.json'));

async function main() {
  const elements = new Map(), calls = [], warnings = [];
  let dirty = false, activeUser = {role:'student', userId:'U1'};
  let login = '1';
  const element = (selector, props = {}) => {
    const item = {tagName:'INPUT', value:'', dataset:{}, options:undefined, disabled:false,
      classList:{contains:()=>false}, closest:()=>null, querySelector:()=>null, querySelectorAll:()=>[],
      dispatchEvent:event=>calls.push(['event', selector, event.type]),
      click:()=>calls.push(['click', selector]), focus:()=>{}, scrollIntoView:()=>{}, ...props};
    elements.set(selector, item); return item;
  };
  const document = {body:{}, addEventListener:()=>{},
    getElementById:()=>({querySelector:selector=>elements.get(selector)}),
    querySelectorAll:()=>[], querySelector:selector=>selector.includes('data-agent-dirty') ? dirty : elements.get(selector)};
  const sandbox = {document, Auth:{currentUser:()=>activeUser,getSession:()=>({loginStartedAt:login})}, API:{config:{activeCourseId:'C1'}},
    Router:{current:'ai', go(view) { this.current = view; calls.push(['route',view]); }},
    Toast:{warn:(...args)=>warnings.push(args)}, CSS:{escape:String},
    fetch:async()=>({ok:true,json:async()=>catalogue}),
    MutationObserver:class {observe(){} disconnect(){}}, Event:class {constructor(type){this.type=type}},
    DataTransfer:class {constructor(){this.files=[];this.items={add:file=>this.files.push(file)}}},
    setTimeout, clearTimeout, setInterval, clearInterval, console,
    Practice:{activeMode:null}, window:{}, icon:()=>'', U:{esc:String},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(read('assets/js/shared/agent-ui.js'), context);
  const ui = vm.runInContext('AgentUI', context);
  let number = 0;
  const plan = (target, values={}, object=null) => ({id:String(++number), target, values, object,
      role:activeUser.role,userId:activeUser.userId,courseId:'C1',attachments:[],auto:true});
  for (const action of catalogue.actions) assert(!action.handler || typeof ui.handlers[action.handler] === 'function', action.id);
  element('#joinCourseBtn'); const code = element('#jcCode');
  const join = plan('student.course.join',{inviteCode:'ABC123'});
  assert(await ui.apply(join,{auto:true,fromView:'ai'}));
  assert.equal(code.value,'ABC123');
  assert(calls.some(c=>c[1]==='#joinCourseBtn'));
  assert(!calls.some(c=>c[1]==='#jcGo'),'不能点击加入确认');
  const count = calls.length;
  assert.equal(await ui.apply(join,{auto:true,fromView:'ai'}),false);
  assert.equal(calls.length,count,'自动执行只执行一次');
  assert(await ui.apply(join),'历史按钮允许手动再次打开');
  console.log('PASS 加入课程弹窗及邀请码回填，保留确认按钮；自动去重、历史手动重开');

  element('#msgBtn'); element('.modal'); assert(await ui.apply(plan('student.messages')));
  element('#pTabs [data-t="quiz"]');
  element('#modeGrid [data-mode="order"]',{click:()=>{sandbox.Practice.activeMode='order';calls.push(['mode','order'])}});
  element('#modePanel [data-kp]');
  assert(await ui.apply(plan('student.practice.mode.order'),{auto:true,fromView:'ai'}));
  assert.equal(sandbox.Router.current,'practice'); assert.equal(sandbox.Practice.activeMode,'order');
  sandbox.Router.current='ai';
  element('#pTabs [data-t="wrong"]'); element('#wFilter [data-f="true"]');
  assert(await ui.apply(plan('student.practice.wrong.filter',{filter:'true'})));
  console.log('PASS 顶栏通知、顺序练习的实际模式处理器和错题筛选');

  sandbox.Router.current='ai';
  const prior = calls.length;
  dirty = true; assert.equal(await ui.apply(plan('student.messages')),false); dirty=false;
  assert.equal(await ui.apply({...plan('student.messages'),role:'teacher'}),false);
  assert.equal(await ui.apply({...plan('student.messages'),courseId:'OTHER'}),false);
  assert.equal(await ui.apply(plan('student.messages'),{auto:true,fromView:'users'}),false);
  assert.equal(await ui.apply(plan('student.course.join',{selector:'#jcGo'})),false);
  assert.equal(calls.length,prior);
  console.log('PASS 未保存输入、跨角色、跨课程、离开聊天页和非法字段不会执行');
  const ordinaryFetch=sandbox.fetch;
  sandbox.fetch=async()=>{login='2';return {ok:true,json:async()=>catalogue}};
  assert.equal(await ui.apply(plan('student.messages')),false);
  assert.equal(calls.length,prior);
  sandbox.fetch=ordinaryFetch;
  console.log('PASS 操作等待中同一账号重新登录也会取消');

  activeUser={role:'teacher',userId:'T1'}; sandbox.Router.current='chat';
  sandbox.Monitor={openProfile:id=>{calls.push(['student',id]); element('#prMsg')}};
  element('#prMsg'); const message = element('#msgBody',{closest:()=>({})});
  assert(await ui.apply(plan('teacher.monitor.message',{content:'请复习树的遍历。'},{id:'S1',name:'小明'})));
  assert.equal(message.value,'请复习树的遍历。'); assert.equal(message.dataset.agentDirty,'1');
  assert(calls.some(c=>c[0]==='student' && c[1]==='S1'));
  assert(!calls.some(c=>c[1]==='#msgSend'));
  console.log('PASS 指定学生私信弹窗与原文回填，未发送');

  activeUser={role:'admin',userId:'A1'}; sandbox.Router.current='assistant';
  element('#btnCreate'); element('#cuRole',{tagName:'SELECT',options:[{value:'student'},{value:'teacher'}]});
  const name=element('#cuName',{closest:()=>({})});
  assert(await ui.apply(plan('admin.users.new',{role:'teacher',name:'测试教师'})));
  assert.equal(name.value,'测试教师'); assert(!calls.some(c=>c[1]==='#cuGo'));
  const input={accept:'.xlsx,.docx', multiple:false, dispatchEvent:()=>{}};
  const file={name:'accounts.xlsx',type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'};
  ui.setFile(input,[file]); assert.equal(input.files[0],file);
  assert.throws(()=>ui.setFile(input,[{name:'wrong.png',type:'image/png'}]));
  console.log('PASS 管理员账号表单原文回填、附件 DataTransfer 与文件格式验证，未创建账号');

  sandbox.API.ai={};
  vm.runInContext(read('assets/js/shared/agent-chat.js'),context);
  const chat=sandbox.window.AgentChatView.create({viewKey:'assistant',api:sandbox.API.ai});
  chat.sessionId='SESSION';
  const saved={toolLog:[{kind:'ui_action',plan:join},{kind:'ui_action',plan:join}]};
  const restored=chat.uiCardsOf(JSON.parse(JSON.stringify(saved)));
  assert.equal(restored.length,1); assert.equal(restored[0].sessionId,'SESSION');
  assert.equal(restored[0].values.inviteCode,'ABC123');
  console.log('PASS 实际共享聊天从持久化日志重建入口并去重，恢复数据不自动执行');
  let origin={key:'account-course',loginId:'1'}, invoked=0;
  chat._openSessionStorageInfo=()=>origin;
  sandbox.API.ai.fetchAttachment=async()=>({blob:{type:'text/plain'}});
  sandbox.File=class {constructor(parts,name,options){this.name=name;this.type=options.type}};
  const normalApply=ui.apply;ui.apply=async()=>{invoked++;return true};
  const withFile={...restored[0],attachments:[{attachmentId:'A',name:'q.txt',mimeType:'text/plain'}]};
  const pending=chat.applyUiPlan(withFile);chat.sessionId='OTHER';
  assert.equal(await pending,false);assert.equal(invoked,0);
  chat.sessionId='SESSION';
  const relogin=chat.applyUiPlan(withFile);origin={...origin,loginId:'2'};
  assert.equal(await relogin,false);assert.equal(invoked,0);
  ui.apply=normalApply;
  console.log('PASS 附件恢复等待中切换会话或重新登录不会触发旧计划');
  console.log(`全部通过：${catalogue.actions.length} 个处理器入口，前端逻辑验收（非浏览器实测）`);
}
main().catch(error=>{console.error(error);process.exitCode=1});
