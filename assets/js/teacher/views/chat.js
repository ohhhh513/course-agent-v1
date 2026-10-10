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
  badges: `<span class="badge badge--ok">${icon('shield')} 教师视角</span>
           <span class="badge badge--outline">${icon('grid')} 全班学情</span>`,
  placeholder: '问班级学情，例如「我班上谁最需要关注」，Enter 发送 / Shift+Enter 换行',
  welcomeHtml: `<b>👋 教师智能助手</b>
    <p style="margin:8px 0 0;color:var(--text-2)">你可以问全班层面的学情（谁需要关注、哪个知识点整体最差、
    哪几道题全班都错），也可以照常问课程内容。数据实时取自本课程的学习记录，不是教材检索。</p>`,
  // 基于当前课程驾驶舱生成推荐，并按教师近期答疑主题调整顺序。
  recommended: () => Promise.all([
    API.teacher.dashboard().catch(() => null),
    AgentChatView.recentUserQuestions(API.ai),
  ]).then(([dashboard, history]) => {
    const data = dashboard || {};
    const overview = data.classOverview || {};
    const course = String(overview.courseName || overview.className || '当前课程');
    const students = Math.max(0, Number(overview.studentCount) || 0);
    const alertStudents = Math.max(0, Number(overview.alertStudentCount) || 0);
    const candidates = [];

    if (alertStudents > 0) {
      candidates.push({
        topic: 'alerts', priority: 12, keywords: ['预警', '风险', '关注', '干预', '待办'],
        prompt: `「${course}」目前有 ${alertStudents} 名学生存在预警，请帮我分析风险成因并安排跟进优先级。`,
      });
    }

    const weakestKp = (Array.isArray(data.kpRanking) ? data.kpRanking : [])
      .slice().sort((a, b) => (Number(b.weakCount) || 0) - (Number(a.weakCount) || 0))[0];
    if (weakestKp) {
      const kpName = String(weakestKp.kpName || weakestKp.name || '当前薄弱知识点');
      const mastery = Number(weakestKp.avgMastery != null ? weakestKp.avgMastery : weakestKp.mastery);
      const weakCount = Math.max(0, Number(weakestKp.weakCount) || 0);
      candidates.push({
        topic: 'knowledge-points', priority: 10 + Math.min(weakCount, 4),
        keywords: ['知识点', '掌握', '薄弱', '练习', '错题', '讲解'],
        prompt: `「${course}」中「${kpName}」有 ${weakCount} 名学生尚未达标，平均掌握率 ${Number.isFinite(mastery) ? mastery.toFixed(1) + '%' : '暂无数据'}；请给出针对性的讲解与练习建议。`,
      });
    }

    if (students > 0) {
      const mastery = Number(overview.avgMasteryRate);
      candidates.push({
        topic: 'class-progress', priority: 7,
        keywords: ['整体', '班级', '学情', '进度', '完成', '掌握', '参与'],
        prompt: `「${course}」当前有 ${students} 名学生，平均掌握率 ${Number.isFinite(mastery) ? mastery.toFixed(1) + '%' : '暂无数据'}；请结合现有学情指出最值得优先处理的问题。`,
      });
    } else if (dashboard) {
      candidates.push({
        topic: 'empty-class', priority: 11, keywords: ['班级', '学生', '学情', '数据'],
        prompt: `「${course}」当前还没有学生学习记录，请帮我梳理开始进行班级学情分析前需要检查的事项。`,
      });
    }

    const firstTodo = Array.isArray(data.todos) ? data.todos.find(item => item && (item.title || item.desc)) : null;
    if (firstTodo) {
      const todoTitle = String(firstTodo.title || firstTodo.desc).slice(0, 60);
      candidates.push({
        topic: 'dashboard-todo', priority: 9, keywords: ['待办', '处理', '建议', '干预', '学生', '预警'],
        prompt: `驾驶舱当前待办是「${todoTitle}」，请结合本课程学情说明建议的处理顺序和依据。`,
      });
    }

    const activeToday = Math.max(0, Number(overview.activeToday) || 0);
    if (students > 0) {
      candidates.push({
        topic: 'participation', priority: 5, keywords: ['活跃', '参与', '学习', '练习', '答题'],
        prompt: `今天「${course}」有 ${activeToday} 名学生活跃学习，请帮我判断班级参与情况，并指出需要跟进的变化。`,
      });
    }

    if (!dashboard && history.length) {
      [
        { topic: 'alerts', label: '预警与学生关注', keywords: ['预警', '风险', '关注', '干预'] },
        { topic: 'knowledge-points', label: '薄弱知识点与练习', keywords: ['知识点', '掌握', '薄弱', '练习', '错题'] },
        { topic: 'class-progress', label: '班级整体学情', keywords: ['班级', '学情', '进度', '完成', '参与'] },
      ].forEach(item => candidates.push({
        topic: item.topic, priority: 1, keywords: item.keywords,
        prompt: `结合你近期关于「${item.label}」的答疑，继续梳理当前课程可以采取的教学措施。`,
      }));
      candidates.push({
        topic: 'recent-followup', priority: 2, keywords: [],
        prompt: `围绕你最近的问题「${String(history[0]).slice(0, 48)}」，列出下一步可核查的班级学情信息。`,
      });
    }

    return AgentChatView.rankRecommendationCandidates(candidates, history);
  }),
  emptyRecommend: '暂无可用的课程学情或历史提问，暂时无法生成个性化问题。',

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
