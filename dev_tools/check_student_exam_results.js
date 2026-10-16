'use strict';
/* 运行真实学生试卷脚本；DOM 替身检查逻辑，不作为浏览器显示验收。 */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const ids = new Map(), modals = [], calls = [], notices = [];
class Element {
  constructor() { this.isConnected=true; this.disabled=false; this.dataset={}; this.events={}; this.children=[]; this.textContent=''; this._html=''; }
  set innerHTML(html) {
    this._html=html; this.children=[];
    for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
      const child=new Element();ids.set('#'+match[1],child);this.children.push(child);
    }
    for (const match of html.matchAll(/<button[^>]+data-exam-(start|result)="([^"]*)"[^>]*>/g)) {
      const child=new Element();child.dataset[match[1]==='start'?'examStart':'examResult']=match[2];this.children.push(child);
    }
  }
  get innerHTML() { return this._html; }
  querySelector(selector) { return ids.get(selector)||null; }
  querySelectorAll(selector) {
    if (selector==='[data-exam-start]') return this.children.filter(el=>'examStart' in el.dataset);
    if (selector==='[data-exam-result]') return this.children.filter(el=>'examResult' in el.dataset);
    return [];
  }
  addEventListener(type, handler) { (this.events[type]||=[]).push(handler); }
  async click() { if(this.disabled)return;for(const handler of this.events.click||[])await handler({target:this,currentTarget:this}); }
}
const box=new Element(),list=new Element();ids.set('#pBody',box);ids.set('#examPaperList',list);
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let session={user:{userId:'S1'},loginStartedAt:1};
const result={attemptId:'EA1',paperId:'EP1',title:'阶段测验',score:50,totalScore:100,durationSeconds:125,correct:1,total:2,accuracy:50,
 ranking:{rank:2,classSize:32,className:'测试班'},items:[
  {stem:'第一题',chapter:'第一章',type:'single',score:50,earnedScore:50,correct:true,myAnswer:'A',correctAnswer:'A',analysis:'第一题解析',options:[{key:'A',text:'选项一'}]},
  {stem:'第二题',chapter:'第二章',type:'single',score:50,earnedScore:0,correct:false,myAnswer:'B',correctAnswer:'A',analysis:'第二题解析',options:[]},
 ]};
