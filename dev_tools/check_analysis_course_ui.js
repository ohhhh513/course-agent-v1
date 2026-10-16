'use strict';
/* 使用真实归因分析脚本，模拟异步请求返回顺序；不是浏览器显示验收。 */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const el={innerHTML:''},requests=[],banks=[],modals=[],errors=[];
let session={user:{userId:'T1'},loginStartedAt:1};
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const context={window:{},Auth:{getSession:()=>session},U:{$:selector=>selector==='#view-analysis'?el:null,$$:()=>[],esc,skeleton:()=>'<loading>',bar:()=>'',stars:()=>''},
 API:{config:{activeCourseId:'A'},analysis:{errors:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))},question:{bank:()=>new Promise((resolve,reject)=>banks.push({resolve,reject}))}},
 Router:{current:'analysis',register(){}},Toast:{warn:(...args)=>errors.push(args),err:(...args)=>errors.push(args)},Monitor:{openProfile(){}},R:{empty:()=>'<empty>'},icon:()=>'',
 Modal:{open(opts){const modal={options:opts,close(){this.closed=true;opts.onClose?.();}};modals.push(modal);opts.onMount?.();return modal;}},
};
vm.createContext(context);vm.runInContext(fs.readFileSync('assets/js/teacher/views/analysis.js','utf8'),context);const analysis=vm.runInContext('Analysis',context);
const data=course=>({topWrongQuestions:[{qId:course+'Q',stem:course+'课程题目',kpId:course+'KP',count:1,wrongRate:100}],commonVsIndividual:{common:[],individual:[]}});
const bank=qId=>({list:[{qId,type:'single',stem:qId,options:[{key:'A',text:'正确项',right:true},{key:'B',text:'干扰项',right:false}],answer:'A',analysis:'解析'}]});
const flush=async()=>{for(let index=0;index<10;index++)await Promise.resolve();};
(async()=>{
 analysis.render();context.API.config.activeCourseId='B';analysis.render();
 requests[1].resolve(data('B'));await flush();requests[0].resolve(data('A'));await flush();
 assert(el.innerHTML.includes('B课程题目')&&!el.innerHTML.includes('A课程题目'));assert.equal(analysis._topWrong[0].qId,'BQ');
 context.API.config.activeCourseId='A';analysis.render();context.API.config.activeCourseId='B';analysis.render();context.API.config.activeCourseId='A';analysis.render();
 requests[4].resolve(data('最新A'));await flush();requests[3].resolve(data('B'));requests[2].resolve(data('旧A'));await flush();assert(el.innerHTML.includes('最新A课程题目'));
 analysis.render();context.API.config.activeCourseId='B';analysis.render();requests[6].resolve(data('B'));await flush();requests[5].reject(new Error('旧课程失败'));await flush();assert(!el.innerHTML.includes('旧课程失败'));
 analysis.openWrongDetail({qId:'BQ',count:1});context.API.config.activeCourseId='A';analysis.render();banks[0].resolve(bank('BQ'));requests[7].resolve(data('A'));await flush();assert.equal(modals.length,0);
 analysis.openWrongDetail({qId:'A1',count:1});analysis.openWrongDetail({qId:'A2',count:1});banks[2].resolve(bank('A2'));await flush();banks[1].resolve(bank('A1'));await flush();assert.equal(modals.length,1);assert(modals[0].options.title.includes('A2'));
 assert(modals[0].options.body.includes('opt is-right')&&modals[0].options.body.includes('opt is-wrong'));
 assert(!modals[0].options.body.includes('错误选项'));assert(!modals[0].options.body.includes('正确答案'));
 assert(modals[0].options.body.includes('选项统计暂不可用')&&!modals[0].options.body.includes('0 人选择'));
 context.API.config.activeCourseId='B';analysis.render();assert(modals[0].closed);assert.equal(analysis._topWrong.length,0);
 session={...session,loginStartedAt:2};requests[8].resolve(data('旧登录'));await flush();assert(!el.innerHTML.includes('旧登录课程题目'));
 analysis.render();context.Router.current='dashboard';requests[9].resolve(data('离开页面'));await flush();assert(!el.innerHTML.includes('离开页面课程题目'));
 context.Router.current='analysis';context.API.config.activeCourseId='';analysis.render();assert(el.innerHTML.includes('尚未创建或选择课程'));
 context.API.config.activeCourseId='B';
 analysis.render();const mixed=data('选择');mixed.topWrongQuestions.unshift({qId:'BLANK',stem:'填空题卡片',count:1,wrongRate:100,mainWrongOption:'B',optionStats:[]});
 mixed.topWrongQuestions[1].optionStats=[{key:'A',count:1,percent:50},{key:'B',count:1,percent:50}];
 requests.at(-1).resolve(mixed);await flush();
 assert.equal((el.innerHTML.match(/主要错项/g)||[]).length,1);
 const blankCard=el.innerHTML.split('data-wrong="0"')[1].split('data-wrong="1"')[0];
 assert(blankCard.includes('填空题卡片')&&!blankCard.includes('主要错项')&&!blankCard.includes('class="an-sep"'));
 for(const type of ['multi','judge','blank']){
  const qId='TYPE_'+type;analysis.openWrongDetail({qId,respondentCount:3,optionStats:[{key:'A',count:2,percent:66.7},{key:'B',count:1,percent:33.3},{key:'C',count:0,percent:0}]});const response=bank(qId);response.list[0].type=type;
  if(type==='multi'){response.list[0].options.push({key:'C',text:'另一正确项',right:true});response.list[0].answer='AC';}
  if(type==='blank'){response.list[0].options=[];response.list[0].answer='填空答案';}
  banks.at(-1).resolve(response);await flush();const body=modals.at(-1).options.body;
  assert(!body.includes('错误选项')&&!body.includes('正确答案'));
  if(type==='blank')assert(body.includes('填空答案')&&!body.includes('is-wrong'));
  else { assert(body.includes('opt is-right')&&body.includes('opt is-wrong'));assert(body.includes('2 人选择 · 66.7%')&&body.includes('1 人选择 · 33.3%')); }
  if(type==='multi')assert(body.includes('0 人选择 · 0%')&&body.includes('多选比例可合计超过 100%'));
 }
 const css=fs.readFileSync('assets/css/app.css','utf8');
 assert(/\.an-wrong-options \.opt\.is-wrong:hover\s*\{[^}]*var\(--danger-soft\)[^}]*var\(--danger\)/.test(css));
 assert(/\.an-wrong-options \.opt\.is-right:hover\s*\{[^}]*var\(--ok-soft\)[^}]*var\(--ok\)/.test(css));
 assert.equal(errors.length,0);
 console.log('PASS A→B及A→B→A过期结果、旧失败响应、新登录及离开页面保护；切课清理错题与弹窗、题目详情旧请求与重复点击顺序保护（DOM 替身）');
 console.log('PASS 红绿配色且不显示答案标签；人数/百分比、多选说明、零选择和缺少统计时不伪造零值；填空保留及悬停 CSS 检查（非浏览器实测）');
 console.log('PASS 填空卡片隐藏主要错项及多余分隔符，选择题卡片保留主要错项（DOM 替身）');
})().catch(error=>{console.error(error);process.exitCode=1;});
