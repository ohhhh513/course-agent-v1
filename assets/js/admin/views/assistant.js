'use strict';

/* ================================================================
   视图 · 智能助手（管理员端 · 平台治理流）
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js，
   这里只提供管理员端配置 + 治理流端点（API.adminAgent → /admin/agent/*）。
   管理员业务治理工具全部是 admin-only：5 个只读治理查询（system_overview /
   account_overview / course_overview / kb_status / data_check）+ 账号治理写操作
   （preview_account_import 只读 / import_accounts 写；preview_account_delete 只读 /
   delete_accounts 写 —— 两个写操作都挂审批闸门，确认卡片确认后才落库）。
   教师 / 学生拿不到业务治理工具；管理员也进不了 explain / 出题流。
   另含 get_system_guide / suggest_action 共享只读帮助，服务端按角色限定操作目录和导航。
   ================================================================ */

const AdminChat = AgentChatView.create({
  viewKey: 'assistant',
  containerId: '#view-assistant',
  badges: `<span class="badge badge--ok">${icon('shield')} 平台治理</span>
           <span class="badge badge--outline">${icon('grid')} 全平台 · 写操作需确认</span>`,
  placeholder: '问平台情况，例如「系统现在什么状态」，Enter 发送 / Shift+Enter 换行',
  welcomeTitle: '你好，今天需要处理什么？',
  welcomeText: '查询平台情况、核查课程数据、管理师生账号，重要操作由你确认。',
  // 根据平台实时汇总和管理员近期提问生成，并按关注主题调整顺序。
  recommended: () => Promise.all([
    API.adminAgent.recommendationContext().catch(() => null),
    AgentChatView.recentUserQuestions(API.adminAgent),
  ]).then(([context, history]) => {
    const candidates = [];
    const stats = context || {};
    const students = Math.max(0, Number(stats.studentAccounts) || 0);
    const teachers = Math.max(0, Number(stats.teacherAccounts) || 0);
    const courses = Math.max(0, Number(stats.courses) || 0);
    const questions = Math.max(0, Number(stats.questions) || 0);
    const resources = Math.max(0, Number(stats.resources) || 0);
    const knowledgePoints = Math.max(0, Number(stats.knowledgePoints) || 0);
    const alerts = Math.max(0, Number(stats.alerts) || 0);

    if (context) {
      candidates.push({
        topic: 'accounts', priority: 8, keywords: ['账号', '账户', '用户', '教师', '学生', '导入', '删除', '角色'],
        prompt: `平台当前有 ${students} 名学生和 ${teachers} 名教师账号，请结合现有数据梳理账号治理中需要优先核对的事项。`,
      });
      candidates.push({
        topic: 'courses', priority: 6, keywords: ['课程', '班级', '关联', '任课', '教师'],
        prompt: `平台当前有 ${courses} 门课程，请帮我检查课程与师生账号的关联情况，并指出需要关注的治理问题。`,
      });
      candidates.push({
        topic: 'content', priority: 7, keywords: ['题库', '题目', '资源', '知识点', '内容'],
        prompt: `平台当前有 ${questions} 道题、${resources} 份资源和 ${knowledgePoints} 个知识点，请帮我检查教学内容数据的完整性。`,
      });
      candidates.push({
        topic: 'alerts', priority: alerts > 0 ? 10 : 4, keywords: ['预警', '风险', '干预', '学情', '学生'],
        prompt: `平台当前记录 ${alerts} 条学情预警，请帮我梳理管理员应优先核查的预警治理事项。`,
      });
      const mode = stats.assistantMode === 'live' ? '真实问答' : '演示';
      candidates.push({
        topic: 'agent-runtime', priority: stats.assistantMode === 'demo' ? 9 : 5,
        keywords: ['智能体', '模型', '运行', '状态', '配置', '知识库', '检索'],
        prompt: `智能体当前处于${mode}模式，请结合平台现状说明需要检查的运行配置和数据环节。`,
      });
    }

    const topics = [
      { topic: 'accounts', label: '账号治理', keywords: ['账号', '账户', '用户', '教师', '学生', '导入', '删除', '角色'] },
      { topic: 'courses', label: '课程关联', keywords: ['课程', '班级', '关联', '任课', '教师'] },
      { topic: 'content', label: '题库与资源', keywords: ['题库', '题目', '资源', '知识点', '内容'] },
      { topic: 'alerts', label: '预警治理', keywords: ['预警', '风险', '干预', '学情', '学生'] },
      { topic: 'agent-runtime', label: '智能体运行', keywords: ['智能体', '模型', '运行', '状态', '配置', '知识库', '检索'] },
    ];
    if (!context && history.length) {
      topics.forEach(item => candidates.push({
        topic: item.topic, priority: 1, keywords: item.keywords,
        prompt: `结合你近期关于「${item.label}」的提问，帮我整理下一步值得核查的事项。`,
      }));
      candidates.push({
        topic: 'recent-followup', priority: 2,
        keywords: [],
        prompt: `围绕我最近的问题「${String(history[0]).slice(0, 48)}」，列出下一步可执行的核查步骤。`,
      });
    }
    return AgentChatView.rankRecommendationCandidates(candidates, history);
  }),
  emptyRecommend: '还没有足够的平台汇总数据或历史提问来判断关注点；开始对话后，推荐会随你的关注主题调整。',

  // 只跳转本端真实页面，编辑、保存和删除仍由用户自行操作。
  applyAction(act) {
    const VIEWS = ['users', 'assistant'];
    if (act && act.kind === 'navigate' && VIEWS.includes(act.view)) {
      Router.go(act.view);
      return true;
    }
    return false;
  },

  // 治理流端点：会话 / 消息 / 流式问答都走 /admin/agent/*（挂 require_admin，不吃课程上下文）
  api: API.adminAgent,

  // 支持上传附件（xlsx/csv/docx/txt/md/json/pdf）：文本随本轮问题提交给助手，
  // 不落库正文、不进知识库；历史会话只回显文件名。
  // 学生/教师账号表会被结构化解析，说「录入系统」即可生成待批准动作（确认后才落库）。
  // 上传能力三端一致（学生端 / 教师端 / 管理端均开启）；仅「账号表结构化解析」是本端独有。
  allowUpload: true,
});

Router.register('assistant', {
  title: '智能助手',
  mount: () => AdminChat.render(),
  reset: () => {
    AdminChat.busy = false;
    AdminChat.startNewSession();
  },
});
