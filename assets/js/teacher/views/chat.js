'use strict';

/* ================================================================
   视图 · 智能助手（教师端）
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js（与学生端共用），
   这里只提供教师端配置：技能菜单、教师端页面白名单。
   ================================================================ */

const TeacherChat = AgentChatView.create({
  viewKey: 'chat',
  containerId: '#view-chat',
  badges: '',
  placeholder: '问班级学情，例如「谁最需要关注」',
  welcomeTitle: '今天需要什么教学帮助？',
  welcomeText: '点加号选择技能或上传文件，或直接写下你的问题。',
  skills: [
    { id: 'class', label: '班级学情', icon: 'users', hint: '想看谁需要关注，还是某个知识点？', desc: '全班掌握、预警和知识点强弱' },
    { id: 'student_track', label: '个体追踪', icon: 'user', hint: '想看哪位学生最近的学习？', desc: '点名学生看练习与匿名答疑摘要' },
    { id: 'wrong_analysis', label: '错题归因', icon: 'flask', hint: '想看共性错题，还是某一题？', desc: '共性错因和课堂上怎么讲' },
    { id: 'question', label: '备课出题', icon: 'sparkle', hint: '范围、题型和题量是什么？', desc: '按知识点生成草稿，不直接进正式题库' },
    { id: 'report', label: '学情报告', icon: 'file', hint: '要生成报告，还是先看已有报告？', desc: '生成或打开班级学情报告' },
  ],
  recommended: () => Promise.resolve([]),

  allowUpload: true,

  applyAction(a) {
    const VIEWS = ['dashboard', 'monitor', 'analysis', 'question',
                   'report', 'structure', 'shares', 'graph-edit', 'chat'];
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
