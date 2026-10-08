'use strict';

/* ================================================================
   视图 · 智能答疑（教师端）
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js（与学生端共用），
   这里只提供教师端配置：教师向推荐问题、教师端页面白名单。
   教师视角工具（class_overview / class_alerts / student_profile /
   kp_heatmap / hot_wrong_questions）只在教师与管理员提问时可用，
   学生端看不到也调不到 —— 由后端按登录角色过滤。
   ================================================================ */

const TeacherChat = AgentChatView.create({
  viewKey: 'chat',
  containerId: '#view-chat',
  badges: `<span class="badge badge--ok">${icon('shield')} 教师视角</span>
           <span class="badge badge--outline">${icon('grid')} 全班学情</span>`,
  placeholder: '问班级学情，例如「我班上谁最需要关注」，Enter 发送 / Shift+Enter 换行',
  welcomeHtml: `<b>👋 教师视角答疑</b>
    <p style="margin:8px 0 0;color:var(--text-2)">你可以问全班层面的学情（谁需要关注、哪个知识点整体最差、
    哪几道题全班都错），也可以照常问课程内容。数据实时取自本课程的学习记录，不是教材检索。</p>`,
  // 教师向推荐问题（静态清单：教师端没有「猜你想问」接口）
  recommended: () => Promise.resolve([
    '我班上谁最需要关注？',
    '我班上整体学情怎么样？',
    '哪个知识点全班掌握最差？',
    '哪几道题全班都错？',
  ]),

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
  title: '智能答疑',
  mount: () => TeacherChat.render(),
  reset: () => {
    TeacherChat.busy = false;
    TeacherChat.sessionId = 'new';
    TeacherChat.pendingDraft = null;
  },
});
