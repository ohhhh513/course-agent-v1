'use strict';

  /* ================================================================
     视图 4 · AI 智能答疑
     ================================================================ */
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
          <div class="bubble">${m.content}
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
      log.insertAdjacentHTML('beforeend',
        `<div class="msg msg--ai" id="typing"><div class="msg__av">AI</div><div class="msg__wrap">
          <div class="bubble"><span class="typing"><i></i><i></i><i></i></span>
          <span class="fz-12 t-dim" style="margin-left:6px">正在检索课程材料…</span></div></div></div>`);
      this.scroll();

      API.ai.chat({ question, method: this.method, sessionId: this.sessionId }).then(res => {
        const t = U.$('#typing'); if (t) t.remove();
        // 后端如果生成了新 sessionId（之前传了 'new'），更新本地引用
        if (res.sessionId && res.sessionId !== this.sessionId) {
          this.sessionId = res.sessionId;
        }
        log.insertAdjacentHTML('beforeend', this.tpl({ role: 'ai', method: res.method, content: res.content, citations: res.citations, outOfScope: res.outOfScope }));
        this.bindCites();
        this.scroll();
        this.busy = false;
        // 刷新历史会话列表（新会话可能已创建）
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
      });
    }
  };

Router.register('ai', { title: 'AI 智能答疑', mount: () => Chat.render() });
