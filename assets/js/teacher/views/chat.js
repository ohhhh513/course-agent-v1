'use strict';

/* ================================================================
   视图 · 智能助手（教师端）
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js（与学生端共用），
   这里只提供教师端配置：教师向推荐问题、教师端页面白名单。
   教师视角工具（class_overview / class_alerts / student_profile /
   kp_heatmap / hot_wrong_questions）只在教师与管理员提问时可用，
   学生端看不到也调不到 —— 由后端按登录角色过滤。
   ================================================================ */

const TeacherChat = AgentChatView.create({
  viewKey: 'chat',
  containerId: '#view-chat',
  badges: '',
  placeholder: '问班级学情，例如「我班上谁最需要关注」，Enter 发送 / Shift+Enter 换行',
  welcomeTitle: '你好，今天需要什么教学帮助？',
  welcomeText: '查看班级学情、管理课程资源、准备题目，告诉我你想做什么。',
  // 「猜你想问」已下线：教师端欢迎区不显示推荐问题
  recommended: () => Promise.resolve([]),

  /**
   * 执行 AI 建议的界面动作（来自工具 suggest_action）。返回 false = 未识别/不允许。
   * 教师端只允许跳转到教师端自己的页面（白名单）；教师端没有练习页，
   * 所以 practice / 学生端页面一律不执行。
   */
  /**
   * 支持上传附件（xlsx/csv/docx/txt/md/json/pdf）：文件抽取的纯文本随本轮问题一起提交，
   * 不落库正文、不进知识库；历史会话只回显文件名。上限三端统一
   * （见 backend/app/services/attachments.py）。学生端与管理员端同样已开启。
   */
  allowUpload: true,

  applyAction(a) {
    const VIEWS = ['dashboard', 'monitor', 'analysis', 'question',
                   'report', 'structure', 'graph-edit', 'chat'];
    if (!a || typeof a !== 'object') return false;
    if (a.kind === 'navigate' && VIEWS.includes(a.view)) {
      Router.go(a.view);
      return true;
    }
    return false;
  },
});

Router.register('chat', {
  title: '智能助手',
  mount: () => TeacherChat.render(),
  reset: () => {
    TeacherChat.busy = false;
    TeacherChat.startNewSession();
    TeacherChat.pendingDraft = null;
  },
});
