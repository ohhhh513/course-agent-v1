'use strict';
/* 运行真实教师试卷与详情脚本；DOM 替身不替代浏览器显示验收。 */
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const ids=new Map(), modals=[], documentClicks=new Set(), calls=[];
class Element {
  constructor(){this.isConnected=true;this.disabled=false;this.hidden=false;this.value='';this.dataset={};this.attributes={};this.events={};this.children=[];this._html='';this.textContent='';}
  set innerHTML(html){
    this._html=html;this.children=[];
    for(const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)){
      const child=new Element();child.id=match[1];child.hidden=/\bhidden\b/.test(match[0]);ids.set('#'+child.id,child);this.children.push(child);
    }
    for(const match of html.matchAll(/<button[^>]*data-exam-(student|rank-user)="([^"]*)"[^>]*>/g)){
      const id=match[0].match(/\bid="([^"]+)"/),child=id?ids.get('#'+id[1]):new Element();
      child.dataset[match[1]==='student'?'examStudent':'examRankUser']=match[2];if(!id)this.children.push(child);
    }
  }
  get innerHTML(){return this._html;}
  querySelector(selector){if(selector==='.teacher-exam-student-search')return {contains:target=>target===ids.get('#teacherExamStudentSearch')};return ids.get(selector)||null;}
  querySelectorAll(selector){if(selector==='[data-exam-student]')return this.children.filter(child=>child.dataset.examStudent);if(selector==='[data-exam-rank-user]')return this.children.filter(child=>child.dataset.examRankUser);return [];}
  addEventListener(type,fn){(this.events[type]||=[]).push(fn);}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];}
  closest(selector){return selector==='[data-exam-student]'&&this.dataset.examStudent?this:null;}
  scrollIntoView(){}
  focus(){return this.emit('focus');}
  async emit(type,extra={}){const event={target:this,currentTarget:this,preventDefault(){},...extra};for(const fn of this.events[type]||[])await fn(event);if(this['on'+type])await this['on'+type](event);}
  click(){return this.emit('click');}
}
const box=new Element();ids.set('#qBody',box);
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const stats={paperId:'EP1',title:'教师统计',summary:{submittedCount:2,averageScore:75,highestScore:100,lowestScore:50},classes:['A班','B班'],
 students:Array.from({length:7},(_,index)=>({userId:'S'+index,name:index===6?'李七':'王'+index,className:'A班',status:index<2?'finished':'pending'})),
 questions:[{number:1,type:'single',stem:'统计题',score:100,chapter:'第一章',respondentCount:2,correctCount:1,unansweredCount:0,answer:'A',analysis:'解析',options:[{key:'A',text:'正确项',right:true,count:1},{key:'B',text:'错误项',right:false,count:1}]}]};
let session={user:{userId:'T1'},loginStartedAt:1},failDetail=false,failRanking=false;
const detail=id=>({paperId:'EP1',student:{userId:id,name:'王'+id.slice(1),className:'A班',status:id==='S6'?'pending':'finished'},
 score:id==='S6'?null:50,totalScore:100,durationSeconds:id==='S6'?null:125,ranking:{rank:id==='S6'?null:2,classSize:7},
 items:id==='S6'?[]:[{type:'single',stem:'学生题目',score:100,earnedScore:0,chapter:'第一章',myAnswer:'B',correctAnswer:'A',correct:false,analysis:'个人解析',options:[{key:'A',text:'正确项'},{key:'B',text:'错误项'}]}]});
const ranking={className:'A班',classes:['A班','B班'],classSize:7,testedCount:2,list:[{userId:'S0',name:'王0',rank:1,score:100,totalScore:100,durationSeconds:90,status:'finished'},
 {userId:'S6',name:'李七',rank:null,score:null,durationSeconds:null,status:'pending'}]};
const api={list:async()=>({list:[{paperId:'EP1',title:'已发布',status:'published',questionCount:1,totalScore:100,assignedScore:100,issues:[],updatedAt:'2026-10-16'},
 {paperId:'EP2',title:'草稿',status:'draft',questionCount:0,totalScore:100,assignedScore:0,issues:[],updatedAt:'2026-10-16'}]}),
 results:async id=>{calls.push(['results',id]);return structuredClone(stats);},
 studentResult:async(id,studentId)=>{calls.push(['student',id,studentId]);if(failDetail)throw new Error('个人加载失败');return detail(studentId);},
 ranking:async(id,className)=>{calls.push(['ranking',id,className]);if(failRanking)throw new Error('排名加载失败');return structuredClone(ranking);},
};
const sandbox={window:{addEventListener(){},scrollTo(){}},document:{addEventListener(type,fn,opts){if(type==='click'){documentClicks.add(fn);opts?.signal?.addEventListener('abort',()=>documentClicks.delete(fn));}}},
 U:{$:(selector,parent)=>parent?parent.querySelector(selector):ids.get(selector)||null,esc},
 Auth:{getSession:()=>session},Question:{tab:'exam'},API:{config:{activeCourseId:'C1'},question:{exams:api}},Router:{current:'question',beforeNavigate:null},
 Toast:{ok(){},warn(){}},icon:()=>'',AbortController,CSS:{escape:value=>value},Modal:{open(opts){const el=new Element();el.innerHTML=opts.body;const modal={el,close(){if(!el.isConnected)return;el.isConnected=false;opts.onClose?.();}};modals.push(modal);opts.onMount?.(el,modal.close);return modal;}}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('assets/js/teacher/views/exams.js','utf8'),sandbox);
