/* 运行真实练习/报告页和执行器；DOM 替身仅用于逻辑回归，不替代浏览器验收。 */
'use strict';
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const catalogue = JSON.parse(read('assets/agent-ui-actions.json'));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b)=>{resolve=a;reject=b}); return {promise,resolve,reject}; };
const flush = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };

class Element {
  constructor(tag='div', attributes={}) {
    this.tagName=tag.toUpperCase(); this.attributes=attributes; this.children=[]; this.dataset={}; this.events={};
    this.disabled='disabled' in attributes; this.hidden='hidden' in attributes; this.checked='checked' in attributes;
    this.value=attributes.value||''; this.type=attributes.type||'';
    for(const [key,value] of Object.entries(attributes)) if(key.startsWith('data-')) this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;
    const classes=new Set((attributes.class||'').split(/\s+/).filter(Boolean));
    this.classList={contains:x=>classes.has(x),add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>{const flag=on===undefined?!classes.has(x):on;flag?classes.add(x):classes.delete(x);return flag;}};
  }
  set innerHTML(html) {
    this._html=html; this.children=[]; this._text=''; const stack=[this];
    for(const token of html.match(/<[^>]+>|[^<]+/g)||[]) {
      if(token.startsWith('</')) {if(stack.length>1) stack.pop();continue;}
      if(!token.startsWith('<')) {stack.at(-1)._text=(stack.at(-1)._text||'')+token;continue;}
      const match=/^<(\w+)([^>]*)>/.exec(token); if(!match)continue;
      const attrs={}; for(const a of match[2].matchAll(/([\w-]+)(?:="([^"]*)"|='([^']*)')?/g))attrs[a[1]]=a[2]??a[3]??'';
      const child=new Element(match[1],attrs); stack.at(-1).appendChild(child);
      if(!['input','br','hr','img','meta','link'].includes(match[1]))stack.push(child);
    }
    for(const select of this.querySelectorAll('select')) {const selected=select.options.find(o=>'selected' in o.attributes)||select.options[0];if(selected)select.value=selected.value;}
  }
  get innerHTML(){return this._html||'';}
  get textContent(){return (this._text||'')+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  get options(){return this.tagName==='SELECT'?this.querySelectorAll('option'):undefined;}
  get id(){return this.attributes.id||'';}
  set id(value){this.attributes.id=String(value);}
  appendChild(child){child.parentElement=this;this.children.push(child);return child;}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);this.parentElement=null;}
  get isConnected(){return Boolean(this.parentElement);}
  getAttribute(name){return this.attributes[name]??null;}
  addEventListener(type,fn){(this.events[type]||=[]).push(fn);}
  dispatchEvent(event){for(const fn of this.events[event.type]||[])fn(event);return true;}
  click(){if(!this.disabled)this.dispatchEvent({type:'click',target:this,stopPropagation(){}});}
  focus(){} scrollIntoView(){}
  matches(selector){
    const attrs=[...selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)];
    if(attrs.some(a=>this.getAttribute(a[1])===null||(a[2]!==undefined&&this.getAttribute(a[1])!==a[2])))return false;
    const basic=selector.replace(/\[[^\]]+\]/g,'');
    const tag=/^[\w-]+/.exec(basic);if(tag&&this.tagName!==tag[0].toUpperCase())return false;
    const id=/#([\w-]+)/.exec(basic);if(id&&this.attributes.id!==id[1])return false;
    return [...basic.matchAll(/\.([\w-]+)/g)].every(c=>this.classList.contains(c[1]));
  }
  closest(selector){return selector.split(',').some(s=>this.matches(s.trim()))?this:this.parentElement?.closest(selector)||null;}
  querySelectorAll(selector){
    const results=[];
    for(const group of selector.split(',')) {
      const parts=group.trim().split(/\s+(?![^[]*\])/);
      const visit=node=>{for(const child of node.children){if(child.matches(parts.at(-1))){let cursor=child.parentElement,i=parts.length-2;while(cursor&&i>=0){if(cursor.matches(parts[i]))i--;cursor=cursor.parentElement;}if(i<0&&!results.includes(child))results.push(child);}visit(child);}};
      visit(this);
    }
    return results;
  }
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}

