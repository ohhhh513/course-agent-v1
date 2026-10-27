/* 检查完整模板的生成规则、边界长度和可恢复配置；可导出真实问答所用的草稿。 */
'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const context = vm.createContext({console});
vm.runInContext(fs.readFileSync('assets/js/shared/skill-designer.js','utf8'),context);
const designer = vm.runInContext('SkillDesigner',context);
const limits = {name:40,purpose:300,steps:3000,outputFormat:1000,example:2000};
assert.equal(designer.templates.length,7);
const bases = new Set();
for(const template of designer.templates){
  bases.add(template.base);
  const values = designer.defaults(template);
  const initial = designer.emptyValues(template);
  for (const key of Object.keys(designer.textLimits)) assert.equal(initial[key], '', `${template.id} ${key} 新建时应为空`);
  for (const key of ['teachingStyle','pace','answerPolicy']) assert.equal(initial[key], '', `${key} 应由教师选择`);
  for (const key of ['depth','evidence','check','layout','tone','length','missingInfo']) assert.equal(initial[key],values[key],`${key} 保留更多教学细节的推荐值`);
  assert.equal(designer.compile('',template.id,initial).builder.values.teachingStyle,'','未选择时不能悄悄写入默认值');
  const payload = designer.compile(template.name,template.id,values);
  assert.equal(payload.baseSkillId,template.base);
  assert.equal(payload.builder.mode,'guided');
  assert.equal(payload.builder.templateId,template.id);
  assert(payload.steps.includes('流程衔接')&&payload.steps.includes('不代提交练习')&&payload.steps.includes('不擅自保存'));
  assert(payload.steps.includes(template.flow[0])&&payload.steps.includes(template.flow.at(-1)));
  assert(!JSON.stringify(payload).includes('undefined'));
  for(const [key,limit] of Object.entries(limits))assert(payload[key].length<=limit,`${template.id} ${key}`);
  for(const [key,options] of Object.entries(designer.options))for(const choice of options){
    const changed=designer.compile(template.name,template.id,{...values,[key]:choice[0]});
    assert((changed.steps+'\n'+changed.outputFormat).includes(choice[2]),`${template.id} ${key} should affect rules`);
  }
  const filled={...values};
  for(const [key,limit] of Object.entries(designer.textLimits))filled[key]='字'.repeat(limit);
  const largest=designer.compile('字'.repeat(40),template.id,filled);
  for(const [key,limit] of Object.entries(limits))assert(largest[key].length<=limit,`完整填空超限：${template.id} ${key} ${largest[key].length}`);
  const restored=designer.compile(payload.name,payload.builder.templateId,payload.builder.values);
  assert.equal(JSON.stringify(restored),JSON.stringify(payload));
}
assert.deepEqual([...bases].sort(),['course_qa','mastery','practice','resource','wrong_review'].sort());
assert.equal(new Set(designer.audiences).size,designer.audiences.length);
assert(designer.audiences.length>=4&&designer.audiences.every(text=>text.length<=40));
const wrong=designer.compile('错题', 'wrong',designer.defaults(designer.templates.find(template=>template.id==='wrong')));
assert(wrong.steps.includes('最近一次作答')&&wrong.steps.includes('没有作答记录时明确说明'));
const mastery=designer.compile('学情', 'mastery',designer.defaults(designer.templates.find(template=>template.id==='mastery')));
assert(mastery.steps.includes('不猜测分数')&&mastery.steps.includes('只查询其本人'));
console.log('[ok] 七个完整教学模板覆盖五种基础技能，流程、真实数据和学生操作边界完整');
console.log('[ok] 所有教学选项都会进入对应规则，最大填空长度满足现有接口限制');
console.log('[ok] 模板选项可以恢复并生成相同规则；错题/学情模板不编造个人数据');
console.log('[ok] 新建文字和主要选择项留空，更多教学细节保留推荐值，学生对象选项满足接口限制');
if(process.argv[2]==='--export'){
  if(!process.argv[3])throw Error('缺少导出路径');
  const template=designer.templates[0];
  const payload=designer.compile('引导式讲题验证',template.id,{...designer.defaults(template),topic:'栈和队列',extra:'每轮回答的第一行固定写：引导模式已启用。'});
  fs.writeFileSync(process.argv[3],JSON.stringify(payload,null,2));
  console.log('已导出真实模型验证草稿：'+process.argv[3]);
}
