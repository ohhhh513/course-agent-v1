/* 真实共享渲染器：来源链接、危险协议、HTML 与代码隔离，教师菜单与历史显示。 */
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const context=vm.createContext({window:{},console,URL,U:{esc},Router:{register(){}},API:{},
  assistantMark:()=>'',icon:()=>''});
vm.runInContext(fs.readFileSync('assets/js/shared/agent-chat.js','utf8'),context);
context.AgentChatView=context.window.AgentChatView;
const render=context.AgentChatView.mdToHtml;
const source='【网络补充】[Python & deque](https://docs.python.org/3/library/collections.html?q=deque&lang=zh#collections.deque)';
const html=render(source,{escapeHtml:true});
assert.match(html,/<a class="md-link" href="https:\/\/docs.python.org/);
assert.match(html,/q=deque&amp;lang=zh/);assert.doesNotMatch(html,/amp;amp/);
assert.match(html,/target="_blank" rel="noopener noreferrer"/);assert.match(html,/>Python &amp; deque<\/a>/);
for(const href of ['javascript:alert(1)','data:text/html,abc','file:///secret','https://u:p@example.com/a','https://example.com/"onclick=1']){
  assert.doesNotMatch(render(`[来源](${href})`,{escapeHtml:true}),/<a\b/);
}
assert.doesNotMatch(render('`[代码](https://example.com)`',{escapeHtml:true}),/<a\b/);
assert.doesNotMatch(render('```text\n[代码](https://example.com)\n```',{escapeHtml:true}),/<a\b/);
assert.doesNotMatch(render('<img src=x onerror=bad()>\n<script>bad()</script>',{escapeHtml:true}),/<img|<script/);
assert.match(render('**摘要**\n\n- [来源](https://example.com/a_(b))',{escapeHtml:true}),/<strong>摘要<\/strong>/);
vm.runInContext(fs.readFileSync('assets/js/teacher/views/chat.js','utf8'),context);
const teacher=vm.runInContext('TeacherChat',context);
const history=teacher.tpl({role:'ai',content:source,toolLog:[]});
assert.match(history,/<a class="md-link"/);assert.doesNotMatch(history,/&lt;a class/);
assert.doesNotMatch(teacher.tpl({role:'ai',content:'<img src=x onerror=bad()>',toolLog:[]}),/<img src=x/);
const teacherSource=fs.readFileSync('assets/js/teacher/views/chat.js','utf8');
assert.match(teacherSource,/id: 'web_research'/);
assert.doesNotMatch(fs.readFileSync('assets/js/student/views/chat.js','utf8'),/web_research/);
assert.doesNotMatch(fs.readFileSync('assets/js/admin/views/assistant.js','utf8'),/web_research/);
console.log('[ok] 搜索来源可点击、URL 参数保留、新窗口隔离、危险协议/HTML 不执行、代码中不生成链接');
console.log('[ok] 教师历史消息安全渲染，联网菜单仅教师可见');