function setup(role='student', storage=new Map()) {
  const body=new Element('body');body.innerHTML='<div id="view-practice" class="view"></div><div id="view-report" class="view"></div>';
  const warnings=[], writes=[];
  const document={body,addEventListener(){},createElement:tag=>new Element(tag),getElementById:id=>body.querySelector('#'+id),querySelector:s=>body.querySelector(s),querySelectorAll:s=>body.querySelectorAll(s)};
  const sandbox={console,document,window:{},icon:()=>'',R:{empty:()=>''},CSS:{escape:String},
    Auth:{currentUser:()=>({role,userId:role+'1'}),getSession:()=>({loginStartedAt:'login1'})},
    U:{$:(s,p=body)=>p.querySelector(s),$$:(s,p=body)=>p.querySelectorAll(s),esc:String,bar:()=>'',stars:()=>''},
    Router:{current:'ai',views:{},register(id,cfg){this.views[id]=cfg;},go(id){this.current=id;const cfg=this.views[id];if(cfg&&!cfg.mounted){cfg.mount();cfg.mounted=true;}}},
    Toast:{warn:(...x)=>warnings.push(x),ok(){},info(){},err(){}},
    MutationObserver:class {observe(){}disconnect(){}},Event:class{constructor(type){this.type=type;}},
    setTimeout,clearTimeout,setInterval:(fn,delay)=>delay===1000?0:setInterval(fn,delay),clearInterval,
    fetch:async()=>({ok:true,json:async()=>catalogue}),sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
    API:{config:{activeCourseId:'C1'},practice:{},student:{},course:{my:async()=>[{courseId:'C1',name:'课程'}]},teacher:{resourceKps:async()=>({chapters:[{chapter:'第1章 绪论'}]})}},
  };
  sandbox.Modal={open:cfg=>{const ov=body.appendChild(new Element('div',{class:'overlay'}));ov.innerHTML='<div class="modal">'+cfg.body+(cfg.footer||'')+'</div>';const close=()=>ov.remove();if(cfg.onMount)cfg.onMount(ov,close);return {el:ov,close};}};
  const context=vm.createContext(sandbox);
  vm.runInContext(read('assets/js/shared/agent-ui.js'),context);
  return {sandbox,context,body,warnings,writes,ui:vm.runInContext('AgentUI',context),storage};
}
let next=0;
function plan(s,target,values={},object=null){const user=s.sandbox.Auth.currentUser();return {id:'click-'+(++next),target,values,object,role:user.role,userId:user.userId,courseId:'C1',auto:true};}
const modes=[{key:'wrong',name:'错题重练',count:10},{key:'order',name:'顺序练习',count:20}];
const question={qId:'Q1',stem:'测试题',options:[{key:'A',text:'选项A'},{key:'B',text:'选项B'}],difficulty:1};

