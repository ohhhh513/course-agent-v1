'use strict';

/* ================================================================
   视图 · 智能助手（管理员端 · 平台治理流）
   渲染 / 流式 / 会话逻辑在 assets/js/shared/agent-chat.js，
   这里只提供管理员端配置 + 治理流端点（API.adminAgent → /admin/agent/*）。
   管理员流的工具全部是 admin-only：5 个只读治理查询（system_overview /
   account_overview / course_overview / kb_status / data_check）+ 账号治理写操作
   （preview_account_import 只读 / import_accounts 写；preview_account_delete 只读 /
   delete_accounts 写 —— 两个写操作都挂审批闸门，确认卡片确认后才落库）。
   教师 / 学生拿不到也调不到；管理员也进不了 explain / 出题流。
   ================================================================ */

const AdminChat = AgentChatView.create({
  viewKey: 'assistant',
  containerId: '#view-assistant',
  badges: `<span class="badge badge--ok">${icon('shield')} 平台治理</span>
           <span class="badge badge--outline">${icon('grid')} 全平台 · 写操作需确认</span>`,
  placeholder: '问平台情况，例如「系统现在什么状态」，Enter 发送 / Shift+Enter 换行',
  welcomeHtml: `<b>👋 平台治理助手</b>
    <p style="margin:8px 0 0;color:var(--text-2)">你可以问平台运行与治理情况：账号与课程规模、题库 / 资源数据量、
    知识库索引状态、数据一致性体检。数据实时取自平台真实业务表；<b>上传学生／教师信息文件（或点名用户名）可生成
    账号录入 / 删除动作，需你在卡片上确认后才会写入或删除</b>。</p>`,
  // 管理员向推荐问题（静态清单）
  recommended: () => Promise.resolve([
    '系统现在什么状态？',
    '平台一共有多少数据？',
    '知识库索引情况怎么样？要不要重建索引？',
    '帮我做一次数据体检',
  ]),

  // 管理员端暂无界面动作入口：任何建议按钮都不执行
  applyAction: () => false,

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
    AdminChat.sessionId = 'new';
  },
});
