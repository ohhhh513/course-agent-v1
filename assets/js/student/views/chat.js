'use strict';

/* ================================================================
   视图 4 · AI 智能答疑
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js（与教师端共用），
   这里只提供学生端的配置：欢迎语、技能菜单、界面动作白名单。
   Chat 为全局对象：dashboard.js / graph.js 会调用 Chat.draft() 带入问题。
   ================================================================ */

const Chat = AgentChatView.create({
  viewKey: 'ai',
  containerId: '#view-ai',
  badges: '',
  placeholder: '输入你的问题',
  welcomeTitle: '今天想学点什么？',
  welcomeText: '点加号选择技能或上传文件，或直接写下你的问题。',
  skills: [
    { id: 'course_qa', label: '课程答疑', icon: 'message', hint: '想搞懂哪个知识点或哪道题？', desc: '结合本课讲清概念、对比和题面思路' },
    { id: 'wrong_review', label: '错题复盘', icon: 'quiz', hint: '哪道题没做对？', desc: '对照你上次作答讲错因，不代交答案' },
    { id: 'mastery', label: '学情诊断', icon: 'chart', hint: '想看掌握、预警还是报告？', desc: '看薄弱点、预警，必要时生成个人报告' },
    { id: 'practice', label: '练习教练', icon: 'target', hint: '想练薄弱点、指定知识还是错题？', desc: '安排练习入口，不代答、不刷分' },
    { id: 'resource', label: '资源导航', icon: 'folder', hint: '想找哪一部分的课件或材料？', desc: '按章节或知识点定位本课资料' },
  ],
  customSkills: 'student',
  recommended: () => Promise.resolve([]),

  allowUpload: true,

  /**
   * 执行 AI 建议的界面动作（来自工具 suggest_action）。返回 false = 未识别/不允许。
   * 仅在用户点击回答下方按钮后调用，流式回答结束不会自动跳转。
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
