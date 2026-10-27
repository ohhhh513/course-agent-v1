'use strict';

/* 引导式配置只生成普通文字规则；builder 用于恢复编辑选项，不授予工具权限。 */
const SkillDesigner = (() => {
  const templates = [
    { id: 'guided', base: 'course_qa', name: '循序渐进讲题', label: '一步一步引导', description: '学生先思考，老师式地逐步给提示。', goal: '让学生说清思路，能够自己完成推理，而不是只记住结论。', style: 'questions', pace: 'one',
      question: '这道题我不知道从哪里开始，能一步一步引导我吗？',
      flow: ['先确认学生的问题、已尝试的思路和卡住的位置，已经说清的信息不重复询问。', '定位本课程对应的知识点或题目，需要讲解概念时先查课程资料。', '从学生已经理解的部分开始，只推进当前最必要的一小步，给适量提示。', '等待学生回答后，先判断其理解是否正确；有误时指出原因并换一种提示，不直接替他完成。', '学生能够自行解释后，再归纳可复用的方法，并用一个小问题检验是否理解。'] },
    { id: 'concept', base: 'course_qa', name: '概念讲解助手', label: '把概念讲明白', description: '定义、生活例子和易混点讲清楚。', goal: '理解概念的含义、适用条件和易混点，并能用自己的话说明。', style: 'explain', pace: 'short_steps',
      question: '我总是分不清这两个概念，能用生活中的例子解释吗？',
      flow: ['确认学生要理解的概念和目前不明白的地方。', '定位本课知识点，检索教材或课件，先用课程资料解释定义和适用条件。', '按学生基础拆解关键术语，配一个具体例子，并说明例子与概念的对应关系。', '指出最容易混淆的一点，必要时做对照，说明什么情况下不能套用。', '请学生用自己的话复述或判断一个小例子，再根据回答补充。'] },
    { id: 'example', base: 'course_qa', name: '例题陪练助手', label: '陪学生分析例题', description: '读题、找条件、讲方法，再让学生尝试。', goal: '学会识别题目条件、选择方法，并把方法迁移到相似问题。', style: 'examples', pace: 'one',
      question: '我会背概念，但遇到题目就不会分析，应该先看什么？',
      flow: ['先拿到题目原文或定位系统中的真实题目；题目不完整时先请学生补充。', '让学生指出已知条件和要求解决的问题，核对有无遗漏，不编造题面条件。', '结合本课资料说明为什么选择当前方法，并演示一个关键步骤。', '把下一步交给学生尝试，依据其回答纠正思路，不代提交练习或一次给出刷题答案。', '归纳本题可复用的判断方法，并指出与相似题的区别。'] },
    { id: 'wrong', base: 'wrong_review', name: '错题复盘助手', label: '带学生复盘错题', description: '对照真实作答，找到错因并纠正。', goal: '发现自己出错的具体原因，修正理解，并学会检查同类错误。', style: 'questions', pace: 'one',
      question: '这道题我为什么会选错？能帮我找出问题吗？',
      flow: ['先定位系统中的真实题目，再读取当前学生本人最近一次作答。', '只根据实际记录说明学生选了什么；没有作答记录时明确说明，按题面做一般讲解。', '请学生说明当时的判断理由，区分概念误解、条件遗漏、方法选择或推理错误。', '结合课程资料，针对真正的错误点给提示，让学生自己修正关键一步。', '请学生总结一个以后可用的检查方法；需要重练时提供入口，由学生确认，不代答或代提交。'] },
    { id: 'mastery', base: 'mastery', name: '学情理解助手', label: '解释个人学情', description: '看真实数据，解释薄弱点和下一步。', goal: '读懂自己的掌握情况和预警，知道当前最需要解决的问题。', style: 'explain', pace: 'short_steps',
      question: '我现在最薄弱的是哪里？这些预警代表什么？',
      flow: ['确认学生希望了解掌握情况、预警还是某个知识点，并只查询其本人的课程学情。', '调用系统查询能力，使用真实数据说明情况，不猜测分数、正确率、排名或预警。', '按问题范围解释最值得关注的几项，说明指标含义，不给没有数据依据的归因。', '帮助学生把薄弱点对应到可理解的学习问题，给一个可执行的下一步。', '数据不足时明确说明；需要查看页面或练习时给真实入口，不擅自跳转。'] },
    { id: 'practice', base: 'practice', name: '复习与练习教练', label: '安排复习与练习', description: '结合目标和薄弱点，给可执行的小计划。', goal: '明确练习重点，按自己的时间完成一段可执行的复习或练习。', style: 'explain', pace: 'short_steps',
      question: '我今天只有二十分钟，应该先复习什么、怎么练？',
      flow: ['确认复习范围、可用时间和学习目标，已提供的信息不重复询问。', '在有本人真实学情时结合薄弱点和预警安排重点；没有数据时说明并依据学生提供的信息规划。', '将复习和练习分成少量可执行的小任务，解释先后顺序与每项完成标准。', '给出合适的练习入口；只有学生明确要求打开时才跳转，其余由学生点击确认。', '引导学生完成后反思卡点，再调整下一步；不虚构完成记录，不代答、刷分或提交。'] },
    { id: 'resource', base: 'resource', name: '课程资料导航', label: '帮学生找资料', description: '按知识点定位，告诉学生先看什么。', goal: '找到当前问题对应的真实课程资料，并知道应该关注哪一部分。', style: 'explain', pace: 'short_steps',
      question: '我想复习这个知识点，应该到哪里找课件和视频？',
      flow: ['确认学生想学习的内容或材料类型，需要时只询问最必要的补充信息。', '定位当前课程的章节或知识点，不自行编造章节、资源名称或链接。', '通过系统提供的真实入口帮助学生查找资料，说明该材料与学习目标的关系。', '给一个简明的阅读或观看顺序，提醒重点关注的内容，不声称已经替学生看完。', '工具没有找到资料时如实说明；默认给按钮，由学生决定是否打开。'] },
  ];
  const options = {
    teachingStyle: [ ['questions', '多问少讲，逐步引导', '先问一个关键问题，再依据回答给提示。'], ['explain', '先讲清，再让学生尝试', '先说明关键概念或方法，再留一步让学生完成。'], ['examples', '先给例子，再归纳规律', '从容易理解的例子入手，再联系本课概念。'] ],
    pace: [ ['one', '每轮只推进一步', '讲完当前一步就停下，等待学生回答。'], ['short_steps', '每轮两三小步', '分小段讲解，末尾确认学生是否理解。'], ['complete', '先给完整框架', '先给整体思路，详细推导按学生需要继续。'] ],
    answerPolicy: [ ['after_attempt', '先思考，再讲思路', '先请学生尝试；依据其思路讲解，不代答或提交。'], ['hints', '以提示为主', '不给整套答案，先给方向，必要时再补一个关键步骤。'], ['concept', '侧重概念，不替学生解整题', '用概念和相似例子帮助理解，把原题留给学生完成。'] ],
    depth: [ ['basic', '从基础开始', '解释必要术语，少用未经解释的公式。'], ['standard', '按本课正常难度', '覆盖本课必要概念、推理和使用条件。'], ['advanced', '适当追问与迁移', '基础理解正确后再讨论边界、比较或迁移问题。'] ],
    evidence: [ ['course_first', '以本课资料为主（推荐）', '先使用本课教材和课件；补充常识需标为【补充】非课程原文。'], ['course_only', '只依据本课资料', '资料不足就说明不足，不用课外推测补齐。'], ['marked_extra', '允许明确标注的补充', '课程知识仍先查本课资料；课外解释要与原文明确区分。'] ],
    check: [ ['question', '问一个小问题', '用一个与本轮内容相关的问题确认理解。'], ['retell', '请学生用自己的话复述', '听完复述后再判断哪里需要补充。'], ['compare', '让学生判断或比较一个例子', '给一个简短情境，让学生说明判断理由。'] ],
    layout: [ ['steps', '按小步骤组织', '使用少量编号，每步说明一个重点。'], ['dialogue', '像老师对话一样', '自然分段，不堆很多小标题，每轮只留一个主要问题。'], ['bullets', '重点清单', '先说结论，再列必要的依据或行动。'] ],
    tone: [ ['patient', '耐心、具体', '肯定学生已有的思路，再说明需要修正的部分。'], ['concise', '直接、简洁', '直说重点，减少铺垫和重复。'], ['encourage', '鼓励学生尝试', '反馈具体努力，不空泛表扬，也不因答错责备学生。'] ],
    length: [ ['short', '简短，一屏内读完', '优先用三至五句话表达本轮重点。'], ['normal', '适中，分两三小段', '说明必要理由和例子，避免重复。'], ['detailed', '较详细，但分步展开', '交代条件、原因和例子，按所选节奏推进，不一次堆完所有细节。'] ],
    missingInfo: [ ['ask', '先问最必要的信息', '缺题面、范围或目标时，先问一个能继续处理的关键问题。'], ['limited', '先回答有依据的部分', '说明信息缺口，只回答能够确定的内容，不编造缺失信息。'] ],
  };
  const textLimits = { audience: 40, topic: 80, goal: 140, extra: 600, exampleQuestion: 240, exampleAnswer: 1200 };
  const primaryChoices = ['teachingStyle', 'pace', 'answerPolicy'];
  const audiences = ['刚接触本课程的学生', '已学过基础、需要巩固的学生', '基础较弱、需要更多提示的学生', '已有一定基础、希望拓展的学生', '即将考试、需要系统复习的学生', '本课程全体学生'];
  const errorsFor = { name: '请填写技能名称', templateId: '请选择教学模板', audience: '请选择适用的学生', goal: '请填写学习目标', teachingStyle: '请选择辅导方式', pace: '请选择讲解节奏', answerPolicy: '请选择答题处理方式', baseSkillId: '请选择基础技能', purpose: '请填写用途', steps: '请填写处理步骤' };
  const byId = id => templates.find(template => template.id === id) || templates[0];
  function defaults(template) {
    return { audience: '正在学习本课程的学生', topic: '', goal: template.goal, extra: '', exampleQuestion: '', exampleAnswer: '',
      teachingStyle: template.style, pace: template.pace, answerPolicy: 'after_attempt', depth: 'standard', evidence: 'course_first', check: 'question', layout: 'steps', tone: 'patient', length: 'normal', missingInfo: 'ask' };
  }
  function valuesFor(template, incoming = {}) {
    const values = defaults(template);
    for (const key of Object.keys(textLimits)) if (typeof incoming[key] === 'string') values[key] = incoming[key];
    for (const key of Object.keys(options)) if (incoming[key] === '' || options[key].some(option => option[0] === incoming[key])) values[key] = incoming[key];
    return values;
  }
  function emptyValues(template) {
    return { ...defaults(template), audience: '', goal: '', teachingStyle: '', pace: '', answerPolicy: '' };
  }
  const rule = (key, value) => options[key].find(option => option[0] === value)?.[2] || '';
  function compile(name, templateId, incoming) {
    const template = byId(templateId), values = valuesFor(template, incoming);
    const scope = values.topic.trim() || '学生本轮询问的本课程内容';
    const lines = [
      `适用对象：${values.audience.trim() || '本课程学生'}。学习范围：${scope}。`,
      `学习目标：${values.goal.trim()}。`, '处理流程：',
      ...template.flow.map((text, index) => `${index + 1}. ${text}`),
      '流程衔接：以上是可跨多轮完成的整体流程，按所选节奏推进，不要求一轮全部走完；已确认的信息不重复追问。',
      `辅导方式：${rule('teachingStyle', values.teachingStyle)}`,
      `推进节奏：${rule('pace', values.pace)}`,
      `答题边界：${rule('answerPolicy', values.answerPolicy)}该边界优先于讲解风格，不代提交练习。`,
      `讲解深度：${rule('depth', values.depth)}`,
      `资料依据：${rule('evidence', values.evidence)}`,
      `信息不足时：${rule('missingInfo', values.missingInfo)}`,
      `理解检查：${rule('check', values.check)}只围绕本轮内容，每轮最多留下一个核心提问，不重复已经回答的问题。`,
      '数据与操作：学情、题目、资料和完成情况必须有真实依据；保持当前学生和课程范围；不擅自保存、提交或跳转页面。',
    ];
    if (values.extra.trim()) lines.push('教师补充要求：' + values.extra.trim());
    const example = [values.exampleQuestion.trim() ? '示例提问：' + values.exampleQuestion.trim() : '', values.exampleAnswer.trim() ? '期望回答示例：' + values.exampleAnswer.trim() : ''].filter(Boolean).join('\n');
    return { name: name.trim(), baseSkillId: template.base,
      purpose: `面向${values.audience.trim() || '本课程学生'}，围绕${scope}，${values.goal.trim()}`,
      steps: lines.join('\n'), outputFormat: [rule('layout', values.layout), rule('tone', values.tone), rule('length', values.length), rule('check', values.check)].join('\n'), example,
      builder: { version: 1, mode: 'guided', templateId: template.id, values } };
  }

  function mount(host, { draft, availableTemplates, onChange = () => {}, viewState, navigationHost } = {}) {
    const available = templates.filter(template => availableTemplates.some(base => base.id === template.base));
    const saved = draft?.builder?.version === 1 && available.some(template => template.id === draft.builder.templateId) ? draft.builder : null;
    let template = saved ? byId(saved.templateId) : available.find(value => value.base === draft?.baseSkillId) || available[0] || templates[0];
    let selectedTemplate = saved?.templateId || '';
    let values = saved ? valuesFor(template, saved.values) : emptyValues(template), name = draft?.name || '';
    let mode = saved?.mode || (draft?.name ? 'free' : 'guided');
    let stage = Math.max(0, Math.min(3, viewState?.stage || 0));
    let free = draft?.name ? { ...draft } : { baseSkillId: '', purpose: '', steps: '', outputFormat: '', example: '' };
    const invalid = new Set();
    const stages = ['选教学模板', '填学习目标', '选辅导方式', '预览与试用'];
    const $ = selector => host.querySelector(selector);
    const title = (label, required = false) => `<span>${required ? '<span class="skill-required" aria-hidden="true">*</span>' : ''}${label}</span>`;
    const errorHtml = key => errorsFor[key] ? `<small class="skill-field-error" data-validation-error="${key}" id="skillError_${key}" hidden>${errorsFor[key]}</small>` : '';
    const inputLabel = (key, label, help, placeholder, rows = 0, required = false) => `<label>${title(label, required)}${rows ? `<textarea class="input" data-guide-field="${key}" ${required ? `required aria-required="true" data-validation-field="${key}"` : ''} rows="${rows}" maxlength="${textLimits[key]}" placeholder="${U.esc(placeholder)}">${U.esc(values[key])}</textarea>` : `<input class="input" data-guide-field="${key}" ${required ? `required aria-required="true" data-validation-field="${key}"` : ''} maxlength="${textLimits[key]}" placeholder="${U.esc(placeholder)}" value="${U.esc(values[key])}">`}<small>${help}</small>${required ? errorHtml(key) : ''}</label>`;
    function select(key, label, help) {
      const required = primaryChoices.includes(key);
      return `<label>${title(label, required)}<select class="select" data-guide-field="${key}" ${required ? `required aria-required="true" data-validation-field="${key}"` : ''}>${required ? `<option value="" ${values[key] ? '' : 'selected'}>请选择</option>` : ''}${options[key].map(option => `<option value="${option[0]}" ${values[key] === option[0] ? 'selected' : ''}>${option[1]}</option>`).join('')}</select><small data-option-help="${key}">${help || rule(key, values[key]) || '请选择适合的方式。'}</small>${required ? errorHtml(key) : ''}</label>`;
    }
    function audienceSelect() {
      const choices = values.audience && !audiences.includes(values.audience) ? [...audiences, values.audience] : audiences;
      return `<label>${title('给哪些学生用？', true)}<select class="select" data-guide-field="audience" data-validation-field="audience" required aria-required="true"><option value="" ${values.audience ? '' : 'selected'}>请选择</option>${choices.map(text => `<option value="${U.esc(text)}" ${values.audience === text ? 'selected' : ''}>${U.esc(text)}</option>`).join('')}</select><small>选择最接近的学习基础，智能体会据此调整解释方式。</small>${errorHtml('audience')}</label>`;
    }
    function capture() {
      const nameInput = $('[name="name"]');
      if (nameInput) name = nameInput.value;
      if (mode === 'guided') host.querySelectorAll('[data-guide-field]').forEach(element => { values[element.dataset.guideField] = element.value; });
      else for (const key of ['baseSkillId', 'purpose', 'steps', 'outputFormat', 'example']) if ($(`[name="${key}"]`)) free[key] = $(`[name="${key}"]`).value;
    }
    function focusField(selector) {
      requestAnimationFrame(() => {
        const field = $(selector);
        (field?.querySelector('input, select, textarea') || field)?.focus();
      });
    }
    function filled(key) {
      if (key === 'name') return Boolean(name.trim());
      if (key === 'templateId') return Boolean(selectedTemplate);
      const value = mode === 'guided' ? values[key] : free[key];
      return Boolean(typeof value === 'string' && value.trim());
    }
    function requiredFields(upTo = 2) {
      if (mode === 'free') return ['name', 'baseSkillId', 'purpose', 'steps'];
      return [['name', 'templateId'], ['audience', 'goal'], primaryChoices].slice(0, upTo + 1).flat();
    }
    function paintErrors() {
      for (const key of invalid) if (filled(key)) invalid.delete(key);
      host.querySelectorAll('[data-validation-field]').forEach(field => {
        const key = field.dataset.validationField, failed = invalid.has(key);
        field.classList.toggle('is-invalid', failed);
        field.setAttribute('aria-invalid', String(failed));
        if (failed) field.setAttribute('aria-describedby', 'skillError_' + key);
        else field.removeAttribute('aria-describedby');
      });
      host.querySelectorAll('[data-validation-error]').forEach(error => { error.hidden = !invalid.has(error.dataset.validationError); });
      const summary = $('#skillValidationNotice');
      if (summary) summary.hidden = !host.querySelector('[aria-invalid="true"]');
    }
    function rejectMissing(missing) {
      missing.forEach(key => invalid.add(key));
      if (mode === 'guided') {
        const first = missing[0];
        stage = ['name', 'templateId'].includes(first) ? 0 : ['audience', 'goal'].includes(first) ? 1 : 2;
      }
      render();
      focusField(`[data-validation-field="${missing[0]}"]`);
      return errorsFor[missing[0]] + '，已标红未填写的必填项。';
    }
    function goToStage(target, review = false) {
      capture();
      target = Math.max(0, Math.min(3, target));
      if (review || target > stage) {
        const missing = requiredFields(review ? 2 : target - 1).filter(key => !filled(key));
        if (missing.length) return rejectMissing(missing);
      }
      stage = target; render();
      return '';
    }
    function guideComplete() {
      return selectedTemplate && values.audience.trim() && values.goal.trim() && primaryChoices.every(key => options[key].some(option => option[0] === values[key]));
    }
    function readDraft() {
      capture();
      if (mode === 'guided') return compile(name, template.id, values);
      const result = { name: name.trim(), baseSkillId: free.baseSkillId, purpose: (free.purpose || '').trim(), steps: (free.steps || '').trim(), outputFormat: (free.outputFormat || '').trim(), example: (free.example || '').trim() };
      if (guideComplete()) result.builder = { version: 1, mode: 'free', templateId: template.id, values: { ...values } };
      return result;
    }
    function reviewHtml() {
      const compiled = compile(name, template.id, values);
      return `<div class="skill-guide-review"><p class="skill-guide-callout">配置已整理成下面的规则。先在右侧问一两个真实问题；效果合适，再保存并发布。</p><dl><dt>要帮助学生做到什么</dt><dd>${U.esc(compiled.purpose)}</dd><dt>会怎样引导学生</dt><dd>${U.esc(compiled.steps)}</dd><dt>回答会是什么样</dt><dd>${U.esc(compiled.outputFormat)}</dd>${compiled.example ? `<dt>你提供的示例</dt><dd>${U.esc(compiled.example)}</dd>` : ''}</dl><button type="button" class="btn btn--outline btn--sm" data-designer-mode="free">转为自由编写，继续调整文字</button></div>`;
    }
    function guidedHtml() {
      let body;
      if (stage === 0) body = `<h5 id="skillTemplateLabel">${title('你希望它主要帮学生做什么？', true)}</h5><p class="fz-12 t-dim">请选择一个教学模板，后续填写你的教学目标和辅导方式。</p><div class="skill-template-picker" data-validation-field="templateId" role="radiogroup" aria-labelledby="skillTemplateLabel" aria-required="true"><div class="skill-template-grid">${available.map(item => `<label class="skill-template-card ${item.id === selectedTemplate ? 'is-selected' : ''}"><input type="radio" name="guideTemplate" value="${item.id}" ${item.id === selectedTemplate ? 'checked' : ''}><span><b>${item.label}</b><small>${item.description}</small></span></label>`).join('')}</div></div>${errorHtml('templateId')}`;
      else if (stage === 1) body = `<h5>写清“给谁用、学什么、学到什么程度”</h5>${audienceSelect()}${inputLabel('topic', '主要围绕哪一部分？（可选）', '留空时，跟随学生本轮提问。', '例如：栈和队列、第 3 章')}${inputLabel('goal', '希望学生最后能做到什么？', '写学生最后能做到的事情，框内示例仅供参考，需要自行填写。', '例如：' + template.goal, 3, true)}`;
      else if (stage === 2) body = `<h5>这三项决定主要辅导方式</h5><p class="fz-12 t-dim">请逐项选择；「更多教学细节」保留推荐值，可按需要调整。</p>${select('teachingStyle', '主要怎样教？')}${select('pace', '一次讲多少？')}${select('answerPolicy', '遇到题目时怎样处理？')}<details class="skill-guide-details"><summary>更多教学细节（已有推荐值，可不改）</summary><div class="skill-guide-detail-fields">${select('depth', '讲到什么深度？')}${select('evidence', '怎样使用课程资料？')}${select('missingInfo', '学生没说清楚时怎么办？')}${select('check', '怎样确认学生学会了？')}${select('layout', '怎样组织回答？')}${select('tone', '用什么语气？')}${select('length', '每次回答多长？')}${inputLabel('extra', '还有什么特别要求？（可选）', '补充你的教学要求，不用写程序代码。', '例如：优先用校园生活的例子，先解释术语再写公式', 3)}${inputLabel('exampleQuestion', '学生可能怎么问？（可选）', '填一个真实提问，更容易试出你想要的效果。', '例如：' + template.question, 2)}${inputLabel('exampleAnswer', '你希望怎样回答？（可选）', '给一个简短示范即可，作为回答风格参考。', '例如：先肯定已知思路，再给一个小提示，并留一个问题', 3)}</div></details>`;
      else body = reviewHtml();
      return `<ol class="skill-guide-progress" aria-label="配置步骤">${stages.map((text, index) => `<li><button type="button" data-guide-stage="${index}" ${index === stage ? 'aria-current="step"' : ''}><span>${index + 1}</span>${text}</button></li>`).join('')}</ol><section class="skill-guide-stage">${body}</section>${navigationHost ? '' : '<div class="skill-guide-navigation">' + navigationHtml() + '</div>'}`;
    }
    function navigationHtml() {
      return `<button type="button" class="btn btn--ghost btn--sm" data-guide-next="${stage - 1}" ${stage === 0 ? 'disabled data-designer-disabled="true"' : ''}>上一步</button><span class="fz-12 t-dim">${stage + 1} / 4</span>${stage < 3 ? `<button type="button" class="btn btn--primary btn--sm" data-guide-next="${stage + 1}">下一步：${stages[stage + 1]}</button>` : '<span class="fz-12 t-dim">可在右侧试用，再发布</span>'}`;
    }
    function freeHtml() {
      return `<p class="skill-guide-callout">可以直接写完整要求，自由决定处理步骤和表达方式。这里的文字会作为最终技能规则；切换模式不会授予额外的数据或操作权限。</p><label>${title('基础技能', true)}<select class="select" name="baseSkillId" data-validation-field="baseSkillId" required aria-required="true"><option value="" ${free.baseSkillId ? '' : 'selected'}>请选择</option>${availableTemplates.map(base => `<option value="${U.esc(base.id)}" ${base.id === free.baseSkillId ? 'selected' : ''}>${U.esc(base.label)}</option>`).join('')}</select><small>决定已有的查询能力，选择最接近的用途即可。</small>${errorHtml('baseSkillId')}</label>${[
        ['purpose', '用途', 300, 2, '希望帮学生解决什么问题、达到什么目标？'],
        ['steps', '处理步骤', 3000, 7, '按先后顺序写：先做什么、根据什么判断、什么时候追问或停止。'],
        ['outputFormat', '回答格式', 1000, 3, '例如：简短解释 → 一个例子 → 一个引导问题。'],
        ['example', '示例（可选）', 2000, 3, '写一个学生提问和你期望的回答，帮助表达教学风格。'],
      ].map(([key, label, limit, rows, hint]) => {
        const required = ['purpose', 'steps'].includes(key);
        return `<label>${title(label, required)}<textarea class="input" name="${key}" ${required ? `required aria-required="true" data-validation-field="${key}"` : ''} rows="${rows}" maxlength="${limit}" placeholder="${hint}">${U.esc(free[key] || '')}</textarea><small>${hint}</small>${required ? errorHtml(key) : ''}</label>`;
      }).join('')}<button type="button" class="btn btn--ghost btn--sm" data-clear-free>清空正文，自己编写</button>`;
    }
    function render() {
      host.innerHTML = `<div class="skill-designer-modes" role="tablist" aria-label="选择配置方式"><button id="skillModeGuided" type="button" role="tab" aria-selected="${mode === 'guided'}" data-designer-mode="guided"><b>引导式配置</b><span>选模板、填空，推荐新手使用</span></button><button id="skillModeFree" type="button" role="tab" aria-selected="${mode === 'free'}" data-designer-mode="free"><b>自由编写</b><span>直接写要求，更灵活</span></button></div><label class="skill-designer-name">${title('给技能起个名字', true)}<input class="input" name="name" data-validation-field="name" maxlength="40" required aria-required="true" value="${U.esc(name)}" placeholder="例如：${U.esc(template.name)}"><small>学生会在加号菜单中看到这个名称。</small>${errorHtml('name')}</label><p id="skillValidationNotice" class="skill-validation-notice" role="alert" hidden>请填写标红的必填项后继续。</p><div class="skill-designer-content">${mode === 'guided' ? guidedHtml() : freeHtml()}</div>`;
      if (navigationHost) { navigationHost.hidden = mode !== 'guided'; navigationHost.innerHTML = mode === 'guided' ? navigationHtml() : ''; }
      paintErrors();
      notifyChange();
    }
    function notifyChange() { onChange({ needsReview: mode === 'guided' && stage < 3, mode, stage, name }); }
    function changeMode(next) {
      capture();
      if (next === mode) return;
      if (next === 'free' && guideComplete()) free = compile(name, template.id, values);
      else if (next === 'guided' && (free.purpose || free.steps) && !window.confirm('引导式会按模板和填空重新生成规则，覆盖当前自由编写的正文。确定切换吗？')) return;
      mode = next; invalid.clear(); render();
    }
    host.addEventListener('click', event => {
      const modeButton = event.target.closest('[data-designer-mode]');
      if (modeButton) return changeMode(modeButton.dataset.designerMode);
      const next = event.target.closest('[data-guide-next], [data-guide-stage]');
      if (next && !next.disabled) goToStage(Number(next.dataset.guideNext ?? next.dataset.guideStage));
      if (event.target.closest('[data-clear-free]') && window.confirm('清空用途、步骤、格式和示例，改为自己编写？技能名称和基础技能会保留。')) {
        capture(); free = { ...free, purpose: '', steps: '', outputFormat: '', example: '' }; render();
      }
    });
    navigationHost?.addEventListener('click', event => {
      const next = event.target.closest('[data-guide-next]');
      if (next && !next.disabled) goToStage(Number(next.dataset.guideNext));
    });
    host.addEventListener('change', event => {
      if (event.target.name === 'guideTemplate') {
        capture();
        template = byId(event.target.value);
        selectedTemplate = template.id;
        render();
      } else if (event.target.dataset.guideField) {
        capture(); const key = event.target.dataset.guideField;
        if (options[key] && $(`[data-option-help="${key}"]`)) $(`[data-option-help="${key}"]`).textContent = rule(key, values[key]) || '请选择适合的方式。';
      }
      capture(); paintErrors(); notifyChange();
    });
    host.addEventListener('input', () => {
      capture();
      paintErrors();
      if (mode === 'guided' && stage === 3) $('.skill-guide-stage').innerHTML = reviewHtml();
      notifyChange();
    });
    render();
    return { readDraft, viewState: () => ({ stage }), needsReview: () => mode === 'guided' && stage < 3,
      showReview() { return goToStage(3, true); },
      validate() {
        capture();
        const missing = requiredFields().filter(key => !filled(key));
        if (missing.length) return rejectMissing(missing);
        paintErrors();
        return '';
      },
    };
  }
  return { mount, compile, templates, options, defaults, emptyValues, audiences, textLimits };
})();