let failRanking=false;
const ranking={rank:2,classSize:3,className:'测试班',testedCount:2,list:[
 {name:'第一名',rank:1,score:100,totalScore:100,durationSeconds:90,status:'finished'},
 {name:'<我的姓名>',rank:2,score:50,totalScore:100,durationSeconds:125,status:'finished',isMe:true},
 {name:'未答同学',rank:null,status:'pending'},
]};
const practice={
 examResult:async p=>{calls.push(['detail',p]);return structuredClone(result);},
 examRanking:async p=>{calls.push(['ranking',p]);if(failRanking)throw new Error('临时网络错误');return structuredClone(ranking);},
 startExam:async()=>{calls.push(['start']);throw new Error('本检查不应开考');},
};
const sandbox={window:{addEventListener(){},scrollTo(){}},document:{addEventListener(){},querySelector:selector=>ids.get(selector)||null},
 U:{$:(selector,parent)=>parent?parent.querySelector(selector):ids.get(selector)||null,$$:(selector,parent)=>(parent||box).querySelectorAll(selector),esc},
 Auth:{getSession:()=>session},API:{config:{activeCourseId:'C1'},practice},
 StudentPractice:{tab:'exam'},Router:{current:'practice',views:{},beforeNavigate:null},
 Toast:{warn:(...args)=>notices.push(args),error:(...args)=>notices.push(args)},icon:()=>'',
 clearInterval(){},clearTimeout(){},setInterval(){},setTimeout(){},CSS:{escape:value=>value},
 Modal:{open(opts){const el=new Element();el.innerHTML=opts.body;const modal={el,close(){if(!el.isConnected)return;el.isConnected=false;opts.onClose?.();}};modals.push(modal);opts.onMount?.(el,modal.close);return modal;}},
};
sandbox.window.StudentPractice=sandbox.StudentPractice;
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('assets/js/student/views/exams.js','utf8'),sandbox);
const exams=sandbox.window.StudentExams;
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
(async()=>{
 exams.papers=[{paperId:'EP1',title:'阶段测验',totalScore:100,questionCount:2,attemptCount:1,lastAttemptId:'EA1',lastScore:50,lastAccuracy:50,knowledgePoints:[]},
  {paperId:'EP2',title:'新试卷',totalScore:100,questionCount:1,attemptCount:0,knowledgePoints:[]},
  {paperId:'EP3',title:'未完成试卷',totalScore:100,questionCount:1,attemptCount:0,inProgress:true,knowledgePoints:[]}];
 exams.renderPaperCards();assert(list.innerHTML.includes('查看详细'));assert(!list.innerHTML.includes('重新测验'));
 assert.equal(list.querySelectorAll('[data-exam-start]').length,2);assert.equal(list.querySelectorAll('[data-exam-result]').length,1);
 await list.querySelectorAll('[data-exam-result]')[0].click();
 assert.equal(calls[0][0],'detail');assert.equal(calls[0][1].attemptId,'EA1');assert(!calls.some(call=>call[0]==='start'));
 assert(box.innerHTML.includes('50 / 100'));assert(box.innerHTML.includes('2 分 5 秒'));assert(box.innerHTML.includes('2/32'));
 const stats=box.innerHTML.match(/<div class="exam-result-stats">([\s\S]*?)<\/div><\/div>/)[1];
 assert.equal((stats.match(/<span>/g)||[]).length,3);assert(stats.includes('分数')&&stats.includes('时长')&&stats.includes('班级排名'));
 assert(box.innerHTML.includes('第一题解析')&&box.innerHTML.includes('第二题解析'));assert(!box.innerHTML.includes('examRetake'));
 assert(box.innerHTML.includes('你的答案')&&box.innerHTML.includes('正确答案'));
 assert(box.innerHTML.indexOf('id="examBackList"')<box.innerHTML.indexOf('class="exam-result-stats"'));
 assert.equal((box.innerHTML.match(/id="examBackList"/g)||[]).length,1);
 const originalBack=exams.backToList;let returned=0;exams.backToList=()=>returned++;
 await ids.get('#examBackList').click();assert.equal(returned,1);exams.backToList=originalBack;
 await ids.get('#examViewRanking').click();await flush();
 const modal=modals.at(-1),content=ids.get('#examRankingContent');
 assert(content.innerHTML.includes('&lt;我的姓名&gt;'));assert(content.innerHTML.includes('exam-ranking-me'));
 assert(content.innerHTML.indexOf('第一名')<content.innerHTML.indexOf('未答同学'));assert(content.innerHTML.includes('未测验'));
 assert.equal(ids.get('#examClassRank').textContent,'2/3');
 exams.openRanking();assert.equal(modals.at(-1),modal);modal.close();
 console.log('PASS 已完成试卷只读详情入口、未完成继续入口、顶部三项数据、逐题答案解析、右上角排名、自己高亮及未测验展示');

 failRanking=true;exams.openRanking();await flush();assert(ids.get('#examRankingContent').innerHTML.includes('排名加载失败'));
 failRanking=false;await ids.get('#examRankingRetry').click();assert(ids.get('#examRankingContent').innerHTML.includes('第一名'));modals.at(-1).close();
 const normalDetail=practice.examResult;
 for(const change of [()=>{sandbox.API.config.activeCourseId='C2';},()=>{session={...session,loginStartedAt:2};},()=>{exams._cancelReads();},()=>{sandbox.StudentPractice.tab='wrong';}]){
  sandbox.API.config.activeCourseId='C1';session={user:{userId:'S1'},loginStartedAt:1};sandbox.StudentPractice.tab='exam';
  let resolve;practice.examResult=()=>new Promise(done=>resolve=done);const before=exams.result,pending=exams.viewResult('EA1');
  change();resolve(structuredClone(result));await pending;assert.equal(exams.result,before);
 }
 practice.examResult=normalDetail;sandbox.API.config.activeCourseId='C1';sandbox.StudentPractice.tab='exam';
 await exams.viewResult('EA1');
 let resolveRanking;const normalRanking=practice.examRanking;practice.examRanking=()=>new Promise(resolve=>resolveRanking=resolve);
 exams.openRanking();const staleModal=modals.at(-1);sandbox.API.config.activeCourseId='C2';resolveRanking(ranking);await flush();assert(!staleModal.el.isConnected);
 sandbox.API.config.activeCourseId='C1';practice.examRanking=normalRanking;
 exams.openRanking();await flush();const leaving=modals.at(-1);await exams.beforeCourseChange();assert(!leaving.el.isConnected);
 console.log('PASS 排名失败可重试、重复点击防堆叠、切课程/重新登录/切标签/取消请求的过期响应保护及离开时关闭榜单');
 console.log('全部通过：学生试卷详情与班级排名逻辑检查（DOM 替身，非浏览器实测）。');
})().catch(error=>{console.error(error);process.exitCode=1;});
