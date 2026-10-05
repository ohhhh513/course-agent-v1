/* ==========================================================================
   课程智能体系统 · 统一接口层
   --------------------------------------------------------------------------
   1. 所有页面只通过 API.xxx() 取数，请求直连真实后端 /api/v1。
   2. 历史 mock 模式（含本地账号表与 window.MOCK）已于 2026-09-30 彻底移除。
   3. 每个方法上方注释即为接口契约，与 docs/接口文档.md 一一对应。
   ========================================================================== */
window.API = (function () {

  const config = {
    baseURL: '/api/v1',
    token: 'Bearer <JWT>',
    activeCourseId: '', // 当前课程上下文；空=未选课（不发 X-Course-Id，后端取用户第一门课或报错）
  };

  /* 从 localStorage 恢复 token 与当前课程（页面刷新后保持） */
  try {
    const s = JSON.parse(localStorage.getItem('ca_session') || 'null');
    if (s && s.token) {
      config.token = s.token.startsWith('Bearer ') ? s.token : ('Bearer ' + s.token);
    }
    if (s && s.activeCourseId) config.activeCourseId = s.activeCourseId;
  } catch (e) {}

  /**
   * 切换当前课程上下文（多课程）。
   * 只更新请求头来源并持久化；调用方负责在切换后刷新当前视图数据。
   */
  function setActiveCourse(courseId) {
    config.activeCourseId = courseId || '';
    try {
      const s = JSON.parse(localStorage.getItem('ca_session') || 'null') || {};
      s.activeCourseId = config.activeCourseId;
      localStorage.setItem('ca_session', JSON.stringify(s));
    } catch (e) {}
  }

  /* ---------- 底层请求 ---------- */
  /**
   * 统一请求入口
   * @param {'GET'|'POST'|'PUT'|'DELETE'} method
   * @param {string} path      形如 '/student/dashboard'
   * @param {object} payload   GET 为 query，其余为 body
   */
  function request(method, path, payload) {
    const isGet = method === 'GET';
    let url = config.baseURL + path;
    if (isGet && payload) {
      const qs = new URLSearchParams(
        Object.entries(payload).filter(([, v]) => v !== undefined && v !== null && v !== '')
      ).toString();
      if (qs) url += '?' + qs;
    }
    const isFormData = payload instanceof FormData;
    const headers = isFormData
      ? { Authorization: config.token }
      : { 'Content-Type': 'application/json', Authorization: config.token };
    if (config.activeCourseId) headers['X-Course-Id'] = config.activeCourseId;
    return fetch(url, {
      method,
      headers,
      body: isGet ? undefined : (isFormData ? payload : JSON.stringify(payload || {}))
    })
      .then(async r => {
        let res;
        try { res = await r.json(); } catch (e) { res = { code: r.status, message: r.statusText }; }
        // FastAPI HTTPException 只有 detail，没有信封
        if (!r.ok || (res && res.detail && res.code === undefined)) {
          const msg = (res && (res.detail || res.message)) || ('HTTP ' + r.status);
          const err = new Error(typeof msg === 'string' ? msg : '接口异常');
          err.status = r.status;
          throw err;
        }
        if (res.code !== 0) throw new Error(res.message || res.detail || '接口异常');
        return res;
      })
      .then(res => {
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

  /** 下载二进制文件，返回 { blob, filename }，供报告等导出接口使用。 */
  function download(method, path, payload) {
    const isGet = method === 'GET';
    let url = config.baseURL + path;
    if (isGet && payload) {
      const qs = new URLSearchParams(
        Object.entries(payload).filter(([, v]) => v !== undefined && v !== null && v !== '')
      ).toString();
      if (qs) url += '?' + qs;
    }
    return fetch(url, {
      method,
      headers: Object.assign(
        { 'Content-Type': 'application/json', Authorization: config.token },
        config.activeCourseId ? { 'X-Course-Id': config.activeCourseId } : {}
      ),
      body: isGet ? undefined : JSON.stringify(payload || {})
    }).then(async res => {
      const contentType = res.headers.get('content-type') || '';
      const blob = await res.blob();
      if (!res.ok || contentType.includes('application/json')) {
        let message = '文件导出失败';
        try {
          const data = JSON.parse(await blob.text());
          message = data.message || data.detail || (data.data && data.data.error) || message;
        } catch (e) {}
        throw new Error(message);
      }
      const disposition = res.headers.get('content-disposition') || '';
      const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const plain = disposition.match(/filename="?([^";]+)"?/i);
      let filename = encoded ? encoded[1] : (plain ? plain[1] : '');
      if (encoded) {
        try { filename = decodeURIComponent(filename); } catch (e) {}
      }
      return { blob, filename };
    });
  }

  /**
   * SSE 流式请求（fetch + getReader 手动解析，可携带 JWT 头）
   * @param {string} method   一般为 'POST'
   * @param {string} path     形如 '/ai/chat/stream'
   * @param {object} payload  请求体
   * @param {object} handlers 事件回调：{ onMeta, onToolStart, onToolEnd, onContent,
   *                                   onCitations, onDraft, onLog, onDone, onError }
   *                           各回调接收解析后的 data 对象
   * @returns {Promise<void>} 流结束后 resolve；HTTP 非 200 时 reject
   */
  function streamRequest(method, path, payload, handlers) {
    const h = handlers || {};
    let url = config.baseURL + path;
    return fetch(url, {
      method: method || 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: config.token, 'X-Course-Id': config.activeCourseId },
      body: JSON.stringify(payload || {})
    }).then(res => {
      if (!res.ok || !res.body) return res.json().then(r => { throw new Error(r.message || ('HTTP ' + res.status)); });
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buf = '';
      function dispatch(eventName, dataStr) {
        let data;
        try { data = dataStr ? JSON.parse(dataStr) : {}; } catch (e) { data = { raw: dataStr }; }
        switch (eventName) {
          case 'meta':        h.onMeta && h.onMeta(data); break;
          case 'tool_start':  h.onToolStart && h.onToolStart(data); break;
          case 'tool_end':    h.onToolEnd && h.onToolEnd(data); break;
          case 'content':     h.onContent && h.onContent(data); break;
          case 'think':       h.onThink && h.onThink(data); break;
          case 'citations':   h.onCitations && h.onCitations(data); break;
          case 'draft':       h.onDraft && h.onDraft(data); break;
          case 'log':         h.onLog && h.onLog(data); break;
          case 'error':       h.onError && h.onError(data); break;
          case 'done':        h.onDone && h.onDone(data); break;
          default:            h.onEvent && h.onEvent(eventName, data);
        }
      }
      function parseSseBlock(block) {
        let eventName = 'message';
        const dataLines = [];
        block.split(/\r?\n/).forEach(line => {
          if (line.startsWith('event:')) eventName = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));  // 仅去掉字段名后的一个空格，保留 delta 内的前导空格
        });
        if (dataLines.length) dispatch(eventName, dataLines.join('\n'));
      }
      function pump() {
        return reader.read().then(({ done, value }) => {
          if (done) return;
          buf += decoder.decode(value, { stream: true });
          // sse_starlette 使用 \r\n 行尾，事件分隔符是 \r\n\r\n（兼容 \n\n）
          let m;
          while ((m = buf.match(/\r?\n\r?\n/))) {
            const block = buf.slice(0, m.index);
            buf = buf.slice(m.index + m[0].length);
            if (block.trim()) parseSseBlock(block);
          }
          return pump();
        });
      }
      return pump();
    });
  }

  /* ======================================================================
     一、认证与公共
     ====================================================================== */
  const admin = {
    /** GET /admin/users  管理员列表账号 params: { role, keyword } */
    listUsers: (p) => request('GET', '/admin/users', p),
    /** POST /admin/users  创建教师/学生账号 */
    createUser: (p) => request('POST', '/admin/users', p),
    /** PUT /admin/users/{userId}  编辑账号（name/username/密码/班级/部门等，角色不可改） */
    updateUser: (userId, p) => request('PUT', `/admin/users/${userId}`, p),
    /** DELETE /admin/users/{userId}  删除账号（级联清理个人数据） */
    deleteUser: (userId, p) => request('DELETE', `/admin/users/${userId}`, p || {}),
  };

  const auth = {
    /** POST /auth/login  账号密码登录，返回 token 与用户信息 */
    login: (p) => request('POST', '/auth/login', p),

    /** POST /auth/reset-password  找回密码，校验账号后重置密码 */
    resetPassword: (p) => request('POST', '/auth/reset-password', p),

    /** 退出登录：清除本地会话 token */
    logout: () => {
      config.token = 'Bearer <JWT>';
      try {
        const s = JSON.parse(localStorage.getItem('ca_session') || 'null') || {};
        delete s.token;
        localStorage.setItem('ca_session', JSON.stringify(s));
      } catch (e) {}
    },

    /** GET /auth/profile  获取当前登录用户信息（优先取本地会话） */
    profile: () => request('GET', '/auth/profile', {}),

    /** GET /course/{courseId}  获取课程基本信息 */
    course: (p) => request('GET', '/course/' + (p && p.courseId), p)
  };

  /* ======================================================================
     二、三大课程图谱（师生共用）
     ====================================================================== */
  const graph = {
    /** GET /graph  查询图谱数据  params: { courseId, type: knowledge|problem|goal, userId? } */
    get: (p) => request('GET', '/graph', p),

    /** GET /graph/kp/{kpId}  知识点详情（含前后置、资源、习题统计、真实学情与课程均值） */
    kpDetail: (p) => request('GET', '/graph/kp/' + p.kpId, p),

    /** GET /graph/path  基于知识图谱前后置关系生成的推荐学习路径 */
    learningPath: (p) => request('GET', '/graph/path', p)
  };

  /* ======================================================================
     三、学生端
     ====================================================================== */
  const stu = {
    /** GET /student/dashboard  学习驾驶舱聚合数据 */
    dashboard: (p) => request('GET', '/student/dashboard', p),

    /**
     * GET /student/study-duration  当天累计学习时长
     * 返回 { todaySeconds, todayMinutes, practiceSeconds, resourceSeconds }
     * 供驾驶舱「今日累计学习时长」轻量轮询刷新（不触发预警重算）
     */
    studyDuration: () => request('GET', '/student/study-duration'),

    /** GET /student/resources  资源中心列表  params: { type, kpId, keyword, page, size } */
    resources: (p) => request('GET', '/student/resources', p),

    /** POST /student/resources/{res_id}/view  记录资源查看 */
    resourceView: (p) => request('POST', `/student/resources/${p.resId}/view`, {}),

    /** GET /student/resources/{res_id}/progress  获取资源学习进度（视频：秒；文档：页码/百分比） */
    resourceProgress: (resId) => request('GET', `/student/resources/${resId}/progress`),

    /** POST /student/resources/{res_id}/progress  保存学习进度  body={progress,position} */
    saveResourceProgress: (resId, body) => request('POST', `/student/resources/${resId}/progress`, body),

    /** GET /student/resource-stats  资源学习进度统计 */
    resourceStats: () => request('GET', '/student/resource-stats'),

    /** GET /student/mastery/matrix  知识点掌握矩阵（按章节分组） */
    masteryMatrix: (p) => request('GET', '/student/mastery/matrix', p),

    /** GET /student/growth  成长轨迹  params: { dimension: week|month } */
    growth: (p) => request('GET', '/student/growth', p),

    /** GET /student/compare  与班级平均对比 */
    compare: (p) => request('GET', '/student/compare', p),

    /** GET /student/alerts  我的预警列表  params: { level, status } */
    alerts: (p) => request('GET', '/student/alerts', p),

    /** PUT /student/alerts/{alertId}/read  标记预警已读 */
    readAlert: (p) => request('PUT', `/student/alerts/${p.alertId}/read`, p),

    /** GET /student/messages  教师私信 / 系统通知 */
    messages: (p) => request('GET', '/student/messages', p),

    /** PUT /student/messages/{msgId}/read  标记消息已读 */
    readMessage: (p) => request('PUT', `/student/messages/${p.msgId}/read`, p)
  };

  /* ======================================================================
     四、AI 智能辅导与答疑
     ====================================================================== */
  const ai = {
    /** GET /ai/sessions  历史会话列表 */
    sessions: (p) => request('GET', '/ai/sessions', p),

    /** GET /ai/sessions/{sessionId}/messages  会话消息（含溯源引用） */
    messages: (p) => request('GET', `/ai/sessions/${p.sessionId || 'new'}/messages`, p),

    /** DELETE /ai/sessions/{sessionId}  删除会话（仅本人会话，含全部消息） */
    deleteSession: (p) => request('DELETE', `/ai/sessions/${p.sessionId}`, p),

    /**
     * POST /ai/chat/stream  SSE 流式答疑（真实 token 流）
     * handlers: onMeta({sessionId,messageId}) / onToolStart / onToolEnd /
     *           onContent({delta}) / onCitations({items}) / onDone({outOfScope,demo})
     */
    chatStream: (p, handlers) => streamRequest('POST', '/ai/chat/stream', p, handlers),

    /** GET /agent/status  智能体运行状态（live/demo 与模型信息） */

    /** POST /ai/feedback  对回答点赞/点踩，真实写入 ai_feedback（按用户 + 课程归属） */
    feedback: (p) => request('POST', '/ai/feedback', p)
  };

  /* ======================================================================
     五、练习 / 题库（学生侧）
     ====================================================================== */
  const practice = {
    /** GET /practice/modes  练习模式列表（含推荐题量） */
    modes: (p) => request('GET', '/practice/modes', p),

    /**
     * GET /practice/kp-pool  各知识点的已发布题量（顺序练习选章节用）
     * 返回 { counts: { kpId: 题数 }, total }；无题的知识点不在 counts 里。
     */
    kpPool: (p) => request('GET', '/practice/kp-pool', p),

    /**
     * POST /practice/sessions  创建练习会话（组卷）
     * body: { mode: weak|order|random|wrong, kpIds?, count, difficulty? }
     */
    create: (p) => request('POST', '/practice/sessions', p),

    /** GET /practice/sessions/current  当前进行中的练习存档（无则 null）  params: { mode } */
    current: (p) => request('GET', '/practice/sessions/current', p),

    /** GET /practice/sessions/{sessionId}/questions  取题 */
    questions: (p) => request('GET', `/practice/sessions/${p.sessionId}/questions`, p),

    /**
     * POST /practice/answers  提交单题作答，返回即时判分与解析
     * body: { sessionId, qId, answer, durationSeconds }
     */
    submitAnswer: (p) => request('POST', '/practice/answers', p),

    /** POST /practice/sessions/{sessionId}/finish  结束练习，返回练习报告 */
    finish: (p) => request('POST', `/practice/sessions/${p.sessionId}/finish`, p),

    /** GET /practice/wrong-book  错题本  params: { kpId, mastered, page } */
    wrongBook: (p) => request('GET', '/practice/wrong-book', p),

    /** DELETE /practice/wrong-book/{qId}  移出错题本（标记已掌握） */
    removeWrong: (p) => request('DELETE', '/practice/wrong-book/' + p.qId, p),

    /** GET /practice/wrong-book/{qId}  错题详情（含完整题目、解析、错题历史、相似题、推荐资源） */
    wrongDetail: (p) => request('GET', '/practice/wrong-book/' + p.qId + '/detail', p)
  };

  /* ======================================================================
     六、教师端 · 学情监测
     ====================================================================== */
  const tea = {
    /** GET /teacher/dashboard  教学驾驶舱  params: { classId } */
    dashboard: (p) => request('GET', '/teacher/dashboard', p),

    /** GET /teacher/heatmap  知识点 × 学生 热力图  params: { classId, dimension: day|week|month } */
    heatmap: (p) => request('GET', '/teacher/heatmap', p),

    /** GET /teacher/students  学生列表  params: { classId, alertLevel, keyword, sortBy, page } */
    students: (p) => request('GET', '/teacher/students', p),

    /** GET /teacher/students/{userId}/profile  个体学情详情（画像 + 轨迹 + 答题明细） */
    studentProfile: (p) => request('GET', `/teacher/students/${p.userId}/profile`, p),

    /** GET /teacher/alerts  预警列表  params: { classId, level, status, type, kpId, page } */
    alerts: (p) => request('GET', '/teacher/alerts', p),

    /**
     * PUT /teacher/alerts/{alertId}/review  人工复核预警
     * body: { action: confirm|ignore|annotate, note? }
     */
    reviewAlert: (p) => request('PUT', `/teacher/alerts/${p.alertId}/review`, p),

    /** POST /teacher/messages  向学生发送私信（含改进建议） */
    sendMessage: (p) => request('POST', '/teacher/messages', p),

    /** GET /teacher/classes  当前教师所带班级（真实数据，来自数据库） */
    classes: () => request('GET', '/teacher/classes'),

    /** GET /teacher/resources  教师资源管理列表  params: { keyword } */
    resources: (p) => request('GET', '/teacher/resources', p),

    /** GET /teacher/resources/kps  上传时可选择的知识点（按章节分组） */
    resourceKps: () => request('GET', '/teacher/resources/kps'),

    /** POST /teacher/resources/upload  上传资源  body: FormData { file, title, kp, category, tagIds? } */
    uploadResource: (formData) => request('POST', '/teacher/resources/upload', formData),

    /** PUT /teacher/resources/{res_id}  编辑资源（标题/知识点/标签） */
    updateResource: (resId, p) => request('PUT', `/teacher/resources/${resId}`, p),

    /** DELETE /teacher/resources/{res_id}  删除资源 */
    deleteResource: (resId) => request('DELETE', `/teacher/resources/${resId}`),

    /** GET /teacher/tags  当前课程标签列表 */
    tags: () => request('GET', '/teacher/tags'),
    /** POST /teacher/tags  新建（或复用）标签 */
    createTag: (p) => request('POST', '/teacher/tags', p),
    /** DELETE /teacher/tags/{tagId}  删除标签 */
    deleteTag: (tagId) => request('DELETE', `/teacher/tags/${tagId}`),

    /** GET /teacher/resources/{res_id}/rag-status  查询上传后的 RAG 切片进度 */
    resourceRagStatus: (resId) => request('GET', `/teacher/resources/${resId}/rag-status`),

    /** POST /teacher/courses  新建课程（生成邀请码，教师自动成为成员） */
    createCourse: (p) => request('POST', '/teacher/courses', p),

    /** GET /teacher/structure  课程结构（章节树 + 知识点 + 统计） */
    structure: () => request('GET', '/teacher/structure'),
    /** POST /teacher/structure/chapters  新建章节 */
    createChapter: (p) => request('POST', '/teacher/structure/chapters', p),
    /** PUT /teacher/structure/chapters/{id}  改章节（重命名同步章下知识点） */
    updateChapter: (id, p) => request('PUT', `/teacher/structure/chapters/${id}`, p),
    /** DELETE /teacher/structure/chapters/{id}  删空章节 */
    deleteChapter: (id) => request('DELETE', `/teacher/structure/chapters/${id}`),
    /** GET /teacher/graph/kp-detail  知识点详情（结构 + 图谱关系 + 课程学情，全部真实表计算） */
    kpDetail: (p) => request('GET', '/teacher/graph/kp-detail', p),
    /** GET /teacher/graph/kp-topology  知识图谱拓扑（节点=课程KP，边=关系） */
    kpTopology: () => request('GET', '/teacher/graph/kp-topology'),
    /** PUT /teacher/graph/kp-topology  保存坐标与边 */
    saveKpTopology: (p) => request('PUT', '/teacher/graph/kp-topology', p),

    /** POST /teacher/structure/kps  新建知识点（自动重建全员学习路径） */
    createKp: (p) => request('POST', '/teacher/structure/kps', p),
    /** PUT /teacher/structure/kps/{id}  改知识点 */
    updateKp: (id, p) => request('PUT', `/teacher/structure/kps/${id}`, p),
    /** DELETE /teacher/structure/kps/{id}  删知识点（有资源/题目时 400 拒绝） */
    deleteKp: (id) => request('DELETE', `/teacher/structure/kps/${id}`),
    /** GET /teacher/structure/kps/{id}/relations  前置列表 + 候选 */
    kpRelations: (id) => request('GET', `/teacher/structure/kps/${id}/relations`),
    /** PUT /teacher/structure/kps/{id}/relations  覆盖保存前置（环检测） */
    saveKpRelations: (id, p) => request('PUT', `/teacher/structure/kps/${id}/relations`, p),

    /** POST /question/import  批量导入题目（含单题；支持 figure_json 图结构） */
    importQuestions: (p) => request('POST', '/question/import', p)
  };

  /* ======================================================================
     七、教师端 · 归因与错题分析
     ====================================================================== */
  const analysis = {
    /** GET /analysis/errors  错题与归因分析  params: { classId, chapter, kpId, timeRange } */
    errors: (p) => request('GET', '/analysis/errors', p)
  };

  /* ======================================================================
     八、教师端 · AI 出题与题库管理
     ====================================================================== */
  const question = {
    /** GET /question/gen/config  出题配置项（知识点、题型） */
    genConfig: (p) => request('GET', '/question/gen/config', p),

    /**
     * POST /question/gen  AI 生成习题
     * body: { materialIds[], kpIds[], types[], difficulty, count, skillId?, requirement? }
     */
    generate: (p) => request('POST', '/question/gen', p),

    /**
     * POST /question/gen  SSE 流式智能出题（真实 LLM 生成，草稿只存个人会话历史）
     * handlers: onMeta({batchId,count}) / onDraft({draftId,status,errors,payload}) /
     *           onLog(过程事件) / onDone({batchId,draftIds,count,demo}) / onError
     */
    genStream: (p, handlers) => streamRequest('POST', '/question/gen', p, handlers),

    /** GET /agent/ingest/stats  RAG 知识库切片统计（教师） */
    ingestStats: (p) => request('GET', '/agent/ingest/stats', p),

    /** GET /question/drafts  我的出题草稿箱  params: { status: draft|published }（2026-09-24 移除 all/invalid） */
    drafts: (p) => request('GET', '/question/drafts', p),

    /** PUT /question/drafts/{draftId}  编辑草稿（保存时后端重新校验） */
    draftUpdate: (p) => request('PUT', '/question/drafts/' + p.draftId, { payload: p.payload }),

    /** DELETE /question/drafts/{draftId}  删除草稿 */
    draftDelete: (p) => request('DELETE', '/question/drafts/' + p.draftId, p),

    /** POST /question/drafts/{draftId}/publish  发布草稿 → 正式题库 */
    draftPublish: (p) => request('POST', '/question/drafts/' + p.draftId + '/publish', p),

    /** GET /question/bank  题库列表  params: { kpId, type, difficulty, keyword, page, sort, dir }
     *  2026-09-24：去掉 status 维度，改为按正确率/难度/知识点/默认 排序（sort=correctRate|difficulty|kp|default, dir=asc|desc）。
    bank: (p) => request('GET', '/question/bank', p),

    /** PUT /question/{qId}  编辑习题（含 figureJson/hasImage/tagIds） */
    update: (p) => request('PUT', '/question/' + p.qId, p),

    /** POST /question/review  批量审核发布  body: { qIds[], action: approve|reject|publish } */
    review: (p) => request('POST', '/question/review', p),

    /** DELETE /question/{qId}  删除习题 */
    remove: (p) => request('DELETE', '/question/' + p.qId, p),

    /** POST /question/import  批量导入题目（JSON 数组） */
    importBatch: (p) => request('POST', '/question/import', p),

  };

  /* ======================================================================
     九、教师端 · 教学干预与策略
     ====================================================================== */
  const intervention = {
    /** GET /intervention/list  干预建议列表  params: { classId, status, scope } */
    list: (p) => request('GET', '/intervention/list', p),

    /**
     * POST /intervention/{ivId}/confirm  确认执行 / 自定义修改后执行
     * body: { steps?, resources?, note? }
     */
    confirm: (p) => request('POST', `/intervention/${p.ivId}/confirm`, p),

    /** POST /intervention/{ivId}/reject  忽略该建议 */
    reject: (p) => request('POST', `/intervention/${p.ivId}/reject`, p),

    /** GET /intervention/templates  策略库模板  params: { scene, keyword } */
    templates: (p) => request('GET', '/intervention/templates', p),

    /** POST /intervention/templates  沉淀新策略模板 */
    saveTemplate: (p) => request('POST', '/intervention/templates', p)
  };

  /* ======================================================================
     十、教师端 · 学情分析报告
     ====================================================================== */
  const report = {
    /** GET /report/list  历史报告归档  params: { classId, page } */
    list: (p) => request('GET', '/report/list', p),

    /**
     * POST /report/generate  一键生成报告
     * body: { classIds[], chapter?|kpIds[], startDate, endDate, sections[] }
     */
    generate: (p) => request('POST', '/report/generate', p),

    /** GET /report/{reportId}  报告详情 */
    detail: (p) => request('GET', '/report/' + p.reportId, p),

    /** POST /report/{reportId}/export  导出  body: { format: pdf|html } */
    exportReport: (p) => download('POST', `/report/${p.reportId}/export`, p)
  };

  /* ---------- 课程（多课程上下文） ---------- */
  const course = {
    /** GET /course/my  当前用户的课程列表（含 role，课程教师另带 inviteCode） */
    my: () => request('GET', '/course/my'),

    /** POST /course/join  凭邀请码加入课程  body: { inviteCode } */
    join: (p) => request('POST', '/course/join', p),
  };

  return { config, request, download, setActiveCourse, course, auth, admin, graph, student: stu, ai, practice, teacher: tea, analysis, question, intervention, report };
})();