async function practice() {
  const s=setup(), api=s.sandbox.API;
  api.practice.modes=async()=>modes;api.student.dashboard=async()=>({weakPoints:[]});
  api.practice.current=async()=>({});api.practice.create=async args=>{s.writes.push(args);return {sessionId:'P1',questions:[question]};};
  api.practice.submitAnswer=()=>{throw Error('禁止自动提交');};
  vm.runInContext(read('assets/js/student/views/practice.js'),s.context);
  const practice=vm.runInContext('Practice',s.context);
  assert.equal(await s.ui.apply({...plan(s,'student.practice.mode.wrong'),auto:false},{auto:true,fromView:'ai'}),false,
    '未确认的界面跳转不能自动执行');
  assert(await s.ui.apply(plan(s,'student.practice.mode.wrong'),{auto:true,fromView:'ai'}));
  assert.equal(practice.state,'quiz');assert.equal(practice.mode,'wrong');assert.equal(practice.picked,null);
  assert(s.body.querySelector('#qBack'));assert(s.body.querySelector('#qSubmit').disabled);
  assert.equal(s.writes.length,1);assert.equal(s.writes[0].mode,'wrong');
  const before=s.body.querySelector('#modePanel').innerHTML;
  s.body.querySelector('#pTabs [data-t="quiz"]').click();await flush();
  assert.equal(s.body.querySelector('#modePanel').innerHTML,before,'重复页签不能关闭题目');
  console.log('PASS 实际练习页：错题模式打开题目，无选择答案/提交；重复页签不重绘');

  practice.render();await flush();const sv=deferred();api.practice.current=()=>sv.promise;
  const request=s.ui.apply(plan(s,'student.practice.mode.wrong'));await new Promise(r=>setTimeout(r,120));
  sv.resolve({sessionId:'OLD',mode:'wrong',answered:1,total:2,questions:[{...question,answered:true,myAnswer:'A'},{...question,qId:'Q2'}]});
  assert(await request);assert.equal(practice.sessionId,'OLD');assert.equal(practice.idx,1);assert.equal(s.writes.length,1,'继续存档不能新建卷');
  console.log('PASS 未完成错题自动继续原进度，不重建卷、不代答');

  const one=deferred(),two=deferred();let n=0;api.practice.modes=()=>++n===1?one.promise:two.promise;
  practice.renderSelect();practice.renderSelect();two.resolve(modes);await flush();
  const panel=s.body.querySelector('#modePanel');panel.innerHTML='<b id="openedContent">已打开</b>';
  one.resolve(modes);await flush();assert(s.body.querySelector('#openedContent'),'较晚返回的旧入口请求不能覆盖模式');
  console.log('PASS 同一 DOM 上两次加载：过期请求不覆盖已经打开的内容');

  api.practice.modes=async()=>modes;practice.renderSelect();await flush();
  const pending=deferred();api.practice.current=()=>pending.promise;
  practice.enterMode('wrong',modes,s.body.querySelector('[data-mode="wrong"]'));practice.collapsePanel();await flush();pending.resolve({});await flush();
  assert.equal(s.writes.length,1,'收起后旧存档查询不能创建练习');
  api.practice.current=async()=>({});api.graph={get:async()=>({nodes:[]})};api.practice.kpPool=async()=>({counts:{}});
  assert(await s.ui.apply(plan(s,'student.practice.mode.order')));assert(s.body.querySelector('#modePanel .callout--warn'));
  console.log('PASS 收起取消旧存档回调；顺序题为空正常显示提示，不等待超时');
  api.graph.get=async()=>({nodes:[{id:'K1',name:'绪论',chapter:'第1章 绪论'}]});api.practice.kpPool=async()=>({counts:{K1:2}});
  practice.renderSelect();await flush();
  assert(await s.ui.apply(plan(s,'student.practice.chapter',{}, {id:'CH1',name:'第1章 绪论'})));
  assert.deepEqual(Array.from(s.writes.at(-1).kpIds),['K1']);assert.equal(practice.picked,null);
  practice.renderSelect();await flush();
  assert(await s.ui.apply(plan(s,'student.practice.kp',{}, {id:'K1',name:'绪论'})));
  assert.deepEqual(Array.from(s.writes.at(-1).kpIds),['K1']);assert.equal(practice.picked,null);
  console.log('PASS 指定章节/知识点会点击真实入口组卷，仍不选择答案');
}

