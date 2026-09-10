'use strict';

  /* ================================================================
     视图 3 · 学习资源中心
     - 左侧：推荐学习路径（点击知识点 → 右侧自动过滤绑定资源）
     - 右侧：资源聚合
        · chips 区：按章节折叠分组显示知识点标签，末尾有「其他」标签
        · 点击 chips / 左侧 path item 双向高亮 + 过滤资源
     ================================================================ */
  // 课程章节全名映射（与 resources.kp 一致）
  const CHAPTER_NAMES = {
    '第1章': '第1章 绪论',
    '第2章': '第2章 线性表',
    '第3章': '第3章 栈和队列',
    '第4章': '第4章 串',
    '第5章': '第5章 数组和广义表',
    '第6章': '第6章 树和二叉树',
    '第7章': '第7章 图',
    '第8章': '第8章 查找',
    '第9章': '第9章 排序',
  };

  const ResourceView = {
    filter: 'all', keyword: '',
    // 过滤模式: 'all' | 'chapter' | 'kp' | 'other'
    currentMode: 'all',
    currentKpId: '',
    currentKpName: '',
    // 当前按章节过滤时的章名（仅 currentMode === 'chapter' 时有效）
    currentChapter: '',
    _pendingKp: '',
    _allPaths: [],
    // 当前展开知识点的章节名（null 表示未展开）
    _activeChapter: null,

    render() {
      const el = U.$('#view-resource');
      el.innerHTML = `
      <div class="grid g-12" style="margin-bottom:16px">
        <div class="card">
          <div class="card__head">
            <h3>${icon('route')} 推荐学习路径</h3>
            <span class="spacer"></span>
            <button class="btn btn--ghost btn--sm" id="pathExpandAll" type="button">全部折叠</button>
            <span class="badge badge--brand">图谱驱动</span>
          </div>
          <div class="card__body card__body--flush"><div class="path" id="pathList">${U.skeleton(300)}</div></div>
        </div>

        <div class="card">
          <div class="card__head">
            <h3>${icon('folder')} 资源聚合</h3>
            <span class="spacer"></span>
            <div class="search" style="width:200px">
              ${icon('search2')}<input class="input" id="resSearch" placeholder="搜索资源标题 / 知识点">
            </div>
          </div>
          <div class="card__body">
            <div class="chips-grouped" id="resChips" style="margin-bottom:14px">
              <span class="t-dim fz-12">加载中…</span>
            </div>
            <div class="res-grid" id="resGrid">${U.skeleton(200)}</div>
          </div>
        </div>
      </div>`;

      API.graph.learningPath().then(list => {
        this._allPaths = list;

        // 来自学情矩阵的跳转定位
        if (this._pendingKp) {
          const match = list.find(p => p.name === this._pendingKp);
          if (match) {
            this.currentMode = 'kp';
            this.currentKpId = match.kpId;
            this.currentKpName = match.name;
          } else {
            this.keyword = this._pendingKp;
            const input = U.$('#resSearch');
            if (input) input.value = this.keyword;
          }
          this._pendingKp = '';
        }

        // --- 左侧：学习路径列表 ---
        const statusMap = { done: ['已完成', 'badge--ok', 'path__item--done'], doing: ['学习中', 'badge--brand', 'path__item--doing'], todo: ['未开始', 'badge--outline', ''], warn: ['待加强', 'badge--danger', ''] };

        const renderItem = p => {
          const [txt, bd, cls] = statusMap[p.status];
          const activeCls = (this.currentMode === 'kp' && p.kpId === this.currentKpId) ? ' is-selected' : '';
          return `<div class="path__item ${cls}${activeCls}" data-kp-id="${U.esc(p.kpId)}" data-kp-name="${U.esc(p.name)}" tabindex="0" role="button">
            <div class="path__step">${p.status === 'done' ? '✓' : p.step}</div>
            <div class="path__main">
              <div class="row"><b>${U.esc(p.name)}</b><span class="spacer"></span><span class="badge ${bd}">${txt}</span></div>
              <div class="path__meta">
                <span>${p.hours} 学时</span><span>·</span><span>${p.resCount} 个资源</span>
                  ${p.mastery ? `<span>·</span><span class="${U.level(p.mastery) === 'weak' ? 't-danger' : ''}">掌握率 ${p.mastery}%</span>` : ''}
                ${p.locked ? `<span class="badge badge--outline">🔒 未解锁</span>` : ''}
              </div>
              ${p.progress ? `<div style="margin-top:7px;max-width:260px">${U.bar(p.progress, { done: 'excellent', doing: 'fair', warn: 'weak', todo: 'none' }[p.status], 'sm')}</div>` : ''}
            </div>
          </div>`;
        };

        const groups = [];
        const order = {};
        list.forEach(p => {
          const ch = p.chapter || '其他章节';
          if (!(ch in order)) { order[ch] = groups.length; groups.push({ name: ch, items: [] }); }
          groups[order[ch]].items.push(p);
        });

        const html = groups.map(g => {
          const items = g.items;
          const done = items.filter(x => x.status === 'done').length;
          const avgM = items.length ? Math.round(items.reduce((s, x) => s + (x.mastery || 0), 0) / items.length) : 0;
          const totalHours = items.reduce((s, x) => s + (x.hours || 0), 0);
          const totalRes = items.reduce((s, x) => s + (x.resCount || 0), 0);
          const pct = items.length ? Math.round((done / items.length) * 100) : 0;
          const pctLevel = pct === 100 ? 'is-good' : pct === 0 ? 'is-low' : 'is-fair';
          const summary = `${done}/${items.length} 已完成 · 平均学习完成 ${avgM}%`;
          const itemsHtml = items.map(renderItem).join('');
          return `
            <div class="path__group" data-chapter="${U.esc(g.name)}">
              <button class="path__chapter" type="button" aria-expanded="true">
                <div class="path__ch-row1">
                  <i class="path__caret" aria-hidden="true">▾</i>
                  <span class="path__chapter-name">${U.esc(CHAPTER_NAMES[g.name] || g.name)}</span>
                  <span class="path__chapter-count">${items.length} 个知识点</span>
                  <span class="spacer"></span>
                  <span class="path__chapter-meta">${summary}</span>
                </div>
                <div class="path__ch-row2">
                  <div class="path__ch-progress" aria-hidden="true"><i class="${pctLevel}" style="width:${pct}%"></i></div>
                  <span class="path__ch-stats">共 ${totalHours} 学时 · ${totalRes} 个资源 · 章节完成 <b class="t-num">${pct}%</b></span>
                </div>
              </button>
              <div class="path__items">${itemsHtml}</div>
            </div>`;
        }).join('');

        const root = U.$('#pathList');
        root.innerHTML = html;

        // 章节折叠
        U.$$('.path__chapter', root).forEach(btn => {
          btn.addEventListener('click', () => {
            const g = btn.closest('.path__group');
            const collapsed = g.classList.toggle('is-collapsed');
            btn.setAttribute('aria-expanded', String(!collapsed));
            btn.querySelector('.path__caret').textContent = collapsed ? '▸' : '▾';
            syncExpandAll();
          });
        });

        // path item 点击 → 联动右侧
        U.$$('.path__item', root).forEach(item => {
          const handler = () => {
            const kpId = item.dataset.kpId;
            const kpName = item.dataset.kpName;
            this.selectKp(kpId, kpName);
          };
          item.addEventListener('click', handler);
          item.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); }
          });
        });

        // 全部展开/折叠
        const expBtn = U.$('#pathExpandAll');
        function syncExpandAll() {
          if (!expBtn) return;
          const groups = U.$$('.path__group', root);
          const allCollapsed = groups.length > 0 && groups.every(g => g.classList.contains('is-collapsed'));
          expBtn.textContent = allCollapsed ? '全部展开' : '全部折叠';
        }
        if (expBtn) {
          syncExpandAll();
          expBtn.onclick = () => {
            const allCollapsed = U.$$('.path__group', root).every(g => g.classList.contains('is-collapsed'));
            U.$$('.path__group', root).forEach(g => {
              g.classList.toggle('is-collapsed', !allCollapsed);
              const btn = g.querySelector('.path__chapter');
              if (btn) {
                btn.setAttribute('aria-expanded', allCollapsed ? 'true' : 'false');
                btn.querySelector('.path__caret').textContent = allCollapsed ? '▾' : '▸';
              }
            });
            syncExpandAll();
          };
        }

        // --- 右侧：章节分组 chips ---
        this.renderKpChips();

        // 初始 load
        this.load();
      });

      // 搜索框
      let tm;
      U.$('#resSearch').addEventListener('input', e => {
        clearTimeout(tm);
        tm = setTimeout(() => {
          this.keyword = e.target.value.trim();
          if (this.keyword) {
            // 搜索时清掉筛选模式
            this.currentMode = 'all';
            this.currentKpId = ''; this.currentKpName = '';
            this.currentChapter = '';
            this._activeChapter = null;
            this.renderKpChips(); this.syncPathSelection();
          }
          this.load();
        }, 260);
      });
    },

    /* --- 右侧 chips：章节标签 + 点击弹出知识点 --- */
    renderKpChips() {
      const box = U.$('#resChips');
      if (!box) return;

      // 即使路径为空，也不让“加载中…”一直挂着
      if (!this._allPaths.length) {
        box.innerHTML = `<div class="chips-row"><button class="chip ${this.currentMode === 'all' && !this.keyword ? 'is-active' : ''}" data-mode="all">全部</button><span class="fz-12 t-dim" style="margin-left:8px">暂无知识点标签</span></div>`;
        U.$$('.chip[data-mode="all"]', box).forEach(c => c.addEventListener('click', () => this.selectMode('all')));
        return;
      }

      // 按 chapter 分组
      const groups = [];
      const order = {};
      this._allPaths.forEach(p => {
        const ch = p.chapter || '其他章节';
        if (!(ch in order)) { order[ch] = groups.length; groups.push({ name: ch, items: [] }); }
        groups[order[ch]].items.push(p);
      });

      const chipIsActive = kpId => this.currentMode === 'kp' && this.currentKpId === kpId;

      // 默认行：全部 + 章节标签 + 课外教材
      const allActive = this.currentMode === 'all' && !this.keyword;
      const otherActive = this.currentMode === 'other';
      const row1 = [
        `<button class="chip ${allActive ? 'is-active' : ''}" data-mode="all">全部</button>`,
        ...groups.map(g => {
          // 章标签高亮只由「当前展开的章节」决定，避免与知识点过滤互相叠加
          const chActive = this._activeChapter === g.name;
          const chName = CHAPTER_NAMES[g.name] || g.name;
          return `<button class="chip chip--chapter ${chActive ? 'is-active' : ''}" data-mode="chapter" data-chapter="${U.esc(g.name)}" title="${g.items.length} 个知识点">
            ${U.esc(chName)}
          </button>`;
        }),
        `<button class="chip chip--other ${otherActive ? 'is-active' : ''}" data-mode="other">📚 课外教材</button>`,
      ].join('');

      // 展开行：某章节的知识点 chips
      let row2 = '';
      if (this._activeChapter) {
        const g = groups.find(x => x.name === this._activeChapter);
        if (g) {
          row2 = `<div class="chips-popup" data-chapter="${U.esc(g.name)}">
            <div class="chips-popup__hint">${U.esc(CHAPTER_NAMES[g.name] || g.name)} · ${g.items.length} 个知识点 <button class="chips-popup__close" type="button" title="收起">✕</button></div>
            <div class="chips-popup__row">${g.items.map(p =>
              `<button class="chip chip--kp ${chipIsActive(p.kpId) ? 'is-active' : ''}" data-mode="kp" data-kp-id="${U.esc(p.kpId)}">${U.esc(p.name)}</button>`
            ).join('')}</div>
          </div>`;
        }
      }

      box.innerHTML = `<div class="chips-row">${row1}</div>${row2}`;

      // 事件：章节 chip 点击 → 切换展开
      U.$$('.chip--chapter', box).forEach(c => c.addEventListener('click', () => {
        const ch = c.dataset.chapter;
        if (this._activeChapter === ch) {
          // 再次点击已选中的章节 → 收起弹层并回到「全部」
          this._activeChapter = null;
          this.selectMode('all');
        } else {
          // 选中所点击章节：作为唯一选中项，展开其知识点并仅展示该章资源
          this._activeChapter = ch;
          this.currentChapter = ch;
          this.currentMode = 'chapter';
          this.currentKpId = '';
          this.currentKpName = '';
          this.keyword = '';
          const input = U.$('#resSearch');
          if (input) input.value = '';
          this.renderKpChips();
          this.syncPathSelection();
          this.load();
        }
      }));

      // 事件：popup 关闭按钮
      const closeBtn = box.querySelector('.chips-popup__close');
      if (closeBtn) closeBtn.addEventListener('click', e => { e.stopPropagation(); this._activeChapter = null; this.renderKpChips(); });

      // 通用 chip 点击
      U.$$('.chip[data-mode]', box).forEach(c => {
        if (c.classList.contains('chip--chapter')) return;  // 上面已单独绑定
        c.addEventListener('click', () => {
          const mode = c.dataset.mode;
          if (mode === 'all') this.selectMode('all');
          else if (mode === 'other') this.selectMode('other');
          else if (mode === 'kp') {
            const kpId = c.dataset.kpId;
            const kpName = (this._allPaths.find(p => p.kpId === kpId) || {}).name || '';
            this.selectKp(kpId, kpName);
          }
        });
      });

      // 若当前选中了 kp，自动打开它所属章节的 popup
      if (this.currentMode === 'kp' && !this._activeChapter) {
        const kp = this._allPaths.find(p => p.kpId === this.currentKpId);
        if (kp) { this._activeChapter = kp.chapter; this.renderKpChips(); }
      }
    },

    /* --- 按知识点筛选 --- */
    selectKp(kpId, kpName) {
      this.currentMode = kpId ? 'kp' : 'all';
      this.currentKpId = kpId || '';
      this.currentKpName = kpName || '';
      this.currentChapter = '';
      this.keyword = '';
      const input = U.$('#resSearch');
      if (input) input.value = '';
      // 同步展开并高亮当前知识点所属章节的右侧标签
      if (this.currentMode === 'kp') {
        const kp = this._allPaths.find(p => p.kpId === kpId);
        this._activeChapter = kp ? kp.chapter : null;
      } else {
        this._activeChapter = null;
      }
      this.renderKpChips();
      this.syncPathSelection();
      this.load();
    },

    /* --- 按 category 筛选（all / other）--- */
    selectMode(mode) {
      this.currentMode = mode;
      this.currentKpId = '';
      this.currentKpName = '';
      this.currentChapter = '';
      this._activeChapter = null;
      this.keyword = '';
      const input = U.$('#resSearch');
      if (input) input.value = '';
      this.renderKpChips();
      this.syncPathSelection();
      this.load();
    },

    /* --- 同步左侧学习路径选中高亮 + chips 章节展开 --- */
    syncPathSelection() {
      const pathItems = document.querySelectorAll('.path__item');
      pathItems.forEach(item => {
        const match = this.currentMode === 'kp' && item.dataset.kpId === this.currentKpId;
        item.classList.toggle('is-selected', !!match);
        if (match) {
          const g = item.closest('.path__group');
          if (g && g.classList.contains('is-collapsed')) {
            g.classList.remove('is-collapsed');
            const btn = g.querySelector('.path__chapter');
            if (btn) { btn.setAttribute('aria-expanded', 'true'); btn.querySelector('.path__caret').textContent = '▾'; }
          }
        }
      });
    },

    load() {
      // 资源中心目前按单页大列表展示（后端默认 size=20，本地资源 30 条会截断）
      const params = { type: this.filter, page: 1, size: 200 };
      if (this.currentMode === 'kp') {
        params.kpId = this.currentKpId;
      } else if (this.currentMode === 'other') {
        params.category = 'other';
      }
      if (this.keyword) params.keyword = this.keyword;

      API.student.resources(params).then(r => {
        const box = U.$('#resGrid');
        if (!box) return;

        // 章节过滤当前无后端参数，改在前端过滤。
        // 注意章名/章号在两套数据里并不一致：学习路径按「第3章 栈与队列」分组（旧 6 章体系），
        // 资源按教材 9 章体系标注（「第3章 栈和队列」，且路径的「第4章 树与二叉树」＝资源的「第6章 树和二叉树」），
        // 单纯的章名前缀匹配会 0 结果或串章，所以以「该章知识点的 kpId」为准，
        // 再用命中资源的章名把同章未绑定 kpId 的资源一起带上，章名前缀仅作兜底。
        let items = r.list;
        if (this.currentMode === 'chapter' && this.currentChapter) {
          const list = r.list || [];
          const kpIds = new Set(
            (this._allPaths || [])
              .filter(p => (p.chapter || '其他章节') === this.currentChapter)
              .map(p => p.kpId)
          );
          const hit = list.filter(x => kpIds.has(x.kpId));
          const chapterNames = new Set(hit.map(x => x.kp).filter(Boolean));
          items = list.filter(x =>
            kpIds.has(x.kpId) ||
            chapterNames.has(x.kp) ||
            (x.kp || '').startsWith(this.currentChapter)
          );
        }

        let emptyHtml;
        if (!items.length && this.currentMode === 'kp') {
          emptyHtml = `<div style="text-align:center;padding:30px">
            <div style="font-size:36px;margin-bottom:8px">📭</div>
            <p class="fz-14 fw-6">「${U.esc(this.currentKpName)}」暂未挂载学习资源</p>
            <p class="fz-12 t-dim" style="margin-top:4px">该知识点可能暂无上传资源，尝试切换其他知识点</p>
            <button class="btn btn--sm btn--outline" id="clearKpFilter" style="margin-top:10px">查看全部资源</button>
          </div>`;
        } else if (!items.length && this.currentMode === 'chapter') {
          emptyHtml = `<div style="text-align:center;padding:30px">
            <div style="font-size:36px;margin-bottom:8px">📭</div>
            <p class="fz-14 fw-6">「${U.esc(this.currentChapter)}」暂未匹配到资源</p>
            <button class="btn btn--sm btn--outline" id="clearKpFilter" style="margin-top:10px">查看全部资源</button>
          </div>`;
        } else if (!items.length && this.currentMode === 'other') {
          emptyHtml = `<div style="text-align:center;padding:30px">
            <div style="font-size:36px;margin-bottom:8px">📚</div>
            <p class="fz-14 fw-6">暂未收集到课外教材类资源</p>
            <button class="btn btn--sm btn--outline" id="clearKpFilter" style="margin-top:10px">查看全部资源</button>
          </div>`;
        } else if (!items.length) {
          emptyHtml = R.empty('没有匹配的资源', '试试更换搜索条件', 'search2');
        }

        box.innerHTML = items.length ? items.map(R.res).join('') : emptyHtml;

        const clearBtn = U.$('#clearKpFilter');
        if (clearBtn) clearBtn.addEventListener('click', () => this.selectMode('all'));

        U.$$('.res', box).forEach(c => c.addEventListener('click', () => {
          const res = items.find(x => x.resId === c.dataset.res);
          if (!res || !res.url) {
            Modal.open({ title: '资源不可用', body: '<p class="t-dim">该资源暂无文件，请联系教师上传。</p>', footer: '<button class="btn" data-close>关闭</button>' });
            return;
          }
          API.student.resourceView({ resId: res.resId }).catch(() => {}); // 记录观看次数，失败静默
          this.openResource(res);
        }));
      });
    },

    /* --- 打开资源（带进度续看） --- */
    openResource(res) {
      if (res.type === 'video') {
        API.student.resourceProgress(res.resId)
          .then(pr => this._showVideoModal(res, pr))
          .catch(() => this._showVideoModal(res, null));
      } else if (res.type === 'doc' || res.type === 'ppt') {
        API.student.resourceProgress(res.resId)
          .then(pr => this._openDoc(res, pr))
          .catch(() => this._openDoc(res, null));
      } else {
        Modal.open({
          title: res.title,
          body: `<div class="kv"><div class="kv__row"><span>资源类型</span><span>题库</span></div></div>`,
          footer: `<button class="btn" data-close>关闭</button>`
        });
      }
    },

    /* --- 视频：恢复上次播放位置 + 实时保存进度 --- */
    _showVideoModal(res, pr) {
      const self = this;
      const startAt = (pr && pr.position && pr.position > 0) ? pr.position : 0;
      const body = `
        <video id="rv" src="${U.esc(res.url)}" controls ${startAt ? '' : 'autoplay'} style="width:100%;border-radius:var(--r-md);background:#000;max-height:60vh"></video>
        <div class="kv" style="margin-top:14px">
          <div class="kv__row"><span>资源类型</span><span>教学视频</span></div>
          <div class="kv__row"><span>时长</span><span>${U.esc(res.duration || '—')}</span></div>
          <div class="kv__row"><span>关联知识点</span><span>${U.esc(res.kp) || '—'}</span></div>
          <div class="kv__row"><span>续看进度</span><span id="rvProg" class="mono">${startAt ? '定位到 ' + this._fmt(startAt) : '从头播放'}</span></div>
        </div>`;
      const footer = `<a class="btn btn--primary" href="${U.esc(res.url)}" download>下载视频</a><button class="btn" data-close>关闭</button>`;

      const save = (force) => {
        const v = U.$('#rv');
        if (!v) return;
        const pos = Math.floor(v.currentTime || 0);
        // 避免初始化/seek 时把进度回写成比上次更低的位置
        if (!force && pos <= startAt && !v.ended) return;
        const dur = v.duration ? Math.floor(v.duration) : 0;
        let progress = dur ? Math.min(100, Math.round(pos / dur * 100)) : 0;
        if (v.ended) progress = 100;
        // 已完成资源（进度已达 100%）重复观看/回拖/中途暂停时始终标记完成，不回退
        if (completed && !v.ended) progress = 100;
        const pEl = U.$('#rvProg');
        if (pEl) pEl.textContent = (progress >= 100 ? '已完成 ✓' : '已观看 ' + progress + '%') + (pos ? ' · ' + this._fmt(pos) : '');
        API.student.saveResourceProgress(res.resId, { progress, position: pos }).catch(() => {});
      };

      const completed = pr && pr.progress >= 100;

      Modal.open({
        title: res.title, body, footer,
        onMount(ov) {
          const v = U.$('#rv');
          if (!v) return;
          v.addEventListener('loadedmetadata', () => {
            if (startAt && v.duration && startAt < v.duration - 0.5) {
              try { v.currentTime = startAt; } catch (e) {}
            }
            // 已看完的视频不再自动播放，避免重新从头播放
            if (!completed) {
              v.play().catch(() => {});
            } else {
              try { v.currentTime = v.duration || 0; } catch (e) {}
            }
          });
          v.addEventListener('timeupdate', () => {
            const now = Date.now();
            if (!v._lastSave || now - v._lastSave > 2000) { v._lastSave = now; save(); }
          });
          v.addEventListener('ended', () => {
            // 播放结束停在最后一帧，不循环不自动重播
            try { v.currentTime = v.duration || 0; } catch (e) {}
            save(true);
          });
          v.addEventListener('pause', () => { setTimeout(() => save(true), 300); });
          // 弹窗关闭时再保存一次（捕获阶段，先于 close 执行）
          ov.addEventListener('click', e => {
            if (e.target === ov || e.target.closest('[data-close]')) { save(true); self.load(); }
          }, true);
        }
      });
    },

    /* --- 文档/课件：定位上次页码 + 记录进度 --- */
    _openDoc(res, pr) {
      const self = this;
      const savedPage = (pr && pr.position) ? pr.position : 0;
      const isPdf = (res.url || '').toLowerCase().endsWith('.pdf');

      if (isPdf) {
        const url = res.url + (savedPage > 1 ? '#page=' + savedPage : '');
        const body = `
          <iframe id="rd" src="${U.esc(url)}" style="width:100%;height:62vh;border:0;border-radius:var(--r-md);background:#fff"></iframe>
          <div class="row" style="margin-top:12px;gap:8px;align-items:center">
            <span class="fz-12 t-dim">跳转页码</span>
            <input id="rdPage" class="input" type="number" min="1" max="${res.pages || 999}" value="${savedPage || 1}" style="width:90px">
            <button class="btn btn--sm btn--primary" id="rdJump">跳转</button>
            <span class="spacer"></span>
            <span class="fz-12 t-dim">共 ${res.pages || '?'} 页 · 续看已定位</span>
          </div>`;
        const footer = `<a class="btn btn--primary" href="${U.esc(res.url)}" target="_blank" rel="noopener noreferrer">在新窗口打开</a><button class="btn" data-close>关闭</button>`;
        const save = (page) => {
          page = parseInt(page, 10) || 0;
          API.student.saveResourceProgress(res.resId, {
            progress: res.pages ? Math.min(100, Math.round(page / res.pages * 100)) : 0,
            position: page
          }).catch(() => {});
        };
        Modal.open({
          title: res.title, body, footer,
          onMount(ov) {
            const jb = U.$('#rdJump');
            const inp = U.$('#rdPage');
            if (jb) jb.addEventListener('click', () => {
              const p = parseInt(inp.value, 10) || 1;
              const f = U.$('#rd');
              if (f) f.src = res.url + '#page=' + p;
              save(p);
            });
            ov.addEventListener('click', e => {
              if (e.target === ov || e.target.closest('[data-close]')) { if (inp) save(inp.value); self.load(); }
            }, true);
          }
        });
      } else {
        // ppt/doc 等非 PDF 文档：先弹窗提供「在线查看」/「下载」选项，不再自动 window.open 触发下载
        const typeLabel = res.type === 'doc' ? '教材文献' : '课堂PPT';
        const body = `
          <div class="kv">
            <div class="kv__row"><span>资源类型</span><span>${typeLabel}</span></div>
            <div class="kv__row"><span>页数</span><span>${res.pages || '—'} 页</span></div>
            <div class="kv__row"><span>关联知识点</span><span>${U.esc(res.kp) || '—'}</span></div>
          </div>
          <div class="empty empty--compact" style="margin:18px 0 10px;padding:22px 16px;background:var(--bg-2);border-radius:var(--r-md)">
            <span class="fz-28">${icon('file')}</span>
            <b>${typeLabel} 在线预览</b>
            <p class="t-dim fz-12" style="max-width:360px;text-align:center;line-height:1.8">浏览器将使用内置阅读器或 Office 打开课件。若浏览器未安装对应插件，可选择下载后查看。</p>
          </div>
          <div class="row" style="margin-top:12px;gap:8px;align-items:center;justify-content:center">
            <span class="fz-12 t-dim">已读到第</span>
            <input id="rdPage" class="input" type="number" min="0" max="${res.pages || 999}" value="${savedPage || 0}" style="width:90px">
            <span class="fz-12 t-dim">页</span>
            <button class="btn btn--sm btn--primary" id="rdSave">保存进度</button>
          </div>`;
        const footer = `
          <a class="btn btn--primary" href="${U.esc(res.url)}" target="_blank" rel="noopener noreferrer" id="rdView">在线查看</a>
          <a class="btn" href="${U.esc(res.url)}" download>下载课件</a>
          <button class="btn" data-close>关闭</button>`;
        Modal.open({
          title: res.title, body, footer,
          onMount(ov) {
            const inp = U.$('#rdPage');
            const sb = U.$('#rdSave');
            const save = () => {
              const p = parseInt(inp ? inp.value : '0', 10) || 0;
              API.student.saveResourceProgress(res.resId, {
                progress: res.pages ? Math.min(100, Math.round(p / res.pages * 100)) : 0,
                position: p
              }).catch(() => {});
              if (sb) { sb.textContent = '已保存 ✓'; setTimeout(() => { sb.textContent = '保存进度'; }, 1500); }
            };
            if (sb) sb.addEventListener('click', save);
            ov.addEventListener('click', e => {
              if (e.target === ov || e.target.closest('[data-close]')) { if (inp) save(); self.load(); }
            }, true);
          }
        });
      }
    },

    /* --- 秒 → mm:ss --- */
    _fmt(s) {
      s = Math.max(0, Math.floor(s || 0));
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
      const pad = n => String(n).padStart(2, '0');
      return h ? `${h}:${pad(m)}:${pad(ss)}` : `${m}:${pad(ss)}`;
    }
  };

  // 暴露到全局：课程图谱的「挂载资源」点击会通过 window.ResourceView.openResource 打开资源
  window.ResourceView = ResourceView;

  Router.register('resource', { title: '学习资源中心', mount: () => ResourceView.render() });