vm.runInContext(fs.readFileSync('assets/js/teacher/views/exam-results.js','utf8'),sandbox);
const teacher=vm.runInContext('TeacherExams',sandbox),results=sandbox.window.TeacherExamResults;sandbox.TeacherExamResults=results;
const flush=async()=>{for(let index=0;index<16;index++)await Promise.resolve();};
(async()=>{
 teacher.courseId='C1';await teacher.list();
 assert.equal((ids.get('#examList').innerHTML.match(/data-exam-results=/g)||[]).length,1,'草稿不提供作答详情');
 await ids.get('#examList').emit('click',{target:{closest:selector=>selector==='[data-exam-results]'?{dataset:{examResults:'EP1'}}:null}});await flush();
 assert.equal(calls[0][0],'results');let body=ids.get('#teacherExamResultsBody');
 assert(body.innerHTML.includes('提交人数')&&body.innerHTML.includes('平均分')&&body.innerHTML.includes('最高分')&&body.innerHTML.includes('最低分'));
 assert(body.innerHTML.includes('is-right')&&body.innerHTML.includes('is-wrong')&&body.innerHTML.includes('1 人选择'));
 const input=ids.get('#teacherExamStudentSearch'),options=ids.get('#teacherExamStudentOptions');
 await input.focus();assert.equal(options.querySelectorAll('[data-exam-student]').length,7);assert(!options.hidden);
 input.value='王';await input.emit('input');assert.equal(options.querySelectorAll('[data-exam-student]').length,6);assert(options.innerHTML.includes('bank-hit'));
 await input.emit('keydown',{key:'ArrowDown'});assert.equal(input.attributes['aria-activedescendant'],'teacherExamStudentOption0');
 await input.emit('keydown',{key:'Escape'});assert(options.hidden);
 input.value='李七';await input.emit('input');assert.equal(options.querySelectorAll('[data-exam-student]').length,1);
 await options.emit('click',{target:options.querySelectorAll('[data-exam-student]')[0]});await flush();
 assert(body.innerHTML.includes('未测验')&&body.innerHTML.includes('暂无作答记录'));assert(options.hidden);
 await results.selectStudent('S0');assert(body.innerHTML.includes('50 / 100')&&body.innerHTML.includes('2 分 5 秒')&&body.innerHTML.includes('2/7'));
 assert(body.innerHTML.includes('学生选择')&&body.innerHTML.includes('个人解析')&&body.innerHTML.includes('学生答案'));
 await ids.get('#teacherExamOverview').click();assert(body.innerHTML.includes('提交人数'));
 failDetail=true;await results.selectStudent('S0');assert(body.innerHTML.includes('个人加载失败'));failDetail=false;await ids.get('#teacherExamStudentRetry').click();assert(body.innerHTML.includes('学生答案'));
 results.openRanking();await flush();let modal=modals.at(-1),content=ids.get('#teacherExamRankingContent');assert(content.innerHTML.includes('未测验'));
 results.openRanking();assert.equal(modals.at(-1),modal);
 ids.get('#teacherExamRankClass').value='B班';await ids.get('#teacherExamRankClass').emit('change');assert.equal(calls.at(-1)[2],'B班');
 await content.querySelectorAll('[data-exam-rank-user]')[0].click();await flush();assert(!modal.el.isConnected);assert(body.innerHTML.includes('学生答案'));
 failRanking=true;results.openRanking();await flush();assert(ids.get('#teacherExamRankingContent').innerHTML.includes('排名加载失败'));
 failRanking=false;await ids.get('#teacherExamRankingRetry').click();modals.at(-1).close();
 console.log('PASS 已发布试卷详情入口、整卷四项统计、选项人数和红绿样式、实时姓名筛选、竖列与键盘选择、未测验/个人三项数据/答案解析、班级切换和榜单学生入口、失败重试');

 const normalDetail=api.studentResult;let resolveFirst,resolveSecond;
 api.studentResult=()=>new Promise(resolve=>resolveFirst=resolve);const first=results.selectStudent('S0');
 api.studentResult=()=>new Promise(resolve=>resolveSecond=resolve);const second=results.selectStudent('S1');
 resolveSecond(detail('S1'));await second;resolveFirst(detail('S0'));await first;assert.equal(results.student.userId,'S1');
 api.studentResult=normalDetail;
 let resolveStats;const normalStats=api.results;api.results=()=>new Promise(resolve=>resolveStats=resolve);const stale=results.open('EP1');
 sandbox.API.config.activeCourseId='C2';resolveStats(stats);await stale;assert.equal(results.data,null);
 sandbox.API.config.activeCourseId='C1';api.results=normalStats;await results.open('EP1');assert.equal(documentClicks.size,1);
 await results.open('EP1');assert.equal(documentClicks.size,1,'重绘清理全局监听');
 const originalContext=results.context;session={...session,loginStartedAt:2};assert(!results.active());session={...session,loginStartedAt:1};assert.equal(results.context,originalContext);
 results.openRanking();await flush();sandbox.Router.beforeNavigate('dashboard');assert.equal(documentClicks.size,0);assert(!modals.at(-1).el.isConnected);
 const css=fs.readFileSync('assets/css/app.css','utf8');
 assert(/\.teacher-exam-student-options\s*\{[^}]*max-height:\s*222px;[^}]*overflow-y:\s*auto/s.test(css));
 assert(/\.teacher-exam-student-option\s*\{[^}]*height:\s*44px/s.test(css));
 assert((222-2)/44===5); // 面板上下各 1px 边框，内容恰好五行。
 console.log('PASS 切课程/重新登录/切学生旧响应保护、离开关闭榜单、重绘监听清理，以及最多五行与滚动条 CSS 约束（非浏览器排版验收）');
})().catch(error=>{console.error(error);process.exitCode=1;});
