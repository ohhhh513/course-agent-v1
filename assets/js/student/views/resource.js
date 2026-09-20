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
    // 本次真实拉取到的资源列表与「知识点 → 资源数」映射（用于准确显示章节/知识点资源数）
    _resList: [],
    _resCountByKp: {},
    _resCountTrusted: false,
    // 当前展开知识点的章节名（null 表示未展开）
    _activeChapter: null,

    render() {
      const el = U.$('#view-resource');
      // 同步取走「待定位知识点」：由待办「继续学习」或学情矩阵下钻写入，用后即清，
      // 保证重复点击同一条待办也能重新定位（不能等异步回调里再读，否则会被覆盖）。
      const pendingKp = this._pendingKp;
      this._pendingKp = '';
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

<<<<<<< Updated upstream
      API.graph.learningPath().then(list => {
        this._allPaths = list;
=======
      Promise.all([
        API.graph.learningPath(),
        API.student.resources({ size: 500 }).catch(() => ({ list: [] })),
      ]).then(([list, resPayload]) => {
        this._allPaths = list || [];
        const resList = (resPayload && resPayload.list) || [];
        // 知识点 → 已挂载资源数：与右侧资源列表同源实时统计（主 kpId + kpIds 多标签都计入）。
        // 服务端 learning_paths.res_count 只是派生缓存，可能滞后于实际上传/删除，这里以真实资源为准。
        this._resList = resList;
        this._resCountTrusted = resList.length > 0;
        this._resCountByKp = {};
        resList.forEach(r => {
          new Set([r.kpId, ...(r.kpIds || [])].filter(Boolean)).forEach(id => {
            this._resCountByKp[id] = (this._resCountByKp[id] || 0) + 1;
          });
        });
        this._mergeResourceChapters(resList);
>>>>>>> Stashed changes

        // 来自学情矩阵 / 待办「继续学习」的跳转定位
        if (pendingKp) {
          const match = list.find(p => p.name === pendingKp);
          if (match) {
            this.currentMode = 'kp';
            this.currentKpId = match.kpId;
            this.currentKpName = match.name;
          } else {
            this.keyword = pendingKp;
            const input = U.$('#resSearch');
            if (input) input.value = this.keyword;
          }
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
<<<<<<< Updated upstream
                <span>${p.hours} 学时</span><span>·</span><span>${p.resCount} 个资源</span>
                ${p.mastery ? `<span>·</span><span class="${U.level(p.mastery) === 'weak' ? 't-danger' : ''}">学习完成 ${p.mastery}%</span>` : ''}
=======
                <span>${p.hours} 学时</span><span> </span><span>${p.resCount} 个资源</span>
                  ${p.mastery ? `<span> </span><span class="${U.level(p.mastery) === 'weak' ? 't-danger' : ''}">完成率 ${p.mastery}%</span>` : ''}
>>>>>>> Stashed changes
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
          const totalRes = this.chapterResCount(g.name);
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

<<<<<<< Updated upstream
=======
    /** 把资源上的章/标签并入学习路径分组，保证教师新建章并上传资源后学生端可见 */
    _mergeResourceChapters(resList) {
      const paths = this._allPaths || [];
      const byChapter = new Map();
      paths.forEach(p => {
        const ch = p.chapter || '其他章节';
        if (!byChapter.has(ch)) byChapter.set(ch, []);
        byChapter.get(ch).push(p);
      });
      (resList || []).forEach(r => {
        const ch = r.chapter || '';
        if (!ch) return;
        if (!byChapter.has(ch)) byChapter.set(ch, []);
        const kids = r.tags || r.kps || [];
        kids.forEach(t => {
          const kpId = t.kpId || t.tagId;
          const name = t.name || kpId;
          if (!kpId) return;
          const arr = byChapter.get(ch);
          if (!arr.some(x => x.kpId === kpId)) {
            arr.push({ kpId, name, chapter: ch, step: arr.length + 1, status: 'todo', hours: 0, resCount: (this._resCountByKp || {})[kpId] || 0, mastery: 0, progress: 0 });
          }
        });
      });
      // 章顺序：按第N章编号
      const orderKey = (name) => {
        const m = String(name).match(/第\s*(\d+)\s*章/);
        return m ? parseInt(m[1], 10) : 10000;
      };
      const merged = [];
      [...byChapter.entries()]
        .sort((a, b) => orderKey(a[0]) - orderKey(b[0]) || String(a[0]).localeCompare(String(b[0])))
        .forEach(([, items]) => {
          items.forEach(it => merged.push(it));
        });
      this._allPaths = merged;
    },

    /** 某知识点已挂载的资源数：优先用本次真实拉取的资源列表，拉取失败才回落到服务端值 */
    resCountOf(p) {
      const n = p && p.kpId ? (this._resCountByKp || {})[p.kpId] : undefined;
      if (this._resCountTrusted && n !== undefined) return n;
      return (p && p.resCount) || 0;
    },

    /** 某章节的资源数：按「去重后的资源条数」统计（同一资源挂多个知识点只算一次） */
    chapterResCount(chapterName) {
      const items = (this._allPaths || []).filter(p => (p.chapter || '其他章节') === chapterName);
      if (!this._resCountTrusted) {
        return items.reduce((s, p) => s + (p.resCount || 0), 0);
      }
      const kpIds = new Set(items.map(p => p.kpId).filter(Boolean));
      return (this._resList || []).filter(r => {
        if (r.chapter && r.chapter === chapterName) return true;
        return [r.kpId, ...(r.kpIds || [])].filter(Boolean).some(id => kpIds.has(id));
      }).length;
    },

>>>>>>> Stashed changes
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
            <div class="chips-popup__hint">${U.esc(CHAPTER_NAMES[g.name] || g.name)} · ${g.items.length} 个知识点 · ${this.chapterResCount(g.name)} 个资源 <button class="chips-popup__close" type="button" title="收起">✕</button></div>
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

        // 章节过滤当前无后端参数，改在前端按资源所属章节过滤（资源 kp 形如「第2章 线性表」）
        let items = r.list;
        if (this.currentMode === 'chapter' && this.currentChapter) {
          const ch = this.currentChapter;
          items = (r.list || []).filter(x => (x.kp || '').startsWith(ch));
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

<<<<<<< Updated upstream
    /* --- 视频：恢复上次播放位置 + 实时保存进度 --- */
=======
    /* --- 视频：整体加载完成后再播放 + 进度记录点续播 ---
       1) 播放前先把整段视频缓冲完（preload=auto，等「整段缓冲」或 canplaythrough），
          避免「边下边播」时 duration / currentTime 尚未确定就把缓冲、拖动记成学习进度；
       2) 进入时读取数据库里的记录点（resource_progress.position），
          未看完的视频自动定位到记录点续播，进度条上同时标出记录点位置（可点击跳转）；
       3) 上报带 watchedDelta（本轮真实播放秒数），今日学习时长只统计真正看的时间。 */
>>>>>>> Stashed changes
    _showVideoModal(res, pr) {
      const self = this;
      const bookmark = (pr && pr.position > 0) ? Math.floor(pr.position) : 0;   // 记录点（秒）
      const wasCompleted = !!(pr && pr.progress >= 100);
      const fmt = s => self._fmt(s);

      const body = `
        <div class="rv-wrap" id="rvWrap">
          <video id="rv" class="rv-video" src="${U.esc(res.url)}" controls preload="auto" playsinline></video>
          <div class="rv-load" id="rvLoad">
            <span class="rv-load__spin" aria-hidden="true"></span>
            <b class="rv-load__title" id="rvLoadTitle">正在加载视频…</b>
            <div class="rv-load__bar"><i id="rvLoadBar" style="width:0%"></i></div>
            <p class="rv-load__hint" id="rvLoadHint">整段加载完成后再播放，确保学习进度记录准确</p>
            <button class="btn btn--sm btn--outline" id="rvForce" type="button" hidden>网络较慢，直接播放</button>
          </div>
        </div>
        <div class="rv-track" id="rvTrack" title="点击跳转">
          <i class="rv-track__buffer" id="rvBuf"></i>
          <i class="rv-track__played" id="rvPlayed"></i>
          <span class="rv-track__mark" id="rvMark" hidden title="上次观看记录点"></span>
        </div>
        <div class="rv-meta">
          <span id="rvPos" class="mono">0:00</span>
          <span class="spacer"></span>
          <span id="rvBuffered">已缓冲 0%</span>
          <span class="spacer"></span>
          <span id="rvMarkTxt">${bookmark ? '记录点 ' + fmt(bookmark) : '暂无记录点'}</span>
        </div>
        <div class="kv" style="margin-top:12px">
          <div class="kv__row"><span>资源类型</span><span>教学视频</span></div>
          <div class="kv__row"><span>时长</span><span>${U.esc(res.duration || '—')}</span></div>
          <div class="kv__row"><span>关联知识点</span><span>${U.esc(res.kp) || '—'}</span></div>
<<<<<<< Updated upstream
          <div class="kv__row"><span>续看进度</span><span id="rvProg" class="mono">${startAt ? '定位到 ' + this._fmt(startAt) : '从头播放'}</span></div>
        </div>`;
      const footer = `<a class="btn btn--primary" href="${U.esc(res.url)}" download>下载视频</a><button class="btn" data-close>关闭</button>`;

=======
          <div class="kv__row"><span>学习进度</span><span id="rvProg" class="mono">${bookmark ? '续看自 ' + fmt(bookmark) : '从头播放'}</span></div>
        </div>`;
      const footer = `<a class="btn btn--primary" href="${U.esc(res.url)}" download>下载视频</a><button class="btn" data-close>关闭</button>`;

      let ready = false;     // 是否已完成整体加载：加载期间一律不写进度
      let watched = 0;       // 本轮上报周期内真实播放的秒数
      let lastPos = null;    // 上一帧播放位置，用于累加 watched（拖动会被过滤）
      let totalSec = 0;      // 浏览器解析出的总时长（秒）
      let rvEl = null;       // 当前弹窗里的 video 元素（onMount 时按弹窗容器定位，避免多弹窗时串元素）
      let saving = false;    // 是否有上报在路上（同时只允许一个）
      let queued = false;    // 上报期间又被请求保存 → 结束后补一次

>>>>>>> Stashed changes
      const save = (force) => {
        const v = rvEl;
        if (!v || !ready) return;
        // 串行上报：并发请求会同时命中后端「先查后插」，把同一资源写成两行
        if (saving) { queued = true; return; }
        const pos = Math.floor(v.currentTime || 0);
<<<<<<< Updated upstream
        // 避免初始化/seek 时把进度回写成比上次更低的位置
        if (!force && pos <= startAt && !v.ended) return;
        const dur = v.duration ? Math.floor(v.duration) : 0;
        let progress = dur ? Math.min(100, Math.round(pos / dur * 100)) : 0;
        if (v.ended) progress = 100;
        // 已完成资源（进度已达 100%）重复观看/回拖/中途暂停时始终标记完成，不回退
        if (completed && !v.ended) progress = 100;
=======
        if (!force && pos <= bookmark && !v.ended) return;
        const dur = (v.duration && isFinite(v.duration)) ? Math.floor(v.duration) : totalSec;
        let progress = dur ? Math.min(100, Math.round(pos / dur * 100)) : 0;
        if (v.ended || wasCompleted) progress = 100;   // 已完成的视频重复观看不降级
>>>>>>> Stashed changes
        const pEl = U.$('#rvProg');
        if (pEl) pEl.textContent = (progress >= 100 ? '已完成 ✓' : '已观看 ' + progress + '%') + (pos ? ' · ' + fmt(pos) : '');
        const delta = Math.floor(watched);
        saving = true;
        API.student.saveResourceProgress(res.resId, {
          progress, position: pos, watchedDelta: delta,
        }).then(() => {
          watched -= delta; if (watched < 0) watched = 0;
        }).catch(() => {}).then(() => {
          saving = false;
          if (queued) { queued = false; save(true); }   // 期间被要求保存过 → 补一次
        });
      };

      Modal.open({
        title: res.title, body, footer,
        onMount(ov) {
          const v = ov.querySelector('#rv');
          rvEl = v;
          if (!v) return;
<<<<<<< Updated upstream
          v.addEventListener('loadedmetadata', () => {
            if (startAt && v.duration && startAt < v.duration - 0.5) {
              try { v.currentTime = startAt; } catch (e) {}
            }
            // 已看完的视频不再自动播放，避免重新从头播放
            if (!completed) {
              v.play().catch(() => {});
=======
          // 一律在弹窗容器内查询：多弹窗/残留节点下 ID 查询会串到旧元素
          const q = id => ov.querySelector('#' + id);
          const wrap = q('rvWrap'), loadBar = q('rvLoadBar'), loadTitle = q('rvLoadTitle');
          const loadHint = q('rvLoadHint'), forceBtn = q('rvForce'), durEl = q('rvDur');
          const bufEl = q('rvBuffered'), bufBar = q('rvBuf'), playedBar = q('rvPlayed');
          const markEl = q('rvMark'), posEl = q('rvPos'), track = q('rvTrack');

          const ratio = (a, b) => (b > 0 ? Math.min(100, Math.max(0, (a / b) * 100)) : 0);

          // 缓冲进度：进度条 + 文案（加载遮罩里的百分比同步）
          const paintBuffer = () => {
            const dur = (v.duration && isFinite(v.duration)) ? v.duration : 0;
            let buffered = 0;
            try {
              if (v.buffered && v.buffered.length) buffered = v.buffered.end(v.buffered.length - 1);
            } catch (e) {}
            const p = Math.round(ratio(buffered, dur));
            bufBar.style.width = p + '%';
            if (bufEl) bufEl.textContent = p >= 99 ? '已完全加载' : '已缓冲 ' + p + '%';
            if (loadBar) loadBar.style.width = p + '%';
            if (loadTitle && !ready) loadTitle.textContent = p > 0 ? `正在加载视频 ${p}%` : '正在加载视频…';
            return { dur, buffered };
          };

          const paintPosition = () => {
            const dur = (v.duration && isFinite(v.duration)) ? v.duration : 0;
            if (posEl) posEl.textContent = fmt(v.currentTime || 0);
            playedBar.style.width = ratio(v.currentTime || 0, dur) + '%';
          };

          // ---- 加载阶段：整段缓冲完成才允许播放与记录 ----
          const slowTimer = setTimeout(() => {
            if (ready) return;
            if (forceBtn) forceBtn.hidden = false;
            if (loadHint) loadHint.textContent = '网络较慢：可继续等待完整加载，或直接播放（学习记录可能不准）';
          }, 10000);

          const beginPlay = () => {
            clearTimeout(slowTimer);
            const dur = (v.duration && isFinite(v.duration)) ? v.duration : 0;
            // 未看完 → 定位到记录点续播；已看完 → 从头重新播放
            if (!wasCompleted && bookmark > 0 && (!dur || bookmark < dur - 1)) {
              try { v.currentTime = bookmark; } catch (e) {}
              Toast.info('已从记录点继续播放', `上次看到 ${fmt(bookmark)}`);
>>>>>>> Stashed changes
            } else {
              try { v.currentTime = 0; } catch (e) {}
              if (wasCompleted) Toast.info('该视频已完成', '从头重新播放');
            }
<<<<<<< Updated upstream
=======
            lastPos = v.currentTime || 0;
            paintPosition();
            save(true);
            v.play().catch(() => {});
          };

          const markReady = () => {   // 完成整体加载：收起遮罩 → 定位记录点 → 播放
            if (ready) return;
            ready = true;
            if (wrap) wrap.classList.add('is-ready');
            paintBuffer();
            beginPlay();
          };

          // 整体加载判定：不依赖某一个事件的先后顺序（不同浏览器/不同网络下
          // progress / loadeddata / canplaythrough 的到达顺序并不一致，只等 progress
          // 会漏判）。任一事件后只要「已缓冲到片尾」就直接就绪。
          const checkLoaded = () => {
            const { dur, buffered } = paintBuffer();
            if (!ready && dur && buffered >= dur - 0.5) markReady();
            return { dur, buffered };
          };

          v.addEventListener('loadedmetadata', () => {
            totalSec = (v.duration && isFinite(v.duration)) ? Math.floor(v.duration) : 0;
            if (durEl && totalSec) durEl.textContent = fmt(totalSec);
            if (markEl && totalSec && bookmark > 0 && bookmark < totalSec - 1) {
              markEl.hidden = false;
              markEl.style.left = ratio(bookmark, totalSec) + '%';
              const mt = q('rvMarkTxt');
              if (mt) mt.textContent = `记录点 ${fmt(bookmark)} / ${fmt(totalSec)}`;
            }
            paintPosition();
            checkLoaded();
          });
          v.addEventListener('progress', checkLoaded);
          v.addEventListener('loadeddata', checkLoaded);
          v.addEventListener('canplay', checkLoaded);
          v.addEventListener('canplaythrough', () => {
            // 浏览器判定「可以顺畅播完」：再给 5s 把余量补满，仍不满则直接开始
            checkLoaded();
            setTimeout(() => { if (!ready) markReady(); }, 5000);
          });
          v.addEventListener('durationchange', () => {
            totalSec = (v.duration && isFinite(v.duration)) ? Math.floor(v.duration) : 0;
            if (durEl && totalSec) durEl.textContent = fmt(totalSec);
            checkLoaded();
>>>>>>> Stashed changes
          });
          v.addEventListener('timeupdate', () => {
            const t = v.currentTime || 0;
            // 只累计「正常推进」的播放时间：暂停、拖动、跳转都不计
            if (ready && lastPos !== null && !v.paused && !v.seeking) {
              const d = t - lastPos;
              if (d > 0 && d < 5) watched += d;
            }
            lastPos = t;
            paintPosition();
            const now = Date.now();
            if (!v._lastSave || now - v._lastSave > 2000) { v._lastSave = now; save(); }
          });
          v.addEventListener('seeking', () => { lastPos = null; });
          v.addEventListener('seeked', () => { lastPos = v.currentTime || 0; paintPosition(); save(true); });
          v.addEventListener('pause', () => { setTimeout(() => save(true), 200); });
          v.addEventListener('ended', () => {
            // 播放结束停在最后一帧，不循环不自动重播
            try { v.currentTime = v.duration || 0; } catch (e) {}
            paintPosition();
            save(true);
          });
<<<<<<< Updated upstream
          v.addEventListener('pause', () => { setTimeout(() => save(true), 300); });
          // 弹窗关闭时再保存一次（捕获阶段，先于 close 执行）
=======
          v.addEventListener('error', () => {
            if (loadTitle) loadTitle.textContent = '视频加载失败';
            if (loadHint) loadHint.textContent = '文件可能已被删除或暂不可访问，请稍后重试或联系教师。';
          });

          // 「网络较慢」逃生入口：跳过完整加载
          if (forceBtn) forceBtn.addEventListener('click', () => {
            if (forceBtn) forceBtn.hidden = true;
            markReady();
          });

          // 点击进度条跳转（顺带把 watched 清零，避免跳转被算成学习时长）
          if (track) track.addEventListener('click', e => {
            const dur = v.duration;
            if (!dur || !isFinite(dur)) { Toast.warn('视频尚未加载完成', '请等加载完成后再跳转'); return; }
            const rect = track.getBoundingClientRect();
            const target = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)) * dur;
            watched = 0;
            try { v.currentTime = target; } catch (err) {}
            lastPos = target;
            paintPosition();
            if (ready) save(true);
          });

>>>>>>> Stashed changes
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

  Router.register('resource', {
    title: '学习资源中心',
    mount: () => ResourceView.render(),
    // 已 mount 过时再次进入：仅当带着「待定位知识点」才重绘（避免无谓刷新覆盖用户当前筛选）
    update: () => { if (ResourceView._pendingKp) ResourceView.render(); },
  });
