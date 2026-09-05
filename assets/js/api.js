/* ==========================================================================
   课程智能体系统 · 统一接口层
   --------------------------------------------------------------------------
   1. 所有页面只通过 API.xxx() 取数，不直接访问 MOCK，便于后端联调时零改页面。
   2. API.config.mode = 'mock' 走本地模拟数据；改为 'http' 即请求真实后端。
   3. 每个方法上方注释即为接口契约，与 docs/接口文档.md 一一对应。
   ========================================================================== */
window.API = (function () {

  const config = {
    mode: 'http',                 // 'mock' | 'http'
    baseURL: '/api/v1',
    token: 'Bearer <JWT>',
    latency: [120, 380]           // mock 模拟网络延迟区间(ms)
  };

  /* 从 localStorage 恢复 token（页面刷新后保持登录） */
  try {
    const s = JSON.parse(localStorage.getItem('ca_session') || 'null');
    if (s && s.token) {
      config.token = s.token.startsWith('Bearer ') ? s.token : ('Bearer ' + s.token);
    }
  } catch (e) {}

  /* ---------- 底层请求 ---------- */
  function delay() {
    const [a, b] = config.latency;
    return a + Math.random() * (b - a);
  }

  function ok(data, extra) {
    return Object.assign({ code: 0, message: 'success', data, traceId: 'mock-' + Date.now() }, extra || {});
  }

  /**
   * 统一请求入口
   * @param {'GET'|'POST'|'PUT'|'DELETE'} method
   * @param {string} path      形如 '/student/dashboard'
   * @param {object} payload   GET 为 query，其余为 body
   * @param {function} resolver mock 模式下的数据解析函数
   */
  function request(method, path, payload, resolver) {
    if (config.mode === 'http') {
      const isGet = method === 'GET';
      let url = config.baseURL + path;
      if (isGet && payload) {
        const qs = new URLSearchParams(
          Object.entries(payload).filter(([, v]) => v !== undefined && v !== null && v !== '')
        ).toString();
        if (qs) url += '?' + qs;
      }
      const isFormData = payload instanceof FormData;
      return fetch(url, {
        method,
        headers: isFormData ? { Authorization: config.token } : { 'Content-Type': 'application/json', Authorization: config.token },
        body: isGet ? undefined : (isFormData ? payload : JSON.stringify(payload || {}))
      })
        .then(r => r.json())
        .then(res => {
          if (res.code !== 0) throw new Error(res.message || '接口异常');
          // 登录等接口返回 token，自动存进 config + localStorage
          if (res.data && res.data.token) {
            const bearer = res.data.token.startsWith('Bearer ') ? res.data.token : ('Bearer ' + res.data.token);
            config.token = bearer;
            try {
              const s = JSON.parse(localStorage.getItem('ca_session') || 'null') || {};
              s.token = bearer;
              localStorage.setItem('ca_session', JSON.stringify(s));
            } catch (e) {}
          }
          return res.data;
        });
    }
    // mock
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        try { resolve(ok(resolver ? resolver(payload || {}) : null).data); }
        catch (e) { reject(e); }
      }, delay());
    });
  }

  const M = () => window.MOCK;

  /* ---------- 账号表（mock 模式：localStorage 持久化） ---------- */
  const ACCOUNTS_KEY = 'ca_accounts';
  function getAccounts() {
    try { return JSON.parse(localStorage.getItem(ACCOUNTS_KEY)) || []; }
    catch (e) { return []; }
  }
  function saveAccounts(list) {
    try { localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(list)); } catch (e) {}
  }
  /* 账号 → 对外用户信息（剔除密码字段） */
  function toUser(acc) {
    const u = Object.assign({}, acc);
    delete u.password;
    return u;
  }

  /* ======================================================================
     一、认证与公共
     ====================================================================== */
  const auth = {
    /** POST /auth/login  账号密码登录，返回 token 与用户信息（mock 模式校验本地账号表） */
    login: (p) => request('POST', '/auth/login', p, (q) => {
      const list = getAccounts();
      const acc = list.find(a => a.username === q.username);
      if (!acc) throw new Error('账号不存在');
      if (acc.password !== q.password) throw new Error('密码错误，请重试');
      config.token = 'Bearer ' + acc.userId + '.' + Date.now();
      return { token: config.token, user: toUser(acc) };
    }),

    /** POST /auth/reset-password  找回密码，校验账号后重置密码（mock 模式更新本地账号表） */
    resetPassword: (p) => request('POST', '/auth/reset-password', p, (q) => {
      const list = getAccounts();
      const acc = list.find(a => a.username === q.username);
      if (!acc) throw new Error('账号不存在');
      if (!q.password || q.password.length < 6) throw new Error('新密码至少 6 位');
      acc.password = q.password;
      saveAccounts(list);
      return { ok: true };
    }),

    /** POST /auth/logout  退出登录（mock 模式重置 token） */
    logout: () => {
      config.token = 'Bearer <JWT>';
      try {
        const s = JSON.parse(localStorage.getItem('ca_session') || 'null') || {};
        delete s.token;
        localStorage.setItem('ca_session', JSON.stringify(s));
      } catch (e) {}
    },

    /** GET /auth/profile  获取当前登录用户信息（优先取本地会话） */
    profile: () => request('GET', '/auth/profile', {}, () => {
      try {
        const s = JSON.parse(localStorage.getItem('ca_session'));
        if (s && s.user) return s.user;
      } catch (e) {}
      return M().student;
    }),

    /** GET /course/{courseId}  获取课程基本信息 */
    course: (p) => request('GET', '/course/' + (p && p.courseId || 'C2026DS001'), p, () => M().course)
  };

  /* ======================================================================
     二、三大课程图谱（师生共用）
     ====================================================================== */
  const graph = {
    /** GET /graph  查询图谱数据  params: { courseId, type: knowledge|problem|goal, userId? } */
    get: (p) => request('GET', '/graph', p, (q) => {
      const map = { knowledge: M().knowledgeGraph, problem: M().problemGraph, goal: M().goalGraph };
      return map[q.type || 'knowledge'];
    }),

    /** GET /graph/kp/{kpId}  知识点详情（含前后置、资源、习题统计） */
    kpDetail: (p) => request('GET', '/graph/kp/' + p.kpId, p, (q) =>
      M().kpDetail[q.kpId] || M().kpDetail.KP52),

    /** GET /graph/path  基于知识图谱前后置关系生成的推荐学习路径 */
    learningPath: (p) => request('GET', '/graph/path', p, () => M().learningPath)
  };

  /* ======================================================================
     三、学生端
     ====================================================================== */
  const stu = {
    /** GET /student/dashboard  学习驾驶舱聚合数据 */
    dashboard: (p) => request('GET', '/student/dashboard', p, () => M().studentDashboard),

    /** GET /student/resources  资源中心列表  params: { type, kpId, keyword, page, size } */
    resources: (p) => request('GET', '/student/resources', p, (q) => {
      let list = M().resources.slice();
      if (q.type && q.type !== 'all') list = list.filter(r => r.type === q.type);
      if (q.keyword) {
        const k = q.keyword.toLowerCase();
        list = list.filter(r => (r.title + r.kp + r.source).toLowerCase().includes(k));
      }
      return { total: list.length, list };
    }),

    /** POST /student/resources/{res_id}/view  记录资源查看 */
    resourceView: (p) => request('POST', `/student/resources/${p.resId}/view`, {}, () => ({ views: 0 })),

    /** GET /student/resources/{res_id}/progress  获取资源学习进度（视频：秒；文档：页码/百分比） */
    resourceProgress: (resId) => request('GET', `/student/resources/${resId}/progress`),

    /** POST /student/resources/{res_id}/progress  保存学习进度  body={progress,position} */
    saveResourceProgress: (resId, body) => request('POST', `/student/resources/${resId}/progress`, body),

    /** GET /student/resource-stats  资源学习进度统计 */
    resourceStats: () => request('GET', '/student/resource-stats'),

    /** GET /student/mastery/matrix  知识点掌握矩阵（按章节分组） */
    masteryMatrix: (p) => request('GET', '/student/mastery/matrix', p, () => M().masteryMatrix),

    /** GET /student/ability/radar  能力目标达成度（雷达图） */
    abilityRadar: (p) => request('GET', '/student/ability/radar', p, () => M().abilityRadar),

    /** GET /student/growth  成长轨迹  params: { dimension: week|month } */
    growth: (p) => request('GET', '/student/growth', p, () => M().growthTrack),

    /** GET /student/compare  与班级平均对比 */
    compare: (p) => request('GET', '/student/compare', p, () => M().classCompare),

    /** GET /student/alerts  我的预警列表  params: { level, status } */
    alerts: (p) => request('GET', '/student/alerts', p, (q) => {
      let list = M().studentAlerts.slice();
      if (q.level && q.level !== 'all') list = list.filter(a => a.level === q.level);
      if (q.status && q.status !== 'all') list = list.filter(a => a.status === q.status);
      return { total: list.length, list };
    }),

    /** PUT /student/alerts/{alertId}/read  标记预警已读 */
    readAlert: (p) => request('PUT', `/student/alerts/${p.alertId}/read`, p, () => ({ alertId: p.alertId, read: true })),

    /** GET /student/messages  教师私信 / 系统通知 */
    messages: (p) => request('GET', '/student/messages', p, () => ({ total: M().messages.length, list: M().messages })),

    /** PUT /student/messages/{msgId}/read  标记消息已读 */
    readMessage: (p) => request('PUT', `/student/messages/${p.msgId}/read`, p, () => ({ msgId: p.msgId, read: true }))
  };

  /* ======================================================================
     四、AI 智能辅导与答疑
     ====================================================================== */
  const ai = {
    /** GET /ai/methods  可用教学法列表 */
    methods: (p) => request('GET', '/ai/methods', p, () => M().teachingMethods),

    /** GET /ai/sessions  历史会话列表 */
    sessions: (p) => request('GET', '/ai/sessions', p, () => ({ total: M().chatHistory.length, list: M().chatHistory })),

    /** GET /ai/sessions/{sessionId}/messages  会话消息（含溯源引用） */
    messages: (p) => request('GET', `/ai/sessions/${p.sessionId || 'new'}/messages`, p, () => M().chatMessages),

    /** GET /ai/suggest-questions  猜你想问（基于薄弱点 + 高频问题） */
    suggestQuestions: (p) => request('GET', '/ai/suggest-questions', p, () => M().studentDashboard.suggestedQuestions),

    /**
     * POST /ai/chat  发起提问（真实环境建议用 SSE 流式：POST /ai/chat/stream）
     * body: { sessionId, question, method, kpId?, courseId }
     * 返回: { messageId, content, citations[], method, followUpQuiz? }
     */
    chat: (p) => request('POST', '/ai/chat', p, (q) => mockAnswer(q)),

    /** POST /ai/feedback  对回答点赞/点踩，用于知识库迭代 */
    feedback: (p) => request('POST', '/ai/feedback', p, () => ({ accepted: true }))
  };

  // ---- mock：根据提问关键词返回带溯源的回答 ----
  function mockAnswer(q) {
    const question = (q.question || '').trim();
    const method = q.method || 'guided';
    const bank = [
      {
        match: /遍历|前序|中序|后序/,
        content: `<p>三种遍历的差别只有<strong>一处</strong>：访问根结点的时机。</p>
          <ol>
            <li><strong>前序</strong>：<code>根 → 左 → 右</code>，先记录根，适合<strong>复制/序列化</strong>一棵树；</li>
            <li><strong>中序</strong>：<code>左 → 根 → 右</code>，在二叉排序树上会得到<strong>递增有序序列</strong>；</li>
            <li><strong>后序</strong>：<code>左 → 右 → 根</code>，根最后访问，适合<strong>释放内存、计算子树聚合值</strong>。</li>
          </ol>
          <p>本质区别在于：<strong>前序自上而下传递信息，后序自下而上汇总信息</strong>，中序则天然对应"有序性"。</p>
          <p>想不想我出 2 道即时小题检验一下？</p>`,
        citations: [
          { source: '第4章 树与二叉树 课堂课件', locator: 'P31 · 遍历定义', quote: '二叉树的遍历是指按某种规律访问树中每个结点且仅访问一次，三种次序的区别仅在于访问根结点的先后。', kp: '二叉树的遍历' },
          { source: '《数据结构（C语言版）》第6章', locator: 'P130 · 性质 6.4', quote: '中序遍历二叉排序树可得到一个关键字递增有序的序列。', kp: '二叉树的遍历' }
        ]
      },
      {
        match: /负权|Dijkstra|dijkstra|最短路/,
        content: `<p>Dijkstra 的正确性建立在一个<strong>贪心假设</strong>上：每次取出 dist 最小的顶点 u 时，dist[u] 就已是最终答案。</p>
          <p>这个假设成立的前提是 <strong>所有边权非负</strong> —— 因为从 u 继续往后走只会让路径变长，不可能再变短。</p>
          <p>一旦出现负权边，"继续走反而更短"就成立了，提前锁定 u 就错了。此时应改用 <strong>Bellman-Ford</strong>（O(VE)，还能检测负权回路）。</p>
          <p>试着自己跑一遍这个反例：A→B 权 1，A→C 权 4，<strong>C→B 权 -3</strong>。</p>`,
        citations: [
          { source: '第5章 图（下）课堂课件', locator: 'P28 · 算法正确性证明', quote: '若图中所有边的权值均为非负值，则每次选取的当前最短路径顶点，其最短路径长度不会因后续松弛而减小。', kp: '最短路径 Dijkstra' },
          { source: '《算法导论》第24章', locator: 'P658 · 定理 24.6', quote: 'Dijkstra 算法要求所有边权非负。存在负权边时需改用 Bellman-Ford 算法。', kp: '最短路径 Dijkstra' }
        ]
      },
      {
        match: /循环队列|判空|判满/,
        content: `<p>先看矛盾：队空和队满时都会出现 <code>rear == front</code>，无法区分。解决办法有三种，课程采用第一种。</p>
          <ol>
            <li><strong>牺牲一个单元</strong>（本课程标准）：队空 <code>rear == front</code>，队满 <code>(rear+1) % MAXSIZE == front</code>，实际可存 MAXSIZE-1 个；</li>
            <li>增设 <code>size</code> 计数变量；</li>
            <li>增设 <code>tag</code> 标记最后一次操作是入队还是出队。</li>
          </ol>
          <p>你上次这题错在把判满写成了 <code>(front+1) % MAXSIZE == rear</code> —— 指针方向反了。记住：<strong>是 rear 追 front</strong>。</p>`,
        citations: [
          { source: '循环队列判空判满专题', locator: '04:12 · 三种解决方案对比', quote: '为区分队空与队满，最常用的方法是少用一个元素空间，约定以队头指针在队尾指针的下一位置作为队满的标志。', kp: '循环队列判空判满' }
        ]
      },
      {
        match: /哈夫曼|WPL|编码|压缩/,
        content: `<p>哈夫曼编码保证前缀码性质的关键：<strong>所有字符都放在叶子结点上</strong>。</p>
          <p>因为任一叶子都不可能是另一叶子的祖先，所以任一编码都不可能是另一编码的前缀 —— 解码时不会产生歧义。</p>
          <p>WPL 计算有两种等价方式，用第二种更不容易错：</p>
          <ol>
            <li>Σ(叶子权值 × 该叶子路径长度)；</li>
            <li><strong>Σ(所有非叶结点的权值)</strong> —— 即每次合并产生的新结点权值之和。</li>
          </ol>`,
        citations: [
          { source: '《数据结构（C语言版）》第6章', locator: 'P152 · 哈夫曼树的构造', quote: '哈夫曼编码是一种前缀编码，因为所有字符均处于叶子结点，任一编码都不是另一编码的前缀。', kp: '哈夫曼树与编码' }
        ]
      }
    ];

    const hit = bank.find(b => b.match.test(question));
    if (hit) {
      return {
        messageId: 'MSG' + Date.now(), method,
        content: hit.content, citations: hit.citations,
        kpId: null, sourceCount: hit.citations.length
      };
    }
    // 未命中课程材料 —— 演示"严格溯源"约束
    return {
      messageId: 'MSG' + Date.now(), method,
      content: `<p>我在本课程的教材、课件与教学视频中<strong>没有检索到能直接支撑该问题的原文</strong>。为避免给你不可靠的答案，我不做推测性回答。</p>
        <p>你可以：</p>
        <ol>
          <li>换一个更贴近课程知识点的问法（例如指定章节或知识点名称）；</li>
          <li>点击下方「转人工」，我会把这个问题连同你的学情一起提交给李文博老师；</li>
          <li>或者从这些和你薄弱点相关的问题开始：<strong>Dijkstra 为什么不能处理负权边</strong>、<strong>循环队列为什么少用一个单元</strong>。</li>
        </ol>`,
      citations: [], outOfScope: true, sourceCount: 0
    };
  }

  /* ======================================================================
     五、练习 / 题库（学生侧）
     ====================================================================== */
  const practice = {
    /** GET /practice/modes  练习模式列表（含推荐题量） */
    modes: (p) => request('GET', '/practice/modes', p, () => M().practiceModes),

    /**
     * POST /practice/sessions  创建练习会话（组卷）
     * body: { mode: weak|order|random|wrong, kpIds?, count, difficulty? }
     */
    create: (p) => request('POST', '/practice/sessions', p, (q) => ({
      sessionId: 'PS' + Date.now(), mode: q.mode, total: q.count || 10,
      questions: M().practiceQuestions
    })),

    /** GET /practice/sessions/{sessionId}/questions  取题 */
    questions: (p) => request('GET', `/practice/sessions/${p.sessionId}/questions`, p, () => M().practiceQuestions),

    /**
     * POST /practice/answers  提交单题作答，返回即时判分与解析
     * body: { sessionId, qId, answer, durationSeconds }
     */
    submitAnswer: (p) => request('POST', '/practice/answers', p, (q) => {
      const question = M().practiceQuestions.find(x => x.qId === q.qId) || M().practiceQuestions[0];
      const correct = q.answer === question.answer;
      return {
        qId: question.qId, correct, rightAnswer: question.answer,
        analysis: question.analysis, kpPath: question.kpPath,
        classCorrectRate: question.classCorrectRate, avgSeconds: question.avgSeconds,
        masteryDelta: correct ? +2.1 : -1.4, errorType: correct ? null : question.errorType
      };
    }),

    /** POST /practice/sessions/{sessionId}/finish  结束练习，返回练习报告 */
    finish: (p) => request('POST', `/practice/sessions/${p.sessionId}/finish`, p, () => M().practiceReport),

    /** GET /practice/wrong-book  错题本  params: { kpId, errorType, mastered, page } */
    wrongBook: (p) => request('GET', '/practice/wrong-book', p, (q) => {
      let list = M().wrongBook.slice();
      if (q.mastered === 'false') list = list.filter(w => !w.mastered);
      if (q.mastered === 'true') list = list.filter(w => w.mastered);
      if (q.errorType && q.errorType !== 'all') list = list.filter(w => w.errorType === q.errorType);
      return { total: list.length, list };
    }),

    /** DELETE /practice/wrong-book/{qId}  移出错题本（标记已掌握） */
    removeWrong: (p) => request('DELETE', '/practice/wrong-book/' + p.qId, p, () => ({ qId: p.qId, removed: true })),

    /** GET /practice/wrong-book/{qId}  错题详情（含完整题目、解析、错题历史、相似题、推荐资源） */
    wrongDetail: (p) => request('GET', '/practice/wrong-book/' + p.qId + '/detail', p, (q) => {
      const detail = M().wrongDetail[q.qId];
      if (!detail) return Promise.reject({ code: 404, message: '错题不存在或已移除' });
      return detail;
    })
  };

  /* ======================================================================
     六、教师端 · 学情监测
     ====================================================================== */
  const tea = {
    /** GET /teacher/dashboard  教学驾驶舱  params: { classId } */
    dashboard: (p) => request('GET', '/teacher/dashboard', p, () => M().teacherDashboard),

    /** GET /teacher/heatmap  知识点 × 学生 热力图  params: { classId, dimension: day|week|month } */
    heatmap: (p) => request('GET', '/teacher/heatmap', p, () => M().heatmap),

    /** GET /teacher/students  学生列表  params: { classId, alertLevel, keyword, sortBy, page } */
    students: (p) => request('GET', '/teacher/students', p, (q) => {
      let list = M().students.slice();
      if (q.alertLevel && q.alertLevel !== 'all') list = list.filter(s => s.alertLevel === q.alertLevel);
      if (q.keyword) list = list.filter(s => (s.name + s.no).includes(q.keyword));
      if (q.sortBy === 'mastery') list.sort((a, b) => a.mastery - b.mastery);
      if (q.sortBy === 'completion') list.sort((a, b) => a.completion - b.completion);
      return { total: list.length, list };
    }),

    /** GET /teacher/students/{userId}/profile  个体学情详情（画像 + 轨迹 + 答题明细） */
    studentProfile: (p) => request('GET', `/teacher/students/${p.userId}/profile`, p, () => M().studentProfile),

    /** GET /teacher/alerts  预警列表  params: { classId, level, status, type, kpId, page } */
    alerts: (p) => request('GET', '/teacher/alerts', p, (q) => {
      let list = M().teacherAlerts.slice();
      if (q.level && q.level !== 'all') list = list.filter(a => a.level === q.level);
      if (q.status && q.status !== 'all') list = list.filter(a => a.status === q.status);
      if (q.keyword) list = list.filter(a => (a.student + a.kp + a.type).includes(q.keyword));
      return { total: list.length, list };
    }),

    /**
     * PUT /teacher/alerts/{alertId}/review  人工复核预警
     * body: { action: confirm|ignore|annotate, note? }
     */
    reviewAlert: (p) => request('PUT', `/teacher/alerts/${p.alertId}/review`, p, (q) =>
      ({ alertId: q.alertId, status: q.action === 'ignore' ? 'ignored' : 'reviewed', note: q.note || '' })),

    /** POST /teacher/messages  向学生发送私信（含改进建议） */
    sendMessage: (p) => request('POST', '/teacher/messages', p, (q) =>
      ({ msgId: 'MSG' + Date.now(), to: q.userId, sentAt: new Date().toISOString() })),

    /** GET /teacher/classes  当前教师所带班级（真实数据，来自数据库） */
    classes: () => request('GET', '/teacher/classes'),

    /** GET /teacher/resources  教师资源管理列表  params: { keyword } */
    resources: (p) => request('GET', '/teacher/resources', p),

    /** GET /teacher/resources/kps  上传时可选择的知识点（按章节分组） */
    resourceKps: () => request('GET', '/teacher/resources/kps'),

    /** POST /teacher/resources/upload  上传资源  body: FormData { file, title, kp, category } */
    uploadResource: (formData) => request('POST', '/teacher/resources/upload', formData),

    /** DELETE /teacher/resources/{res_id}  删除资源 */
    deleteResource: (resId) => request('DELETE', `/teacher/resources/${resId}`)
  };

  /* ======================================================================
     七、教师端 · 归因与错题分析
     ====================================================================== */
  const analysis = {
    /** GET /analysis/errors  错题与归因分析  params: { classId, chapter, kpId, timeRange } */
    errors: (p) => request('GET', '/analysis/errors', p, () => M().errorAnalysis),

    /** GET /analysis/weak-chain  知识点关联薄弱链路  params: { classId, kpId } */
    weakChain: (p) => request('GET', '/analysis/weak-chain', p, () => M().errorAnalysis.weakChain),

    /** GET /analysis/causes  AI 归因建议（含教学建议） */
    causes: (p) => request('GET', '/analysis/causes', p, () => M().errorAnalysis.causes)
  };

  /* ======================================================================
     八、教师端 · AI 出题与题库管理
     ====================================================================== */
  const question = {
    /** GET /question/gen/config  出题配置项（素材、知识点、题型） */
    genConfig: (p) => request('GET', '/question/gen/config', p, () => M().genConfig),

    /** POST /question/materials  上传教材/课件/视频素材，异步解析并挂载知识点 */
    upload: (p) => request('POST', '/question/materials', p, (q) =>
      ({ fileId: 'M' + Date.now(), name: q.name, status: 'parsing', progress: 0 })),

    /**
     * POST /question/gen  AI 生成习题
     * body: { materialIds[], kpIds[], types[], difficulty, count, skillId?, requirement? }
     */
    generate: (p) => request('POST', '/question/gen', p, (q) => ({
      taskId: 'GT' + Date.now(), count: q.count || 3,
      questions: M().generatedQuestions, usedSkill: q.skillId || 'SK004', elapsedMs: 4200
    })),

    /** GET /question/bank  题库列表  params: { kpId, type, status, difficulty, keyword, page } */
    bank: (p) => request('GET', '/question/bank', p, (q) => {
      let list = M().questionBank.slice();
      if (q.status && q.status !== 'all') list = list.filter(x => x.status === q.status);
      if (q.keyword) list = list.filter(x => (x.stem + x.kp + x.qId).includes(q.keyword));
      return { total: list.length, list };
    }),

    /** PUT /question/{qId}  编辑习题（人工校验后修正） */
    update: (p) => request('PUT', '/question/' + p.qId, p, (q) => ({ qId: q.qId, updated: true })),

    /** POST /question/review  批量审核发布  body: { qIds[], action: approve|reject|publish } */
    review: (p) => request('POST', '/question/review', p, (q) =>
      ({ affected: (q.qIds || []).length, action: q.action })),

    /** DELETE /question/{qId}  删除习题 */
    remove: (p) => request('DELETE', '/question/' + p.qId, p, () => ({ qId: p.qId, removed: true })),

    /** POST /question/import  批量导入题目（JSON 数组） */
    importBatch: (p) => request('POST', '/question/import', p, (q) => ({ taskId: 'IMP' + Date.now(), total: (q.questions || []).length, success: (q.questions || []).length, failed: 0 })),

    /**
     * POST /question/packs  生成靶向补练包（针对预警/薄弱点一键出包）
     * body: { kpIds[], userIds[]|classId, count, difficulty }
     */
    createPack: (p) => request('POST', '/question/packs', p, (q) =>
      ({ packId: 'PK' + Date.now(), kpIds: q.kpIds, count: q.count || 6, pushed: true }))
  };

  /* ======================================================================
     九、教师端 · 教学干预与策略
     ====================================================================== */
  const intervention = {
    /** GET /intervention/list  干预建议列表  params: { classId, status, scope } */
    list: (p) => request('GET', '/intervention/list', p, (q) => {
      let list = M().interventions.slice();
      if (q.status && q.status !== 'all') list = list.filter(i => i.status === q.status);
      return { total: list.length, list };
    }),

    /**
     * POST /intervention/{ivId}/confirm  确认执行 / 自定义修改后执行
     * body: { steps?, resources?, note? }
     */
    confirm: (p) => request('POST', `/intervention/${p.ivId}/confirm`, p, (q) =>
      ({ ivId: q.ivId, status: 'running', pushedAt: new Date().toISOString() })),

    /** POST /intervention/{ivId}/reject  忽略该建议 */
    reject: (p) => request('POST', `/intervention/${p.ivId}/reject`, p, () => ({ ivId: p.ivId, status: 'rejected' })),

    /** GET /intervention/{ivId}/effect  干预前后学情对比曲线 */
    effect: (p) => request('GET', `/intervention/${p.ivId}/effect`, p, () => M().interventionEffect),

    /** GET /intervention/templates  策略库模板  params: { scene, keyword } */
    templates: (p) => request('GET', '/intervention/templates', p, () => M().strategyTemplates),

    /** POST /intervention/templates  沉淀新策略模板 */
    saveTemplate: (p) => request('POST', '/intervention/templates', p, (q) =>
      ({ tplId: 'TPL' + Date.now(), name: q.name }))
  };

  /* ======================================================================
     十、教师端 · 学情分析报告
     ====================================================================== */
  const report = {
    /** GET /report/list  历史报告归档  params: { classId, page } */
    list: (p) => request('GET', '/report/list', p, () => ({ total: M().reportList.length, list: M().reportList })),

    /**
     * POST /report/generate  一键生成报告
     * body: { classIds[], chapter?|kpIds[], startDate, endDate, sections[] }
     */
    generate: (p) => request('POST', '/report/generate', p, () =>
      ({ reportId: 'RP' + Date.now(), status: 'ready', detail: M().reportDetail })),

    /** GET /report/{reportId}  报告详情 */
    detail: (p) => request('GET', '/report/' + p.reportId, p, () => M().reportDetail),

    /** POST /report/{reportId}/export  导出  body: { format: pdf|html } */
    exportReport: (p) => request('POST', `/report/${p.reportId}/export`, p, (q) =>
      ({ url: `/files/report/${q.reportId}.${q.format || 'pdf'}`, format: q.format || 'pdf' }))
  };



  return { config, request, auth, graph, student: stu, ai, practice, teacher: tea, analysis, question, intervention, report };
})();