async function reports() {
  const storage=new Map(),s=setup('student',storage),api=s.sandbox.API;
  const create=deferred();api.student.report={list:async()=>({list:[]}),generate:()=>{s.writes.push('generate');return create.promise;},detail:async()=>({title:'个人学情报告',detail:{meta:{},sections:[]}})};
  vm.runInContext(read('assets/js/student/views/report.js'),s.context);
  const target=plan(s,'student.report.create');const task=s.ui.apply(target,{auto:true,fromView:'ai'});
  await flush();assert.equal(s.writes.length,1);s.body.querySelector('#genMyReport').click();assert.equal(s.writes.length,1);
  create.resolve({reportId:'R1'});assert(await task);assert(s.body.querySelector('#myExPdf'),'生成后实际打开报告详情');
  assert.equal(await s.ui.apply(target),false);assert.equal(s.writes.length,1);
  vm.runInContext(read('assets/js/shared/agent-ui.js').replaceAll('const AgentUI','const AgentUIReloaded'),s.context);
  const reloaded=vm.runInContext('AgentUIReloaded',s.context);
  assert.equal(await reloaded.apply(target),false);assert.equal(s.writes.length,1,'刷新执行器同一计划仍不写入');
  const questionPlan={...plan(s,'student.report.create'),auto:false};assert.equal(await s.ui.apply(questionPlan),false);
  const entry={...plan(s,'student.report.generate'),auto:false};assert(await s.ui.apply(entry));assert.equal(s.writes.length,1);
  console.log('PASS 学生报告：生成一次、打开详情，重复/刷新不再生成；询问仅给入口');

  const teacher=setup('teacher'),tApi=teacher.sandbox.API,pending=deferred();
  tApi.report={list:async()=>({list:[]}),generate:args=>{teacher.writes.push(args);return pending.promise;},detail:async()=>({title:'课程报告',detail:{meta:{},sections:[]}})};
  tApi.setActiveCourse=id=>{tApi.config.activeCourseId=id;};
  vm.runInContext(read('assets/js/teacher/views/report.js'),teacher.context);
  tApi.teacher.structure=async()=>({chapterOptions:[{id:'CH1',name:'第1章 绪论'}]});
  const teacherTask=teacher.ui.apply(plan(teacher,'teacher.report.create',{chapterIds:['CH1'],sections:['整体掌握度','个体预警']}),{auto:true,fromView:'ai'});
  await new Promise(r=>setTimeout(r,120));assert.equal(teacher.writes.length,1);assert.deepEqual(Array.from(teacher.writes[0].classIds),['C1']);
  assert.equal(teacher.writes[0].chapter,'第1章');assert.deepEqual(Array.from(teacher.writes[0].sections),['整体掌握度','个体预警']);
  const button=teacher.body.querySelector('#rgGo');assert(button.disabled);button.click();assert.equal(teacher.writes.length,1);
  pending.resolve({reportId:'TR1',status:'ready'});assert(await teacherTask);assert(teacher.body.querySelector('#exPdf'));
  console.log('PASS 教师报告：实际配置按钮生成当前课程一份报告并打开详情，按钮防重入');

  const canceled=setup('student');const delayed=deferred();
  canceled.sandbox.API.student.report={list:async()=>({list:[]}),generate:()=>delayed.promise,detail:async()=>{throw Error('不应请求过期账号的详情');}};
  vm.runInContext(read('assets/js/student/views/report.js'),canceled.context);
  canceled.sandbox.Router.go('report');const native=vm.runInContext('MyReport.generate()',canceled.context);
  canceled.sandbox.Auth.getSession=()=>({loginStartedAt:'other-login'});delayed.resolve({reportId:'STALE'});
  assert(await native);assert(!canceled.body.querySelector('.overlay'),'登录变化后不打开旧报告');
  console.log('PASS 生成等待中重新登录，不展示旧账号的报告详情');
}

