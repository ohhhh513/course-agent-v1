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
  placeholder: '问班级学情，例如「谁最需要关注」',
  welcomeTitle: '今天需要什么教学帮助？',
  welcomeText: '可以看班级学情、分析错题、准备题目，或生成报告。',
  skills: [
    {
      id: 'class', label: '班级学情', icon: 'users',
      hint: '想看谁需要关注，还是某个知识点？',
      prompts: [
        { label: '谁最需要关注', text: '请看我当前班级，列出最需要关注的学生和原因。' },
        { label: '整体掌握情况', text: '请概括当前班级的整体掌握情况，并指出共同的薄弱点。' },
        { label: '某个知识点', text: '请看这个知识点在班里的掌握情况：哪些人比较弱，可能是什么原因。知识点：' },
      ],
    },
    {
      id: 'wrong', label: '错题分析', icon: 'flask',
      hint: '想看共性错题，还是某一题？',
      prompts: [
        { label: '共性错题', text: '请列出班里最近最集中的错题，并说明共同错因。' },
        { label: '某题为什么错', text: '请分析这道题在班里的错误情况：错在哪，课堂上该怎么讲。题目或知识点：' },
        { label: '高频薄弱点', text: '请从错题里归纳最高频的薄弱知识点，并建议怎么处理。' },
      ],
    },
    {
      id: 'question', label: 'AI 出题', icon: 'sparkle',
      hint: '想按知识点出题，还是出一套小测？',
      prompts: [
        { label: '按知识点出题', text: '请按这个知识点出一组题，标注难度，并说明怎么放进题库。知识点：' },
        { label: '出一套小测', text: '请帮我设计一套课堂小测，包含考查范围、题型和难度。范围：' },
        { label: '针对错题巩固', text: '请根据班里的共性错题出一组巩固题，并说明每题针对什么错因。' },
      ],
    },
    {
      id: 'report', label: '学情报告', icon: 'file',
      hint: '要生成报告，还是先看已有报告？',
      prompts: [
        { label: '生成班级报告', text: '请根据当前班级学情生成一份学情报告。' },
        { label: '先看怎么生成', text: '怎么生成学情报告？请打开生成配置，先不要生成。' },
        { label: '查看已有报告', text: '请打开当前课程已有的学情报告。' },
      ],
    },
  ],
  // 「猜你想问」已下线：教师端欢迎区不显示推荐问题
  recommended: () => Promise.resolve([]),

  /**
   * 执行 AI 建议的界面动作（来自工具 suggest_action）。返回 false = 未识别/不允许。
   * 仅在用户点击回答下方按钮后调用，流式回答结束不会自动跳转。
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
