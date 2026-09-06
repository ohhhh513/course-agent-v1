'use strict';

  /* ================================================================
     视图 4 · AI 智能答疑
     ================================================================ */

  /**
   * 轻量 Markdown → HTML 渲染（讲解 Agent 输出为 Markdown）。
   * 支持：**加粗** / *斜体* / `行内代码` / ```代码块``` / #~###### 标题 /
   *       - 无序列表 / 1. 有序列表 / > 引用 / 空行分段。
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
    // 3) 块级：按空行分段，段内识别标题/列表/引用
    const html = text.split(/\n{2,}/).map(par => {
      const blocks = [];
      let list = null;
      const flushList = () => { if (list) { blocks.push('</' + list + '>'); list = null; } };
      par.split('\n').forEach(raw => {
        const line = raw.replace(/\r$/, '');
        const fence = line.match(/^\s*\u0000F(\d+)\u0000\s*$/);
        if (fence) { flushList(); blocks.push(fences[+fence[1]]); return; }
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

  const Chat = {
    method: 'guided', busy: false, sessionId: 'new',

    render() {
      const el = U.$('#view-ai');
      el.innerHTML = `
      <div class="chat-shell">
        <div class="card chat">
          <div class="chat__method">
            <span class="fz-12 t-dim nowrap">教学法</span>
            <div class="chips" id="methodChips"></div>
            <span class="spacer"></span>
            <button class="btn btn--ghost btn--sm" id="newSessBtn">${icon('plus')} 新建会话</button>
            <span class="badge badge--ok">${icon('shield')} 严格溯源</span>
          </div>
          <div class="chat__log" id="chatLog"></div>
          <div class="chat__input">
            <div class="composer">
              <textarea id="chatInput" rows="1" placeholder="输入你的问题，Enter 发送 / Shift+Enter 换行"></textarea>
              <div class="composer__acts">
                <button class="btn btn--ghost btn--icon btn--sm">${icon('upload')}</button>
                <button class="btn btn--primary btn--icon" id="chatSend">${icon('send')}</button>
              </div>
            </div>
          </div>
        </div>

        <div class="stack">
          <div class="card">
            <div class="card__head"><h3>${icon('bulb')} 猜你想问</h3></div>
            <div class="card__body card__body--tight" id="askBox"></div>
          </div>
          <div class="card">
            <div class="card__head"><h3>${icon('clock')} 历史会话</h3></div>
            <div class="card__body card__body--flush"><div class="list" id="sessBox"></div></div>
          </div>
        </div>
      </div>`;

      // 教学法
      API.ai.methods().then(ms => {
        U.$('#methodChips').innerHTML = ms.map(m =>
          `<button class="chip ${m.key === this.method ? 'is-active' : ''}" data-m="${m.key}" title="${m.desc}">${icon(m.icon)}${m.name}</button>`).join('');
        U.$$('#methodChips .chip').forEach(c => c.addEventListener('click', () => {
          U.$$('#methodChips .chip').forEach(x => x.classList.remove('is-active'));
          c.classList.add('is-active');
          this.method = c.dataset.m;
          const m = ms.find(x => x.key === this.method);
          Toast.info('已切换为' + m.name, m.desc);
        }));
      });

      // 初始消息
      this.loadSession('new');

      // 侧栏
      API.ai.suggestQuestions().then(qs => {
        U.$('#askBox').innerHTML = qs.map(q => `<button class="ask-item" data-ask="${U.esc(q)}">${icon('bulb')}<span>${U.esc(q)}</span></button>`).join('');
        U.$$('#askBox [data-ask]').forEach(b => b.addEventListener('click', () => this.ask(b.dataset.ask)));
      });
      API.ai.sessions().then(r => {
        U.$('#sessBox').innerHTML = r.list.map(s => `
          <div class="list__item list__item--clickable" data-sid="${U.esc(s.sessionId)}">
            <div class="list__main"><b class="clamp-2">${U.esc(s.title)}</b>
              <p>${s.time} · ${s.rounds} 轮 · ${U.esc(s.kp)}</p></div>
          </div>`).join('');
        // 绑定点击事件
        U.$$('#sessBox [data-sid]').forEach(item => {
          item.addEventListener('click', () => {
            const sid = item.dataset.sid;
            // 切换 active 样式
            U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
            item.classList.add('is-active');
            this.loadSession(sid);
          });
        });
        // 点击第一个历史会话（如果有）自动加载
        if (r.list.length) {
          const first = U.$('#sessBox [data-sid]');
          first.classList.add('is-active');
          this.loadSession(first.dataset.sid);
        }
      });

      // 发送
      const input = U.$('#chatInput');
      const send = () => { const v = input.value.trim(); if (v) { input.value = ''; input.style.height = 'auto'; this.ask(v); } };
      U.$('#chatSend').addEventListener('click', send);
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      });
      input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 148) + 'px';
      });

      // 新建会话
      U.$('#newSessBtn')?.addEventListener('click', () => {
        this.loadSession('new');
        U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
        Toast.info('已创建新会话');
      });
    },

    tpl(m) {
      const now = m.time || new Date().toTimeString().slice(0, 5);
      if (m.role === 'me') {
        return `<div class="msg msg--me"><div class="msg__av">陈</div>
          <div class="msg__wrap"><div class="bubble">${U.esc(m.content)}</div>
          <div class="msg__meta"><span>${now}</span></div></div></div>`;
      }
      const mName = { lecture: '讲授法', guided: '引导式', case: '案例式', heuristic: '启发式', fun: '趣味式' }[m.method] || '引导式';
      const cites = (m.citations || []);
      return `<div class="msg msg--ai"><div class="msg__av">AI</div>
        <div class="msg__wrap">
          <div class="bubble">${mdToHtml(m.content)}
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
            ${m.outOfScope ? `<div class="callout callout--warn" style="margin-top:10px">${icon('alert')}<div><b>超出课程材料范围</b>已按「严格溯源」约束拒绝推测性回答，可点击下方转人工。</div></div>` : ''}
          </div>
          <div class="msg__meta">
            <span class="badge badge--outline">${mName}</span>
            <span>${now}</span>
            <span class="spacer"></span>
            <span class="msg__acts">
              <button data-fb="up">${icon('thumbUp')}</button>
              <button data-fb="down">${icon('thumbDown')}</button>
              <button>${icon('copy')}</button>
              ${m.outOfScope ? `<button class="btn btn--xs btn--outline" style="margin-left:6px">转人工</button>` : ''}
            </span>
          </div>
        </div></div>`;
    },

    bindCites() {
      U.$$('.cite__head', U.$('#chatLog')).forEach(h => {
        if (h.dataset.bound) return;
        h.dataset.bound = '1';
        h.addEventListener('click', () => h.closest('.cite').classList.toggle('is-open'));
      });
      U.$$('[data-fb]', U.$('#chatLog')).forEach(b => {
        if (b.dataset.bound) return;
        b.dataset.bound = '1';
        b.addEventListener('click', () => {
          API.ai.feedback({ type: b.dataset.fb });
          Toast.ok('反馈已提交', '将用于 AI 知识库迭代优化');
        });
      });
    },

    // 防外部注入：清除 chatLog 内任何不在我们白名单内的可疑 SVG / 文本水印
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
      const log = U.$('#chatLog');
      if (!log) return;

      // 'new' 会话：不请求后端（后端返回空数组），直接显示欢迎界面
      if (!sid || sid === 'new') {
        log.innerHTML = `
          <div class="msg msg--ai">
            <div class="msg__av">AI</div>
            <div class="msg__wrap">
              <div class="bubble">
                <b>👋 你好！我是你的 AI 助教</b>
                <p style="margin:8px 0 0;color:var(--text-2)">你可以向我提问课程相关的问题，我会结合教材、课件和教学视频为你解答。试试从下方选择一个问题，或直接在输入框提问吧！</p>
              </div>
            </div>
          </div>`;
        this.scroll();
        return;
      }

      log.innerHTML = `<div class="msg msg--ai"><div class="msg__av">AI</div><div class="msg__wrap"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span> <span class="fz-12 t-dim">加载会话中…</span></div></div></div>`;
      API.ai.messages({ sessionId: sid }).then(list => {
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
      if (Router.current !== 'ai') Router.go('ai');
      const log = U.$('#chatLog');
      if (!log || this.busy) return;
      this.busy = true;

      log.insertAdjacentHTML('beforeend', this.tpl({ role: 'me', content: question }));
      // 流式 AI 气泡：delta 逐段累积渲染；结束后替换为完整 tpl（含溯源折叠块）
      log.insertAdjacentHTML('beforeend',
        `<div class="msg msg--ai" id="streamMsg"><div class="msg__av">AI</div><div class="msg__wrap">
          <div class="bubble"><span id="streamText"></span><span class="typing" id="streamCursor"><i></i><i></i><i></i></span>
          <div class="fz-12 t-dim" id="streamTool" style="margin-top:6px"></div></div></div></div>`);
      this.scroll();

      const $id = (id) => U.$('#' + id);
      const setText = (html) => { const t = $id('streamText'); if (t) t.innerHTML = html; };
      const appendDelta = (delta) => {
        // Markdown 增量：按累积全文重渲染（约数百字，开销可忽略），保证半截语法也能正常显示
        this._acc = (this._acc || '') + delta;
        setText(mdToHtml(this._acc));
        this.scroll();
      };
      const toolLine = (name, end) => {
        const el = $id('streamTool');
        if (!el) return;
        el.textContent = end ? `✓ ${name} 完成` : `正在调用 ${name} …`;
      };
      const finish = (payload) => {
        const sm = $id('streamMsg');
        if (sm) sm.remove();
        this._acc = '';
        const cites = (payload.citations || []).map(c => ({
          source: c.source || c.source_id || c.section || '课程资料',
          locator: c.locator || c.section || '',
          quote: c.quote || c.snippet || '',
          kp: c.kp || c.section || ''
        }));
        log.insertAdjacentHTML('beforeend', this.tpl({
          role: 'ai', method: this.method, content: mdToHtml(this._final || ''),
          citations: cites, outOfScope: payload.outOfScope,
        }));
        this._final = '';
        this.bindCites();
        this.scrubLog(log);
        this.scroll();
        this.busy = false;
        this.refreshSessions();
      };
      const fail = (msg) => {
        const sm = $id('streamMsg');
        if (sm) sm.remove();
        this._acc = ''; this._final = '';
        log.insertAdjacentHTML('beforeend', this.tpl({
          role: 'ai', method: this.method,
          content: `<p>${U.esc(msg || '回答生成失败，请稍后重试')}</p>`, citations: [], outOfScope: false,
        }));
        this.bindCites();
        this.scroll();
        this.busy = false;
      };

      API.ai.chatStream(
        { question, method: this.method, sessionId: this.sessionId },
        {
          onMeta: (d) => { if (d.sessionId && d.sessionId !== this.sessionId) this.sessionId = d.sessionId; },
          onToolStart: (d) => toolLine(d.name, false),
          onToolEnd: (d) => toolLine(d.name, true),
          onContent: (d) => {
            const c = $id('streamCursor'); if (c) c.remove();
            // content 事件 data 为 JSON（{delta}）；兼容潜在的裸文本/解析降级形态
            const delta = typeof d === 'string' ? d : (d && (d.delta != null ? d.delta : d.raw)) || '';
            appendDelta(delta);
          },
          onCitations: (d) => { this._cites = (d && d.items) || []; },
          onLog: () => {},
          onDraft: () => {},
          onError: (d) => fail(d && d.message),
          onDone: (d) => {
            this._final = this._acc || '';
            finish({ citations: this._cites || [], outOfScope: !!(d && d.outOfScope) });
          },
        }
      ).catch((e) => fail(e && e.message));
    },

    refreshSessions() {
      API.ai.sessions().then(r => {
        const box = U.$('#sessBox');
        if (box) {
          box.innerHTML = r.list.map(s => `
            <div class="list__item list__item--clickable ${s.sessionId === this.sessionId ? 'is-active' : ''}" data-sid="${U.esc(s.sessionId)}">
              <div class="list__main"><b class="clamp-2">${U.esc(s.title)}</b>
                <p>${s.time} · ${s.rounds} 轮 · ${U.esc(s.kp)}</p></div>
            </div>`).join('');
          U.$$('#sessBox [data-sid]').forEach(item => {
            item.addEventListener('click', () => {
              const sid = item.dataset.sid;
              U.$$('#sessBox [data-sid]').forEach(x => x.classList.remove('is-active'));
              item.classList.add('is-active');
              this.loadSession(sid);
            });
          });
        }
      });
    }
  };

Router.register('ai', { title: 'AI 智能答疑', mount: () => Chat.render() });