async function questions() {
  const s=setup('teacher');
  let pending=null;
  s.sandbox.API.question={
    genStream:(payload,handlers)=>{
      s.writes.push(payload);
      pending=handlers;
      return Promise.resolve();
    },
    draftPublish:async({draftId})=>{s.writes.push('pub:'+draftId);return {qId:'AI1'};},
    draftUpdate:async()=>({status:'draft',errors:[]}),
    exams:{save:async(p)=>{s.writes.push(p);return {paperId:'EP1',status:'draft',items:p.items};},detail:async()=>({paperId:'EP1',title:'课堂小测',items:[]})},
  };
  const target=plan(s,'teacher.question.create',{kpIds:['K1'],count:6,types:['single'],difficulty:3});
  const slot=s.body.appendChild(new Element('div',{'data-preview-job':target.id,class:'msg__preview-slot'}));
  assert(await s.ui.apply(target,{auto:true,fromView:'ai'}));
  await flush();
  assert.equal(s.writes[0].kpIds[0],'K1');
  assert.equal(s.writes[0].count,6);
  const wrapBefore=s.body.querySelector('#agentPreviewWrap')||s.body.querySelector('#agentPreviewPanel');
  assert(!wrapBefore || wrapBefore.hidden,'生成未完成前不打开预览');
  assert(String(slot.textContent).includes('正在'));
  assert(!slot.querySelector('[data-ap-open]'),'生成中不显示预览按钮');
  const draft={draftId:'D1',status:'draft',payload:{type:'single',question:'栈的特点是？',options:{A:'先进后出',B:'先进先出'},answer:'A',analysis:'栈后进先出。'}};
  pending.onDraft(draft);await flush();
  assert(String(slot.textContent).includes('1 / 6') || String(slot.textContent).includes('正在生成'));
  pending.onDone({count:6});await flush();
  const panel=s.body.querySelector('#agentPreviewWrap')||s.body.querySelector('#agentPreviewPanel');
  assert(panel);assert.equal(panel.hidden,false);
  assert(String(s.body.querySelector('#apBody').textContent).includes('栈的特点'));
  assert(s.body.querySelector('[data-ap-edit]'));
  assert(s.body.querySelector('#apExam'));
  assert(slot.querySelector('[data-ap-open]'),'全部完成后才出现预览按钮');
  s.body.querySelector('#apExam').click();await flush();
  assert.equal(s.writes.at(-1).title,'课堂小测');
  assert.equal(await s.ui.apply(target,{fromView:'ai'}),true,'再次点击只重开预览');
  assert.equal(s.writes.filter(x=>x&&x.kpIds).length,1,'同一计划不重复生成');
  console.log('PASS 教师对话出题：生成中显示进度，全部完成后打开预览，可组成试卷');

  const ask=setup('teacher');
  const askPlan=plan(ask,'teacher.question.create',{kpIds:['K1'],types:['single'],difficulty:3});
  const askSlot=ask.body.appendChild(new Element('div',{'data-preview-job':askPlan.id,class:'msg__preview-slot'}));
  ask.sandbox.API.question={
    genStream:(payload,handlers)=>{
      ask.writes.push(payload);
      Promise.resolve().then(()=>{handlers.onDraft(draft);handlers.onDone({count:payload.count});});
      return Promise.resolve();
    },
    exams:{save:async()=>({paperId:'EP2'})},
  };
  assert(await ask.ui.apply(askPlan,{auto:true,fromView:'ai'}));
  await flush();
  assert.equal(ask.writes.length,0,'未选题量时不能直接生成');
  assert(String(askSlot.textContent).includes('几道'));
  const eight=askSlot.querySelector('[data-preview-count="8"]');
  assert(eight);eight.click();await flush();
  assert.equal(ask.writes[0].count,8);
  const askedPanel=ask.body.querySelector('#agentPreviewWrap')||ask.body.querySelector('#agentPreviewPanel');
  assert(askedPanel);assert.equal(askedPanel.hidden,false);
  console.log('PASS 教师对话出题：未说题量时先出选项，点选后再生成');
}

(async()=>{await practice();await reports();await questions();console.log('全部通过：实际页面代码异步点击回归（DOM 替身，非浏览器实测）');})().catch(e=>{console.error(e);process.exitCode=1;});
