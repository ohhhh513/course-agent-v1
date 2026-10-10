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
  badges: `<span class="badge badge--ok">${icon('shield')} 严格溯源</span>
           <span class="badge badge--outline">${icon('bot')} RAG + 工具调用</span>`,
  placeholder: '输入你的问题，Enter 发送 / Shift+Enter 换行',
  welcomeHtml: `<b>👋 你好！我是你的 AI 助教</b>
    <p style="margin:8px 0 0;color:var(--text-2)">你可以向我提问课程相关的问题，我会结合教材、课件和教学视频为你解答。试试从下方选择一个问题，或直接在输入框提问吧！</p>`,
  // 推荐问题与「学习驾驶舱 - AI 助教」同一数据源（/student/dashboard 的 suggestedQuestions；
  // 旧接口 /ai/suggest-questions 后端恒为空，弃用）
  recommended: () => API.student.dashboard().then(d => (d && d.suggestedQuestions) || []),

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
