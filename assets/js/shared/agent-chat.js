/* ==========================================================================
   共享答疑视图工厂（学生端「AI 智能答疑」/ 教师端「智能答疑」共用）
   --------------------------------------------------------------------------
   用法：AgentChatView.create(config) 返回一个 Chat 对象，各端在自己的视图模块里注册：

       const Chat = AgentChatView.create({ viewKey: 'ai', containerId: '#view-ai', ... });
       Router.register('ai', { title: 'AI 智能答疑', mount: () => Chat.render() });

   两端差异全部由 config 提供（容器、顶部徽标、欢迎语、推荐问题、界面动作白名单），
   渲染与流式解析只有这一份实现，避免两端各写一遍后行为漂移。
   依赖全局：U / Toast / Router / API / Auth / icon。
   ========================================================================== */
window.AgentChatView = (function () {
  'use strict';

  /**
   * 轻量 Markdown → HTML 渲染（讲解 Agent 输出为 Markdown）。
   * 支持：**加粗** / *斜体* / `行内代码` / ```代码块``` / #~###### 标题 /
   *       - 无序列表 / 1. 有序列表 / > 引用 / **| 表格 |** / 空行分段。
   * 表格会渲染成真 `<table>`（不再是原始竖线文本），见下方 tableHtml()。
   * 旧版 mock 存量消息是 HTML，本渲染器对其原样放行，二者兼容。
   */
  function mdToHtml(src) {
    if (src == null) return '';
    let text = String(src);
    // 1) 先摘出 fenced 代码块，避免块内语法被二次转换
    const fences = [];
    text = text.replace(/```[a-zA-Z0-9_-]*\r?\n?([\s\S]*?)```/g, (_, code) => {
      fences.push('<pre class="md-pre"><code>' + code.replace(/\n$/, '') + '</code></pre>');
      return '\n\u0000F' + (fences.length - 1) + '\u0000\n';
    });
    // 2) 行内语法
    const inline = (s) => s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');

    // 2.5) 表格：先整体摘出「表头 + |---|---| 分隔行 + 数据行」的连续块，
    //      换成占位符，避免被下面的逐行逻辑当成普通段落（那样只会得到一排竖线）。
    const tables = [];
    const isRow = (l) => /^\s*\|.*\|\s*$/.test(l || '');
    const cellsOf = (l) => String(l).trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
    // 分隔行：每格只由 - 和可选的对齐冒号组成（GFM 允许单横线，如 |:-:|）
    const isSep = (l) => isRow(l) && cellsOf(l).every(c => /^:?-+:?$/.test(c));
    // 列对齐：分隔行写了 :--- / :---: / ---: 就按它，没写就**默认居中**。
    // 关键：**同一列的表头与数据行共用一份对齐** —— 早前表头左对齐、数字列却右对齐，
    // 于是出现「内容对不上标题列」的错位观感。
    const alignOf = (l) => cellsOf(l).map(c => (/^:-+:$/.test(c) ? 'center' : (/-+:$/.test(c) ? 'right' : (/^:-+/.test(c) ? 'left' : ''))));
    const alignAttr = (a) => ' class="md-' + (a || 'center') + '"';
    const tableHtml = (head, aligns, rows) => {
      const colAlign = head.map((_, i) => aligns[i] || 'center');
      const th = head.map((h, i) => '<th' + alignAttr(colAlign[i]) + '>' + inline(h) + '</th>').join('');
      const body = rows.map(r => '<tr>' + head.map((_, i) => {
        const t = r[i] == null ? '' : r[i];
        return '<td' + alignAttr(colAlign[i]) + '>' + inline(t) + '</td>';
      }).join('') + '</tr>').join('');
      return '<div class="md-table-wrap"><table class="md-table"><thead><tr>' + th +
        '</tr></thead><tbody>' + body + '</tbody></table></div>';
    };
    {
      const out = [];
      const lines = text.split('\n');
      let i = 0;
      while (i < lines.length) {
        // 表头行的下一行必须是分隔行，才算一张表（否则只是普通带竖线的句子）
        if (isRow(lines[i]) && isSep(lines[i + 1] || '')) {
          const head = cellsOf(lines[i]);
          const aligns = alignOf(lines[i + 1]);
          i += 2;
          const rows = [];
          while (i < lines.length && isRow(lines[i])) { rows.push(cellsOf(lines[i])); i++; }
          tables.push(tableHtml(head, aligns, rows));
          out.push('\u0000T' + (tables.length - 1) + '\u0000');
        } else {
          out.push(lines[i]);
          i++;
        }
      }
      text = out.join('\n');
    }

    // 3) 块级：按空行分段，段内识别标题/列表/引用/表格
    const html = text.split(/\n{2,}/).map(par => {
      const blocks = [];
      let list = null;
      const flushList = () => { if (list) { blocks.push('</' + list + '>'); list = null; } };
      par.split('\n').forEach(raw => {
        const line = raw.replace(/\r$/, '');
        const fence = line.match(/^\s*\u0000F(\d+)\u0000\s*$/);
        if (fence) { flushList(); blocks.push(fences[+fence[1]]); return; }
        const tbl = line.match(/^\s*\u0000T(\d+)\u0000\s*$/);
        if (tbl) { flushList(); blocks.push(tables[+tbl[1]]); return; }
        const h = line.match(/^(#{1,6})\s+(.*)/);
        if (h) { flushList(); blocks.push('<div class="md-h md-h' + h[1].length + '">' + inline(h[2]) + '</div>'); return; }
        const ul = line.match(/^\s*[-*•]\s+(.*)/);
        if (ul) { if (list !== 'ul') { flushList(); blocks.push('<ul class="md-list">'); list = 'ul'; } blocks.push('<li>' + inline(ul[1]) + '</li>'); return; }
        const ol = line.match(/^\s*\d+[.、)]\s+(.*)/);
        if (ol) { if (list !== 'ol') { flushList(); blocks.push('<ol class="md-list">'); list = 'ol'; } blocks.push('<li>' + inline(ol[1]) + '</li>'); return; }
        const bq = line.match(/^\s*>\s?(.*)/);
        if (bq) { flushList(); blocks.push('<blockquote class="md-quote">' + inline(bq[1]) + '</blockquote>'); return; }
        if (!line.trim()) { flushList(); return; }
        flushList();
        blocks.push(inline(line) + '<br>');
      });
      flushList();
      return blocks.join('');
    }).join('');
    return html.replace(/(<br>\s*)+$/, '');   // 去掉末尾多余换行
  }

  /* ---------- 待批准写操作卡片（P2c）：答疑页与出题页共用同一套渲染与交互 ---------- */

  /** 卡片 HTML：做什么 + 关键参数 + 影响面 + 确认/拒绝 + 状态标签 */
  function confirmCardHtml(c) {
    const status = c.status || 'pending';
    const stateText = { pending: '待批准', executed: '已执行', rejected: '已拒绝' }[status] || status;
    const canAct = status === 'pending';
    return `<div class="confirm-card is-${U.esc(status)}" data-action-id="${U.esc(c.actionId)}">
      <div class="confirm-card__head">${icon('shield')}<b>待你确认的写操作</b>
        <span class="confirm-card__state">${U.esc(stateText)}</span></div>
      <div class="confirm-card__body">
        <div class="confirm-card__what">${U.esc(c.summary || '')}</div>
        ${c.impact ? `<div class="confirm-card__impact">影响：${U.esc(c.impact)}</div>` : ''}
        <div class="confirm-card__tool">工具 <code>${U.esc(c.tool || '')}</code></div>
      </div>
      ${canAct ? `<div class="confirm-card__acts">
        <button class="btn btn--primary btn--sm" data-confirm="approve">确认执行</button>
        <button class="btn btn--outline btn--sm" data-confirm="reject">拒绝</button>
      </div>` : ''}
    </div>`;
  }

  /** 执行结果 → 卡片上那句「发生了什么」（出题写草稿 / 账号录入 / 账号删除 / 其它动作） */
  function _doneText(res) {
    const r = (res && res.result) || {};
    if (r.draft_id) return '已写入草稿（' + U.esc(r.draft_id) + '）';
    if (typeof r.created === 'number') {
      return '已创建 ' + r.created + ' 个账号' + (r.skipped ? '、跳过 ' + r.skipped + ' 个' : '');
    }
    if (typeof r.deleted === 'number') {
      return '已删除 ' + r.deleted + ' 个账号' + (r.refused ? '、被拒 ' + r.refused + ' 个' : '');
    }
    return '已执行';
  }

  /**
   * 复制一条 AI 回答的正文。
   * 取 `.bubble__body` 的 innerText —— 刻意**只复制回答本身**：
   * 不含「思考与工具调用」面板、溯源引用、待批准卡片与建议按钮，也不含自己的提问。
   * 表格在 innerText 里天然是「制表符分列 + 换行分行」，粘进 Excel / 文档仍是表格。
   * 剪贴板 API 在非安全上下文（如 http://局域网IP）不可用，退回 execCommand 兜底。
   */
  function copyAnswer(btn) {
    const msg = btn.closest('.msg');
    const body = msg && msg.querySelector('.bubble__body');
    const text = (body ? body.innerText : '').replace(/\n{3,}/g, '\n\n').trim();
    if (!text) { Toast.warn('这条回答没有可复制的文本'); return; }
    const done = () => Toast.ok('已复制', '回答正文已复制到剪贴板');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => {
        if (_fallbackCopy(text)) done();
        else Toast.err('复制失败', '浏览器拒绝了剪贴板访问，可手动选中文本复制');
      });
    } else if (_fallbackCopy(text)) {
      done();
    } else {
      Toast.err('复制失败', '当前环境不支持自动复制，可手动选中文本复制');
    }
  }

  /** 老浏览器 / 非 HTTPS 下的复制兜底（隐藏 textarea + execCommand）。 */
  function _fallbackCopy(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e) {
      return false;
    }
  }

  function _setCardState(card, status, res) {
    card.classList.remove('is-pending', 'is-executed', 'is-rejected');
    card.classList.add('is-' + status);
    const st = U.$('.confirm-card__state', card);
    if (st) st.textContent = { executed: '已执行', rejected: '已拒绝' }[status] || status;
    const acts = U.$('.confirm-card__acts', card);
    if (!acts) return;
    if (status === 'executed') {
      acts.innerHTML = `<span class="confirm-card__done">${icon('shield')} ${_doneText(res)}</span>`;
    } else {
      acts.innerHTML = `<span class="confirm-card__done">已拒绝，未产生任何写入</span>`;
    }
  }

  /**
   * 点击「确认执行 / 拒绝」：只把 actionId 发给后端，参数以服务端落库的那份为准。
   * @param {HTMLElement} btn       被点的按钮
   * @param {Function}    onChange  状态变化后重新绑定按钮（各页面自己的重绑逻辑）
   * @param {object}      apiGroup  该视图的接口组（答疑端 = API.ai，管理员端 = API.adminAgent）；
   *                                不传默认走 API.ai，兼容既有调用方（如教师出题页）
   */
  function resolveConfirm(btn, onChange, apiGroup) {
    const card = btn.closest('.confirm-card');
    if (!card) return;
    const actionId = card.dataset.actionId;
    const kind = btn.dataset.confirm;                 // approve | reject
    const acts = U.$('.confirm-card__acts', card);
    const restore = () => {
      if (acts) {
        acts.innerHTML = `<button class="btn btn--primary btn--sm" data-confirm="approve">确认执行</button>
          <button class="btn btn--outline btn--sm" data-confirm="reject">拒绝</button>`;
      }
      if (onChange) onChange();
    };
    if (acts) acts.innerHTML = `<span class="fz-12 t-dim">${kind === 'approve' ? '执行中…' : '处理中…'}</span>`;
    const A = apiGroup || API.ai;
    const call = kind === 'approve' ? A.approveAction : A.rejectAction;
    call({ actionId }).then(r => {
      _setCardState(card, kind === 'approve' ? 'executed' : 'rejected', r);
      if (kind === 'approve') {
        const rs = (r && r.result) || {};
        const hint = rs.draft_id ? ('草稿 ' + rs.draft_id + ' 已写入你的草稿箱')
          : (typeof rs.created === 'number'
            ? ('已创建 ' + rs.created + ' 个账号' + (rs.skipped ? '，跳过 ' + rs.skipped + ' 个（重名）' : ''))
            : (typeof rs.deleted === 'number'
              ? ('已删除 ' + rs.deleted + ' 个账号' + (rs.refused ? '，' + rs.refused + ' 个被拒（原因见报告）' : ''))
              : '该动作已执行'));
        Toast.ok('已确认执行', hint);
      } else {
        Toast.info('已拒绝', '没有产生任何写入');
      }
    }).catch(err => {
      restore();
      Toast.err(kind === 'approve' ? '确认失败' : '拒绝失败', (err && err.message) || '请稍后重试');
    });
  }

  /** 在 root 内绑定所有确认/拒绝按钮（幂等：dataset.bound 防重复绑定） */
  function bindConfirms(root, onChange, apiGroup) {
    const scope = root || document;
    scope.querySelectorAll('[data-confirm]').forEach(b => {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', () => resolveConfirm(b, onChange, apiGroup));
    });
  }

  /**
   * 创建一个答疑视图实例。
   * @param {object} config
   *   viewKey      路由键（'ai' / 'chat'），用于 Router.go 与 #view-<key>
   *   containerId  视图容器选择器（'#view-ai'）
   *   badges       顶部徽标 HTML（各端不同）
   *   placeholder  输入框 placeholder
   *   welcomeHtml  新建会话时的欢迎气泡 HTML
   *   recommended  () => Promise<string[]>  推荐问题（「猜你想问」）
   *   applyAction  (action) => boolean      界面动作白名单执行器（各端页面不同）
   *   emptyRecommend / recommendFail        推荐区兜底文案
   */
  function create(config) {
    const cfg = Object.assign({
      viewKey: '',
      containerId: '',
      badges: '',
      placeholder: '输入你的问题，Enter 发送 / Shift+Enter 换行',
      welcomeHtml: '',
      recommended: () => Promise.resolve([]),
      applyAction: () => false,
      emptyRecommend: '暂无推荐问题',
      recommendFail: '推荐问题加载失败',
      // 接口来源：默认走 /ai/*（学生 / 教师答疑）；管理员治理流传 { api: API.adminAgent }
      // 切到 /admin/agent/* —— 事件协议完全一致，只是端点与角色闸门不同。
      api: null,
      // 附件上传：由各端显式开启（学生端「AI 智能答疑」、教师端「智能答疑」、
      // 管理端「智能助手」均为 true）。
      // 关闭的端**不渲染**上传按钮，避免出现点了没反应的占位按钮。
      // 上限与后端 services/attachments.py 保持一致。
      allowUpload: false,
    }, config || {});
    const A = cfg.api || API.ai;   // 本实例使用的接口组（sessions / messages / chatStream / deleteSession）

    const Chat = {
      method: 'guided', busy: false, sessionId: 'new',   // method 字段保留仅为 API 兼容
      pendingDraft: null,   // 其他视图带入的待提问草稿：只填入输入框，绝不自动发送
      pendingFiles: [],     // 待发送附件（File 对象；仅 allowUpload 端会用到）
      _ctrl: null,          // 本轮流式请求的 AbortController（「停止生成」用）
      _stopped: false,      // 用户点了停止 → 收尾时保留「已生成的部分」而不是报错
      _settled: false,      // 本轮是否已收尾（finish/fail），防止 abort 与 done 双重渲染

      render() {
        const el = U.$(cfg.containerId);
        if (!el) return;
        el.innerHTML = `
        <div class="chat-shell">
          <div class="card chat">
            <div class="chat__method">
              ${cfg.badges}
              <span class="spacer"></span>
              <button class="btn btn--ghost btn--sm" id="newSessBtn">${icon('plus')} 新建会话</button>
            </div>
            <div class="chat__log" id="chatLog"></div>
            <div class="chat__input">
              ${cfg.allowUpload ? '<div class="att-tray" id="attTray" hidden></div>' : ''}
              <div class="composer">
                <textarea id="chatInput" rows="1" placeholder="${U.esc(cfg.placeholder)}"></textarea>
                <div class="composer__acts">
                  <button class="btn btn--ghost btn--icon btn--sm" id="chatUpload" type="button">${icon('upload')}</button>
                  <button class="btn btn--primary btn--icon" id="chatSend">${icon('send')}</button>
                </div>
              </div>
              ${cfg.allowUpload ? '<input type="file" id="chatFile" multiple hidden accept=".txt,.md,.csv,.json,.xlsx,.docx,.pdf">' : ''}
            </div>
          </div>

          <div class="stack">
            <div class="card">
              <div class="card__head"><h3>${icon('bulb')} 猜你想问</h3></div>
              <div class="card__body card__body--tight" id="askBox" style="max-height:188px;overflow-y:auto"></div>
            </div>
            <div class="card">
              <div class="card__head"><h3>${icon('clock')} 历史会话</h3></div>
              <div class="card__body card__body--flush"><div class="list" id="sessBox"></div></div>
            </div>
          </div>
        </div>`;

        // 初始消息
        this.loadSession('new');

        // 侧栏 · 猜你想问：问题清单由各端配置提供（学生端取驾驶舱推荐，教师端为教师向问题）
        Promise.resolve().then(() => cfg.recommended()).then(qs0 => {
          const qs = (qs0 || []).slice(0, 4);
          const box = U.$('#askBox');
          if (!box) return;
          box.innerHTML = qs.length
            ? qs.map(q => `<button class="ask-item" data-ask="${U.esc(q)}">${icon('bulb')}<span>${U.esc(q)}</span></button>`).join('')
            : `<p class="fz-12 t-dim" style="padding:4px 2px">${U.esc(cfg.emptyRecommend)}</p>`;
          // 点击「猜你想问」只把问题填进输入框，不直接发送：
          // 统一为「帮你把问题写好，发不发由你决定」。
          U.$$('#askBox [data-ask]').forEach(b => b.addEventListener('click', () => this.fillInput(b.dataset.ask)));
        }).catch(() => {
          const box = U.$('#askBox');
          if (box) box.innerHTML = `<p class="fz-12 t-dim" style="padding:4px 2px">${U.esc(cfg.recommendFail)}</p>`;
        });
        A.sessions().then(r => this.renderSessions(r, true));

        // 发送 / 停止（主流智能体形态：同一个按钮，生成中变成「停止」）
        const input = U.$('#chatInput');
        const submit = () => {
          if (this.busy) return;             // 生成中按 Enter 不发送（也不会误触停止）
          const v = input.value.trim();
          if (v) { input.value = ''; input.style.height = 'auto'; this.ask(v); }
        };
        U.$('#chatSend').addEventListener('click', () => {
          if (this.busy) { this.stop(); return; }
          submit();
        });
        input.addEventListener('keydown', e => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
        });
        this._setSendMode(false);            // 初始态（重进页面时复位）
        input.addEventListener('input', () => {
          input.style.height = 'auto';
          input.style.height = Math.min(input.scrollHeight, 148) + 'px';
        });

        // 附件上传（仅开启 allowUpload 的端）：选文件 → chips → 随本轮问题提交
        if (cfg.allowUpload) this._bindUpload();

        // 新建会话
        U.$('#newSessBtn')?.addEventListener('click', () => {
          this.loadSession('new');
          U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
          Toast.info('已创建新会话');
        });

        // 其他视图带入的草稿：填入输入框，由用户自行决定是否发送
        this._applyPendingDraft();
      },

      /**
       * 供其他视图调用：跳到答疑页并新建会话，把问题填入输入框（不自动发送）。
       * 取代旧的「Router.go + setTimeout(ask)」模式——那会在用户最近一次会话里
       * 直接发出请求，既打断历史上下文又不符合直觉。
       */
      draft(question) {
        this.pendingDraft = question;
        Router.go(cfg.viewKey);
        // Router.go 会同步完成首次 mount（render 已消费草稿）；
        // 若视图此前已挂载（不会重跑 render），在这里补一次。
        if (U.$('#chatInput')) {
          this.loadSession('new');
          U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
          this._applyPendingDraft();
        }
      },

      _applyPendingDraft() {
        const t = this.pendingDraft;
        if (!t) return;
        this.pendingDraft = null;
        this.fillInput(t, true);   // 跨页带入：页面切换本身已是反馈，不再额外提示
      },

      /**
       * 把文字填进输入框：不发送、不切换会话、不清空当前对话。
       * silent=true 时不弹提示（用于跨页带入的草稿）。
       */
      fillInput(question, silent) {
        const input = U.$('#chatInput');
        if (!input || !question) return;
        input.value = question;
        input.dispatchEvent(new Event('input'));   // 触发输入框自适应高度
        input.focus();
        if (!silent) Toast.info('已填入输入框', '确认或修改后发送');
      },

      /* ---------- 附件（仅 allowUpload 的端启用；上限与后端 MAX_ATTACH_* 一致） ---------- */

      _bindUpload() {
        const btn = U.$('#chatUpload');
        const input = U.$('#chatFile');
        if (!btn || !input) return;
        btn.addEventListener('click', () => input.click());
        input.addEventListener('change', () => {
          const picked = Array.from(input.files || []);
          input.value = '';                  // 允许再次选择同一个文件
          this._addFiles(picked);
        });
      },

      _addFiles(files) {
        const MAX_N = 5, MAX_MB = 10;
        const allowed = /\.(txt|md|csv|json|xlsx|docx|pdf)$/i;
        for (const f of (files || [])) {
          if (this.pendingFiles.length >= MAX_N) {
            Toast.warn('最多 5 个附件', '请先移除部分附件再继续选择');
            break;
          }
          if (!allowed.test(f.name)) {
            Toast.warn('不支持的附件类型', f.name + '：仅支持 txt / md / csv / json / xlsx / docx / pdf');
            continue;
          }
          if (f.size > MAX_MB * 1024 * 1024) {
            Toast.warn('附件过大', f.name + ' 超过 10MB');
            continue;
          }
          if (this.pendingFiles.some(x => x.name === f.name && x.size === f.size)) continue;
          this.pendingFiles.push(f);
        }
        this._renderTray();
      },

      _renderTray() {
        const tray = U.$('#attTray');
        if (!tray) return;
        const list = this.pendingFiles || [];
        if (!list.length) { tray.hidden = true; tray.innerHTML = ''; return; }
        tray.hidden = false;
        tray.innerHTML = list.map((f, i) => `<span class="att-chip">
            ${icon('file')}<span class="att-chip__name">${U.esc(f.name)}</span>
            <b class="att-chip__del" data-att-del="${i}" title="移除">${icon('x')}</b></span>`).join('');
        U.$$('#attTray [data-att-del]').forEach(b => b.addEventListener('click', () => {
          this.pendingFiles.splice(+b.dataset.attDel, 1);
          this._renderTray();
        }));
      },

      /**
       * 一条用户消息上的附件 chips。两个来源：
       * ① 实时轮 —— 发送时直接挂在消息对象上（m.attachments）；
       * ② 历史消息 —— 消息接口不返回 attachments，从随消息落库的 toolLog
       *    （{kind:'attach', files:[...]}）重建（与 suggestCardsOf 同一模式）。
       */
      attachChipsOf(m) {
        if (m && m.attachments && m.attachments.length) return m.attachments;
        const out = [];
        ((m && m.toolLog) || []).forEach(x => {
          if (x && x.kind === 'attach' && Array.isArray(x.files)) {
            x.files.forEach(f => { if (f && f.name) out.push({ name: f.name }); });
          }
        });
        return out;
      },

      /**
       * 思考与工具调用折叠面板（模仿常见智能体 UI）。
       * entries 兼容两种格式：
       *   新：{kind:'think', text} / {kind:'tool', name, args, ok}
       *   旧：{name, args, ok}
       */
      toolsPanelHtml(entries, isOpen) {
        // meta 条目是随消息落库的内部标记（如越界判定），不是工具调用，不进面板
        entries = (entries || []).filter(e => e && e.kind !== 'meta');
        if (!entries.length) return '';
        // live 标记只允许存在一个（最后一个），避免重复 id="thinkLive" 导致内容写错位置
        const liveIdx = entries.reduce((acc, e, i) => (e.live ? i : acc), -1);
        const rows = entries.map((e, i) => {
          const kind = e.kind || (e.text ? 'think' : 'tool');
          if (kind === 'think') {
            const liveId = i === liveIdx ? ' id="thinkLive"' : '';
            return `<div class="tools__think">${icon('bulb')}<span${liveId}>${U.esc(e.text || '')}</span></div>`;
          }
          const running = e.ok === undefined || e.ok === null;
          const waiting = !running && !!e.pending;           // 写操作被闸门拦下 = 待批准
          const dot = running ? 'is-run' : (waiting ? 'is-pend' : (e.ok ? 'is-ok' : 'is-bad'));
          const stateText = running ? '运行中…' : (waiting ? '待批准' : (e.ok ? '完成' : '失败'));
          const args = JSON.stringify(e.args || {});
          const short = args.length > 150 ? args.slice(0, 150) + '…' : args;
          return `<div class="tools__item">
            <span class="tools__dot ${dot}"></span>
            <b>${U.esc(e.name || '工具')}</b>
            <span class="tools__state">${stateText}</span>
            <code class="tools__args" title="${U.esc(args)}">${U.esc(short)}</code>
          </div>`;
        }).join('');
        return `<div class="tools ${isOpen ? 'is-open' : ''}">
          <button class="tools__head">${icon('bot')} 思考与工具调用（${entries.length}）<span class="caret" style="width:14px;height:14px">${icon('chevronDown')}</span></button>
          <div class="tools__body">${rows}</div>
        </div>`;
      },

      /** 当前登录用户头像（与顶栏 user-chip 同一数据源：Auth.currentUser） */
      _meAvatar() {
        const u = (window.Auth && Auth.currentUser) ? Auth.currentUser() : null;
        return {
          ch: (u && (u.avatarChar || (u.name ? u.name.charAt(0) : null))) || '我',
          color: (u && u.avatarColor) || ''
        };
      },

      tpl(m) {
        const now = m.time || new Date().toTimeString().slice(0, 5);
        const confirms = this.confirmCardsOf(m);                          // 待批准 / 已处理的写操作
        const suggests = this.suggestCardsOf(m);                          // 只读建议（历史从 toolLog 重建）
        const oos = this.outOfScopeOf(m);                                 // 越界（历史从 toolLog 里的 meta 标记恢复）
        if (m.role === 'me') {
          const me = this._meAvatar();
          const atts = this.attachChipsOf(m);
          return `<div class="msg msg--me"><div class="msg__av"${me.color ? ` style="background:${me.color}"` : ''}>${U.esc(me.ch)}</div>
            <div class="msg__wrap"><div class="bubble">${U.esc(m.content)}${atts.length ? `
              <span class="bubble__atts">${atts.map(a => `<span class="att-chip">${icon('file')}<span class="att-chip__name">${U.esc(a.name || '')}</span></span>`).join('')}</span>` : ''}</div>
            <div class="msg__meta"><span>${now}</span></div></div></div>`;
        }
        const mName = { lecture: '讲授法', guided: '引导式', case: '案例式', heuristic: '启发式', fun: '趣味式' }[m.method] || '';
        const cites = (m.citations || []);
        return `<div class="msg msg--ai"><div class="msg__av">AI</div>
          <div class="msg__wrap">
            <div class="bubble">${this.toolsPanelHtml(m.toolLog, false)}<div class="bubble__body">${mdToHtml(m.content)}</div>
              ${cites.length ? `
              <div class="cite">
                <button class="cite__head">${icon('shield')} 原文溯源（${cites.length} 处）<span class="caret" style="width:14px;height:14px">${icon('chevronDown')}</span></button>
                <div class="cite__body">
                  ${cites.map(c => `<div class="cite-item">
                    <div class="cite-item__src">${icon('quote')} ${U.esc(c.source)}</div>
                    <blockquote>${U.esc(c.quote)}</blockquote>
                    <div class="cite-item__meta">定位：${U.esc(c.locator)} · 知识点：${U.esc(c.kp)}</div>
                  </div>`).join('')}
                </div>
              </div>` : ''}
              ${oos ? `<div class="callout callout--warn" style="margin-top:10px">${icon('alert')}<div><b>超出课程材料范围</b>已按「严格溯源」约束拒绝推测性回答，建议换一个更贴近课程知识点的问法。</div></div>` : ''}
              ${confirms.length ? `<div class="msg__confirms">${confirms.map(c => confirmCardHtml(c)).join('')}</div>` : ''}
              ${suggests.length ? `
              <div class="msg__agent-acts">
                <span class="msg__acts-tag">${icon('eye')} 只读建议 · 点击跳转，不会修改任何数据</span>
                ${suggests.map((a, i) => `<button class="btn btn--sm ${i === 0 ? 'btn--primary' : 'btn--outline'}"
                  data-agent-action="${U.esc(JSON.stringify(a))}">${U.esc(a.label || '打开')}</button>`).join('')}
              </div>` : ''}
            </div>
            <div class="msg__meta">
              ${mName ? `<span class="badge badge--outline">${mName}</span>` : ''}
              <span>${now}</span>
              <span class="spacer"></span>
              <span class="msg__acts">
                <button data-fb="up" title="有帮助">${icon('thumbUp')}</button>
                <button data-fb="down" title="没帮助">${icon('thumbDown')}</button>
                <button data-copy="1" title="复制回答">${icon('copy')}</button>
              </span>
            </div>
          </div></div>`;
      },

      /**
       * 这条回答是否被判成「超出课程材料范围」。
       * 两个来源：① 本轮实时 —— SSE done 事件里的 outOfScope；
       *          ② 历史消息 —— 消息接口不返回该字段，从 toolLog 里随消息落库的
       *             {kind:'meta', out_of_scope:true} 标记恢复。
       * （该判定依赖本轮的检索分与话题确定性，事后无法重算，所以由服务端存下来。）
       */
      outOfScopeOf(m) {
        if (!m) return false;
        if (m.outOfScope) return true;
        const log = m.toolLog || [];
        return log.some(x => x && x.kind === 'meta' && x.out_of_scope);
      },

      /**
       * 一条 AI 消息里要渲染的「待批准写操作」卡片。
       * 两个来源：① 历史消息 —— 动作随 tool_log 落库（状态是最新的）；
       *          ② 本轮实时 —— action 事件透出的 kind=confirm。
       * 按 actionId 去重后输出。
       */
      confirmCardsOf(m) {
        const out = [];
        const seen = {};
        const push = (c) => {
          if (!c || !c.actionId || seen[c.actionId]) return;
          seen[c.actionId] = 1;
          out.push(c);
        };
        (m.toolLog || []).forEach(x => {
          if (x && x.kind === 'action') {
            push({ actionId: x.action_id, tool: x.tool, summary: x.summary, impact: x.impact, status: x.status });
          }
        });
        (m.actions || []).forEach(a => {
          if (a && a.kind === 'confirm') {
            push({ actionId: a.actionId, tool: a.tool, summary: a.summary, impact: a.impact, status: a.status });
          }
        });
        return out;
      },

      /**
       * 只读建议按钮（`suggest_action` 的结果）。两个来源，按「kind + 目标」去重后输出：
       * ① 历史消息 —— 后端 `/ai/sessions/{id}/messages` **不返回 actions**，所以从 `toolLog` 里
       *    该工具的调用参数重建（与 confirmCardsOf 同一思路：落库的工具日志就是权威来源）；
       *    被拒的调用（ok=false，如 view 不在白名单）不重建，避免渲染出点不动的按钮。
       * ② 本轮实时 —— `action` 事件透出的非 confirm 项。
       */
      suggestCardsOf(m) {
        const out = [];
        const seen = {};
        const push = (a) => {
          if (!a || !a.label || (a.kind !== 'navigate' && a.kind !== 'practice')) return;
          const key = a.kind === 'navigate' ? 'nav:' + a.view : 'prac:' + a.kpId;
          if (seen[key]) return;
          seen[key] = 1;
          out.push(a);
        };
        (m.toolLog || []).forEach(x => {
          if (!x || x.kind !== 'tool' || x.name !== 'suggest_action' || x.ok === false) return;
          const args = x.args || {};
          if (args.kind === 'navigate') {
            push({ kind: 'navigate', label: args.label, view: args.view });
          } else if (args.kind === 'practice') {
            push({ kind: 'practice', label: args.label, kpId: args.kp_id, kpName: args.kp_name || '', mode: args.mode });
          }
        });
        (m.actions || []).forEach(a => {
          if (!a || a.kind === 'confirm') return;
          push({ kind: a.kind, label: a.label, view: a.view, kpId: a.kpId, kpName: a.kpName, mode: a.mode });
        });
        return out;
      },

      bindCites() {
        U.$$('.cite__head', U.$('#chatLog')).forEach(h => {
          if (h.dataset.bound) return;
          h.dataset.bound = '1';
          h.addEventListener('click', () => h.closest('.cite').classList.toggle('is-open'));
        });
        // 思考/工具折叠面板（历史消息与最终消息）
        U.$$('.tools__head', U.$('#chatLog')).forEach(h => {
          if (h.dataset.bound) return;
          h.dataset.bound = '1';
          h.addEventListener('click', () => h.closest('.tools').classList.toggle('is-open'));
        });
        U.$$('[data-fb]', U.$('#chatLog')).forEach(b => {
          if (b.dataset.bound) return;
          b.dataset.bound = '1';
          b.addEventListener('click', () => {
            API.ai.feedback({ type: b.dataset.fb });
            Toast.ok('反馈已提交', '将用于 AI 知识库迭代优化');
          });
        });
        // 复制回答（此前是死按钮：渲染了图标但没有任何事件与剪贴板调用）
        U.$$('[data-copy]', U.$('#chatLog')).forEach(b => {
          if (b.dataset.bound) return;
          b.dataset.bound = '1';
          b.addEventListener('click', () => copyAnswer(b));
        });
        // AI 建议的界面动作（工具 suggest_action 的结果）：白名单校验后才执行
        U.$$('[data-agent-action]', U.$('#chatLog')).forEach(b => {
          if (b.dataset.bound) return;
          b.dataset.bound = '1';
          b.addEventListener('click', () => {
            let act = null;
            try { act = JSON.parse(b.dataset.agentAction || 'null'); } catch (e) { act = null; }
            if (!cfg.applyAction(act)) {
              Toast.warn('这个建议暂时无法直接打开', '请从左侧导航手动进入');
            }
          });
        });
        // 待批准写操作（P2c）：确认 / 拒绝 —— 直接调后端接口，参数以服务端落库的为准。
        // apiGroup 用本实例的接口组：学生/教师走 /agent/actions/*，管理员走 /admin/agent/actions/*。
        bindConfirms(U.$('#chatLog'), () => this.bindCites(), A);
      },

      // 防外部注入：清除 chatLog 内任何不在白名单内的可疑 SVG / 文本水印
      scrubLog(log) {
        if (!log) return;
        const badText = /作曲|编曲|WJCTION|小咪|网易云|netease|cloud-?music/i;
        log.querySelectorAll('img, svg').forEach(el => {
          if (!el.closest('.msg, .callout, .typing')) el.remove();
        });
        log.querySelectorAll('*').forEach(el => {
          if (!el.className && el.childElementCount === 0 && badText.test(el.textContent || '')) el.remove();
        });
      },

      scroll() {
        const log = U.$('#chatLog');
        if (log) log.scrollTop = log.scrollHeight;
      },

      loadSession(sid) {
        this.sessionId = sid;
        // 切换/新建会话时清空待发附件（附件属于当前这次提问，不跨会话携带）
        this.pendingFiles = [];
        this._renderTray();
        const log = U.$('#chatLog');
        if (!log) return;

        // 'new' 会话：不请求后端（后端返回空数组），直接显示欢迎界面
        if (!sid || sid === 'new') {
          log.innerHTML = `<div class="msg msg--ai"><div class="msg__av">AI</div>
            <div class="msg__wrap"><div class="bubble">${cfg.welcomeHtml}</div></div></div>`;
          this.scroll();
          return;
        }

        log.innerHTML = `<div class="msg msg--ai"><div class="msg__av">AI</div><div class="msg__wrap"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span> <span class="fz-12 t-dim">加载会话中…</span></div></div></div>`;
        A.messages({ sessionId: sid }).then(list => {
          if (!list || list.length === 0) {
            log.innerHTML = `<div class="msg msg--ai"><div class="msg__av">AI</div><div class="msg__wrap"><div class="bubble t-dim">该会话暂无消息，可能已被清理</div></div></div>`;
          } else {
            log.innerHTML = list.map(m => this.tpl(m)).join('');
          }
          this.scrubLog(log);
          this.bindCites();
          this.scroll();
        }).catch(() => {
          log.innerHTML = `<div class="msg msg--ai"><div class="msg__av">AI</div><div class="msg__wrap"><div class="bubble t-dim">加载会话失败，请重试</div></div></div>`;
        });
      },

      ask(question) {
        if (Router.current !== cfg.viewKey) Router.go(cfg.viewKey);
        const log = U.$('#chatLog');
        if (!log || this.busy) return;
        // 附件随本轮提交：先快照再清空待发区（发送中的文件列表不随后续选择变化）
        const files = (this.pendingFiles || []).slice();
        this.pendingFiles = [];
        this._renderTray();
        this.busy = true;
        this._acc = ''; this._final = ''; this._cites = []; this._actions = [];
        this._tools = [];          // 思考/工具条目（{kind:'think'|'tool', ...}）
        this._toolsOpen = false;   // 流式期间面板折叠，可点击展开
        // 「停止生成」：本轮一个可中止的信号 + 收尾标记；按钮切成停止态
        this._stopped = false;
        this._settled = false;
        this._ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        this._setSendMode(true);

        log.insertAdjacentHTML('beforeend', this.tpl({
          role: 'me', content: question, attachments: files.map(f => ({ name: f.name })),
        }));
        // 流式 AI 气泡：可折叠思考/工具面板 + 实时正文
        log.insertAdjacentHTML('beforeend',
          `<div class="msg msg--ai" id="streamMsg"><div class="msg__av">AI</div><div class="msg__wrap">
            <div class="bubble"><span id="streamPanel"></span><span id="streamText"></span><span class="typing" id="streamCursor"><i></i><i></i><i></i></span></div></div></div>`);
        this.scroll();

        const $id = (id) => U.$('#' + id);
        const setText = (html) => { const t = $id('streamText'); if (t) t.innerHTML = html; };
        const renderPanel = () => {
          const p = $id('streamPanel');
          if (!p) return;
          p.innerHTML = this.toolsPanelHtml(this._tools, this._toolsOpen);
          const head = p.querySelector('.tools__head');
          if (head) head.addEventListener('click', () => {
            this._toolsOpen = !this._toolsOpen;
            p.querySelector('.tools').classList.toggle('is-open', this._toolsOpen);
          });
        };
        const appendDelta = (delta) => {
          // Markdown 增量：按累积全文重渲染（约数百字，开销可忽略），保证半截语法也能正常显示
          this._acc += delta;
          setText(mdToHtml(this._acc));
          this.scroll();
        };
        // 编排轮的过渡文本 → 收进折叠面板的"思考"区（模仿智能体行为）
        const flushAccToThink = () => {
          const text = this._acc.trim();
          if (text) {
            this._tools.push({ kind: 'think', text });
            const i = this._acc.lastIndexOf(text);
            this._acc = i >= 0 ? this._acc.slice(0, i) + this._acc.slice(i + text.length) : '';
            setText(mdToHtml(this._acc));
          }
        };

        const finish = (payload) => {
          const sm = $id('streamMsg');
          if (sm) sm.remove();
          const cites = (payload.citations || []).map(c => ({
            source: c.source || c.source_id || c.section || '课程资料',
            locator: c.locator || c.section || '',
            quote: c.quote || c.snippet || '',
            kp: c.kp || c.section || ''
          }));
          log.insertAdjacentHTML('beforeend', this.tpl({
            role: 'ai', content: mdToHtml(this._final || ''),
            citations: cites, outOfScope: payload.outOfScope,
            toolLog: this._tools,
            actions: this._actions || [],
          }));
          this._acc = ''; this._final = ''; this._tools = []; this._actions = [];
          this.bindCites();
          this.scrubLog(log);
          this.scroll();
          this.busy = false;
          this._settled = true;
          this._ctrl = null;
          this._setSendMode(false);
          this.refreshSessions();
        };
        const fail = (msg) => {
          const sm = $id('streamMsg');
          if (sm) sm.remove();
          this._acc = ''; this._final = ''; this._tools = []; this._actions = [];
          log.insertAdjacentHTML('beforeend', this.tpl({
            role: 'ai',
            content: `<p>${U.esc(msg || '回答生成失败，请稍后重试')}</p>`, citations: [], outOfScope: false,
          }));
          this.bindCites();
          this.scroll();
          this.busy = false;
          this._settled = true;
          this._ctrl = null;
          this._setSendMode(false);
        };

        // 停止时的收尾：保留「已经生成的部分」，不报错、不提示失败（与主流智能体一致）
        const finishStopped = () => {
          this._stopped = false;
          this._final = this._acc || '';
          const sm = $id('streamMsg');
          if (sm) sm.remove();
          if ((this._final || '').trim() || (this._tools || []).length) {
            this._settled = true;
            finish({ citations: this._cites || [], outOfScope: false });
          } else {
            // 一个字都没生成：不留空气泡，直接回到空闲态
            this._acc = ''; this._final = ''; this._tools = []; this._actions = [];
            this.busy = false;
            this._settled = true;
            this._ctrl = null;
            this._setSendMode(false);
            this.scroll();
          }
        };

        A.chatStream(
          { question, sessionId: this.sessionId, files: files },
          {
            onMeta: (d) => { if (d.sessionId && d.sessionId !== this.sessionId) this.sessionId = d.sessionId; },
            onToolStart: (d) => {
              const c = $id('streamCursor'); if (c) c.remove();
              // 新工具轮开始：结束所有未完成的 think 条目（防止跨轮拼接与重复 id）
              this._tools.forEach(e => { if (e.live) e.live = false; });
              flushAccToThink();
              this._tools.push({ kind: 'tool', name: d.name, args: d.args, ok: null });  // null=运行中
              renderPanel();
              this.scroll();
            },
            onToolEnd: (d) => {
              const entry = [...this._tools].reverse().find(x => x.kind === 'tool' && x.name === d.name && x.ok === null);
              if (entry) entry.ok = true;
              renderPanel();
            },
            onContent: (d) => {
              const c = $id('streamCursor'); if (c) c.remove();
              // content 事件 data 为 JSON（{delta}）；兼容潜在的裸文本/解析降级形态
              const delta = typeof d === 'string' ? d : (d && (d.delta != null ? d.delta : d.raw)) || '';
              appendDelta(delta);
            },
            onThink: (d) => {
              // 模型内部推理实时流入折叠面板（轻量更新，不整面板重渲染）
              const delta = typeof d === 'string' ? d : (d && (d.delta != null ? d.delta : d.raw)) || '';
              if (!delta) return;
              let entry = this._tools[this._tools.length - 1];
              if (!entry || entry.kind !== 'think' || !entry.live) {
                this._tools.push({ kind: 'think', text: '', live: true });
                renderPanel();
                entry = this._tools[this._tools.length - 1];
              }
              entry.text += delta;
              const span = document.getElementById('thinkLive');
              if (span) span.textContent = entry.text;
              const now = Date.now();
              if (now - (this._lastScroll || 0) > 300) { this._lastScroll = now; this.scroll(); }
            },
            onCitations: (d) => { this._cites = (d && d.items) || []; },
            onAction: (d) => { this._actions = (d && d.actions) || []; },
            onLog: () => {},
            onDraft: () => {},
            onError: (d) => fail(d && d.message),
            onDone: (d) => {
              if (this._settled) return;      // 已被「停止」收尾过就不再重复渲染
              this._final = this._acc || '';
              finish({ citations: this._cites || [], outOfScope: !!(d && d.outOfScope) });
            },
          },
          // 「停止生成」：AbortSignal 交给 fetch，点停止时立即中止并走 finishStopped()
          { signal: this._ctrl ? this._ctrl.signal : undefined }
        ).catch((e) => {
          if (this._stopped && !this._settled) { finishStopped(); return; }
          if (!this._settled) fail(e && e.message);
        });
      },

      /**
       * 发送按钮的两种形态（主流智能体形态）：空闲 = 发送，生成中 = 停止。
       * 三端共用（学生 / 教师 / 管理员答疑页都是这一个模块）。
       */
      _setSendMode(busy) {
        const btn = U.$('#chatSend');
        if (!btn) return;
        btn.innerHTML = icon(busy ? 'square' : 'send');
        btn.title = busy ? '停止生成' : '发送';
        btn.classList.toggle('is-stopping', !!busy);
      },

      /**
       * 停止生成：先请服务端在本轮的下个检查点收尾（把已生成的部分落库），
       * 再中止前端这条 SSE 连接 —— 立即回到空闲态，保留已经显示出来的内容。
       */
      stop() {
        if (!this.busy) return;
        this._stopped = true;
        const sid = this.sessionId;
        if (sid && sid !== 'new' && A.stopChat) {
          // 先请服务端收尾（失败也不阻塞 UI；吞掉 rejection，避免未捕获异常）
          Promise.resolve().then(() => A.stopChat({ sessionId: sid })).catch(() => {});
        }
        if (this._ctrl && this._ctrl.abort) {
          try { this._ctrl.abort(); } catch (e) { /* 已结束则忽略 */ }
        }
      },

      /**
       * 渲染右侧历史会话列表（含悬停删除按钮，两次点击确认删除）
       * @param {object} r  A.sessions 的返回 {total, list}
       * @param {boolean} autoSelect  是否自动选中并加载第一个会话（仅首挂载）
       */
      renderSessions(r, autoSelect) {
        const box = U.$('#sessBox');
        if (!box) return;
        const list = (r && r.list) || [];
        box.innerHTML = list.map(s => `
          <div class="list__item list__item--clickable ${s.sessionId === this.sessionId ? 'is-active' : ''}" data-sid="${U.esc(s.sessionId)}">
            <div class="list__main"><b class="clamp-2">${U.esc(s.title)}</b>
              <p>${s.time} · ${s.rounds} 轮 · ${U.esc(s.kp)}</p></div>
            <button class="sess-del" data-del="${U.esc(s.sessionId)}" title="删除会话">${icon('trash')}</button>
          </div>`).join('');
        // 打开会话
        U.$$('#sessBox [data-sid]').forEach(item => {
          item.addEventListener('click', () => {
            const sid = item.dataset.sid;
            U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
            item.classList.add('is-active');
            this.loadSession(sid);
          });
        });
        // 删除（两次点击确认，避免误删）
        U.$$('#sessBox [data-del]').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const sid = btn.dataset.del;
            if (!btn.dataset.armed) {
              btn.dataset.armed = '1';
              btn.classList.add('is-arm');
              btn.title = '再次点击确认删除';
              setTimeout(() => { btn.dataset.armed = ''; btn.classList.remove('is-arm'); btn.title = '删除会话'; }, 3000);
              return;
            }
            A.deleteSession({ sessionId: sid }).then(() => {
              Toast.ok('会话已删除');
              if (sid === this.sessionId) {
                this.sessionId = 'new';
                this.loadSession('new');
              }
              A.sessions().then(r2 => this.renderSessions(r2, false));
            }).catch(err => Toast.err('删除失败', err && err.message));
          });
        });
        // 首挂载自动选中第一个历史会话
        if (autoSelect && list.length) {
          const first = U.$('#sessBox [data-sid]');
          first.classList.add('is-active');
          this.loadSession(first.dataset.sid);
        }
      },

      refreshSessions() {
        A.sessions().then(r => this.renderSessions(r, false));
      }
    };

    return Chat;
  }

  return {
    create: create,
    mdToHtml: mdToHtml,
    // 待批准写操作卡片：出题页（teacher/views/question.js）等其它页面复用同一套渲染与交互
    confirmCardHtml: confirmCardHtml,
    bindConfirms: bindConfirms,
  };
})();
