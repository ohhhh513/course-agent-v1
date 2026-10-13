'use strict';

/* ================================================================
   视图 4 · AI 智能答疑
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js（与教师端共用），
   这里只提供学生端的配置：欢迎语、推荐问题来源、界面动作白名单。
   Chat 为全局对象：dashboard.js / graph.js 会调用 Chat.draft() 带入问题。
   ================================================================ */

const Chat = AgentChatView.create({
  viewKey: 'ai',
  containerId: '#view-ai',
  badges: '',
  placeholder: '输入你的问题',
  welcomeTitle: '今天想学点什么？',
  welcomeText: '可以讲知识点、找资料、安排练习，或看看你的学情。',
  skills: [
    {
      id: 'explain', label: '课程答疑', icon: 'message',
      hint: '想搞懂哪个知识点，或哪道题？',
      prompts: [
        { label: '讲清一个知识点', text: '请结合本课程讲清这个知识点：它是什么、什么时候用，并给一个小例子。知识点：' },
        { label: '这道题错在哪', text: '这道题我没做对。请指出错在哪里，并讲正确思路。不要替我提交答案。题目是：' },
        { label: '对比两个概念', text: '请对比这两个概念的相同点和不同点，各举一个本课程里的例子：' },
      ],
    },
    {
      id: 'resource', label: '找学习资源', icon: 'folder',
      hint: '想找哪一部分的课件或材料？',
      prompts: [
        { label: '找本章课件', text: '请在本课程里找和这个内容相关的课件或文档，并告诉我在学习资源中心哪里打开：' },
        { label: '找入门材料', text: '请帮我找适合入门的学习材料，并说明每份材料解决什么问题。内容是：' },
        { label: '按知识点找', text: '请按这个知识点列出本课程里可以看的资源：' },
      ],
    },
    {
      id: 'practice', label: '安排练习', icon: 'pencil',
      hint: '想练薄弱点，还是指定知识点？',
      prompts: [
        { label: '练我的薄弱点', text: '请根据我的学情指出最该先练的薄弱知识点，并带我去练习。不要替我作答。' },
        { label: '练指定知识点', text: '请帮我安排这个知识点的练习，并打开练习页。不要替我作答。知识点：' },
        { label: '复习错题', text: '请根据我的错题告诉我该优先复习什么，并带我去错题练习。不要替我作答。' },
      ],
    },
    {
      id: 'mastery', label: '看我的学情', icon: 'chart',
      hint: '想看掌握情况、最近学习，还是预警？',
      prompts: [
        { label: '哪些知识点薄弱', text: '请看我当前课程的学情，列出掌握最弱的知识点，并说明下一步该做什么。' },
        { label: '最近学得怎么样', text: '请总结我最近的学习情况：掌握程度、该补的地方，以及一条具体建议。' },
        { label: '我有哪些预警', text: '请告诉我现在有哪些预警，以及每条预警我可以怎么处理。' },
      ],
    },
  ],
  // 推荐问题与「学习驾驶舱 - AI 助教」同一数据源（/student/dashboard 的 suggestedQuestions；
  // 旧接口 /ai/suggest-questions 后端恒为空，弃用）
  // 「猜你想问」已下线：欢迎区不显示推荐问题
  recommended: () => Promise.resolve([]),

  // 支持上传附件（txt/md/csv/json/xlsx/docx/pdf，最多 5 个、单个 ≤10MB）：
  // 文件文本随本轮问题一起提交给助手，**不落库正文、不进知识库**；历史会话只回显文件名。
  allowUpload: true,

  /**
   * 执行 AI 建议的界面动作（来自工具 suggest_action）。返回 false = 未识别/不允许。
   *
   * 白名单制：navigate 只允许固定页面；practice 只复用「预警 → 去练习」那套待办机制
   * （设置 Practice._pendingTarget 后跳练习页，仍由用户自己点开始）。
   * 除这两种之外一律不执行 —— 模型给什么都不能触发任意跳转或任意代码。
   */
  applyAction(a) {
    const VIEWS = ['dashboard', 'graph', 'resource', 'practice', 'mastery', 'alerts', 'ai', 'report'];
    const MODES = ['weak', 'order', 'random', 'wrong'];
    if (!a || typeof a !== 'object') return false;
    if (a.kind === 'navigate') {
      if (!VIEWS.includes(a.view)) return false;
      Router.go(a.view);
      return true;
    }
    if (a.kind === 'practice') {
      const kpId = String(a.kpId || '').trim();
      if (!kpId) return false;
      const mode = MODES.includes(a.mode) ? a.mode : 'weak';
      if (typeof Practice !== 'undefined') {
        Practice._pendingTarget = { kpId, kpName: a.kpName || '', mode };
      }
      Router.go('practice');
      return true;
    }
    return false;
  },
});

Router.register('ai', {
  title: 'AI 智能答疑',
  mount: () => Chat.render(),
  reset: () => {
    Chat.busy = false;
    Chat.startNewSession();
    Chat.pendingDraft = null;
    Chat.pendingFiles = [];   // 切换课程时清掉待发附件，别把上个课程的文件带过来
  },
});
