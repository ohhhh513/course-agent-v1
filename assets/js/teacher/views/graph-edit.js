/* ==========================================================================
   教师端 · 知识图谱编排（方案 B · SVG 手绘）
   节点实时来自「课程目录与资源」的 KP；未布点的新 KP 会提醒教师更新图谱。

   交互约定（团队清单 6 项）：
   1) 拖拽/平移/缩放只做「属性增量更新」，不再整树 innerHTML 重建；
      pointermove 经 requestAnimationFrame 合并，事件用画布级委托（只绑一次）。
   2) 去掉「选择/拖拽」「连线」模式切换：默认就是选择与拖拽；
      连线改为「鼠标停在节点上 → 显示 + → 点 + 选关系 → 点目标节点」（Visio 方式）。
   3) 不同章节节点用不同颜色（左栏色点、画布节点、图例同源）。
   4) 撤回：每次结构性改动前压栈快照，按钮 + Ctrl/⌘+Z。
   5) 节点名称不可选中（user-select:none + pointer-events:none）。
   ========================================================================== */
'use strict';

const TeacherGraphEdit = {
  data: null,          // { nodes, edges, pending }
  sel: null,           // { type:'node'|'edge', id }
  linking: null,       // { src, rel } 等待点击目标节点
  hoverId: null,
  cam: { x: 40, y: 40, k: 1 },
  leftTab: 'bank',
  history: [],         // 撤回栈：保存「改动前」的快照

  _drag: null,
  _pan: null,
  _raf: 0,
  _w: 800,
  _h: 520,
  _nodeEls: null,      // Map<id, { g, core, plus, r }>
  _edgeEls: null,      // [ { g, hit, line, text, e } ]
  _keyBound: false,
  _loadToken: 0,

  COLORS: [
    '#0f766e', '#0284c7', '#7c3aed', '#db2777',
    '#d97706', '#059669', '#4f46e5', '#be185d',
    '#0e7490', '#65a30d', '#9333ea', '#ea580c',
  ],

  /** 可保存的关系（后端 _EDITABLE_EDGE_RELS = pre/advance/parallel） */
  _REL() {
    return {
      pre: { color: '#0d9488', label: '前置', dash: '' },
      advance: { color: '#a21caf', label: '进阶', dash: '' },
      parallel: { color: '#718793', label: '并列', dash: '7 5' },
    };
  },

  /* ------------------------------------------------------------------ */
  /* 渲染骨架                                                             */
  /* ------------------------------------------------------------------ */
  render() {
    const el = U.$('#view-graph-edit');
    el.innerHTML = `
      <div class="card ge-root">
        <div class="card__head ge-head">
          <h3>${icon('route')} 知识图谱编排</h3>
          <span class="badge badge--outline">节点 = 课程知识点</span>
          <span class="spacer"></span>
          <button class="btn btn--outline btn--sm" id="geRefresh" type="button">从目录刷新</button>
          <button class="btn btn--primary btn--sm" id="geSave" type="button">保存图谱</button>
        </div>
        <div id="geBanner" class="callout callout--warn" style="margin:0 12px 8px;display:none;flex-shrink:0"></div>
        <div class="ge-shell">
          <aside class="ge-panel">
            <div class="ge-tabs">
              <button class="tab on" data-tab="bank">知识点目录</button>
              <button class="tab" data-tab="pending">待更新 <span class="badge badge--warn" id="gePendingBadge">0</span></button>
            </div>
            <div class="ge-list" id="geLeft"></div>
          </aside>
          <section class="ge-canvas-wrap">
            <div class="ge-tools">
              <button class="btn btn--sm" id="geUndo" type="button" title="撤回上一步（Ctrl+Z）">${icon('undo')} 撤回</button>
              <button class="btn btn--sm btn--danger" id="geDel" type="button">删除选中</button>
              <button class="btn btn--sm btn--ghost" id="geFit" type="button">适配视图</button>
              <span class="fz-12 t-dim" id="geHint">拖拽节点调整位置；悬停节点点「+」连线</span>
            </div>
            <div class="ge-legend" id="geLegend"></div>
            <div class="ge-board-box" id="geBoardBox">
              <svg id="geBoard" class="ge-board" xmlns="http://www.w3.org/2000/svg"></svg>
              <div class="ge-relpop" id="geRelPop" style="display:none"></div>
              <aside class="ge-detail" id="geDetail">
                <div class="ge-detail__head">
                  <h4 id="geDName">知识点详情</h4>
                  <button class="ge-detail__close" id="geDClose" type="button" title="关闭">×</button>
                </div>
                <div class="ge-detail__body" id="geDBody"></div>
              </aside>
            </div>
          </section>
        </div>
      </div>
      <style>
        .view.is-active#view-graph-edit{display:block;height:calc(100vh - var(--topbar-h) - 44px);min-height:0}
        #view-graph-edit .ge-root{height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;margin:0}
        #view-graph-edit .ge-head{flex:0 0 auto;flex-shrink:0}
        #view-graph-edit .ge-shell{display:grid;grid-template-columns:240px minmax(0,1fr);flex:1 1 auto;min-height:0;height:0}
        #view-graph-edit .ge-panel{border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;overflow:hidden}
        #view-graph-edit .ge-tabs{display:flex;gap:6px;padding:8px 10px;flex-shrink:0}
        #view-graph-edit .ge-tabs .tab{flex:1;height:30px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);font-size:12px;cursor:pointer}
        #view-graph-edit .ge-tabs .tab.on{background:rgba(15,118,110,.12);border-color:#5eead4;color:var(--brand)}
        #view-graph-edit .ge-list{flex:1;overflow:auto;padding:0 10px 12px;min-height:0}
        #view-graph-edit .ge-ch{font-size:11px;color:var(--text-3);margin:10px 2px 6px;font-weight:600}
        #view-graph-edit .ge-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2);margin-bottom:6px;cursor:pointer;font-size:12.5px}
        #view-graph-edit .ge-item:hover{border-color:#5eead4}
        #view-graph-edit .ge-item .swatch{width:10px;height:10px;border-radius:50%;flex-shrink:0}
        #view-graph-edit .ge-item .id{margin-left:auto;font-size:10px;color:var(--text-3);font-family:ui-monospace,monospace}
        #view-graph-edit .ge-canvas-wrap{display:flex;flex-direction:column;min-width:0;min-height:0;position:relative;overflow:hidden}
        #view-graph-edit .ge-tools{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0;z-index:2;background:var(--surface)}
        #view-graph-edit .ge-legend{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:6px 12px;border-bottom:1px solid var(--border);font-size:11px;color:var(--text-3);flex-shrink:0;background:var(--surface)}
        #view-graph-edit .ge-legend .lg{display:inline-flex;align-items:center;gap:4px}
        #view-graph-edit .ge-legend .lg i{width:9px;height:9px;border-radius:50%;display:inline-block}
        #view-graph-edit .ge-board-box{position:relative;flex:1 1 auto;min-height:0;overflow:hidden;background:radial-gradient(circle at 30% 20%,rgba(15,118,110,.06),transparent 40%),var(--bg)}
        #view-graph-edit .ge-board{position:absolute;left:0;top:0;right:0;bottom:0;width:100%;height:100%;display:block;touch-action:none;
          user-select:none;-webkit-user-select:none}
        #view-graph-edit .ge-node circle.core{stroke:transparent;stroke-width:0;transition:stroke .15s}
        /* 仿学生端：重难点 = 琥珀色边框（与 var(--warn) 同源，随主题变化） */
        #view-graph-edit .ge-node circle.core.key{stroke:var(--warn);stroke-width:2.2}
        #view-graph-edit .ge-node.on circle.core{stroke:var(--brand);stroke-width:2.5}
        #view-graph-edit .ge-node.src circle.core{stroke:#0ea5e9;stroke-width:2.5;stroke-dasharray:4 3}
        /* 清单 6-5：节点名称不可选中、不吃鼠标事件；名称置于节点下方 */
        #view-graph-edit .ge-node text.lab{fill:var(--text);font-size:11.5px;font-weight:500;pointer-events:none;
          user-select:none;-webkit-user-select:none;dominant-baseline:central}
        /* 悬停某节点 → 虚化（dim）其他节点与无关连线，突出当前聚焦的子图（仿学生端 adjacency） */
        #view-graph-edit .ge-node, #view-graph-edit .ge-edge{transition:opacity .16s ease}
        #view-graph-edit .ge-board.ge-dim .ge-node:not(.is-active){opacity:.2}
        #view-graph-edit .ge-board.ge-dim .ge-edge:not(.is-active){opacity:.08}
        /* 连线预览（Visio 式橡皮筋线段） */
        #view-graph-edit .ge-board .link-preview{fill:none;stroke:var(--brand);stroke-width:1.5;
          stroke-dasharray:6 4;opacity:.85;pointer-events:none}
        #view-graph-edit .ge-edge path.line{fill:none;stroke-width:1.5;stroke-linejoin:round;transition:stroke-width .14s ease}
        /* 选中连线 → 线、箭头、文字三者风格统一高亮：
           - 主线 stroke-width 1.5→2.4 加粗
           - halo（白底层 path）平时透明，选中时显示为 5.5px 白色 stroke，给主线一圈白条边（与箭头白条风格一致）
           - 关系标签加粗、染品牌色、字号 10→11px
           不使用 drop-shadow 滤镜，避免箭头周围出现割裂阴影。*/
        #view-graph-edit .ge-edge.on path.line{stroke-width:2.4}
        #view-graph-edit .ge-edge path.halo{fill:none;stroke:transparent;stroke-width:5.5;stroke-linejoin:round;transition:stroke .14s ease}
        #view-graph-edit .ge-edge.on path.halo{stroke:#fff}
        #view-graph-edit .ge-edge.on text{fill:var(--brand);font-weight:700;font-size:11px}
        #view-graph-edit .ge-edge path.hit{stroke:transparent;stroke-width:14;fill:none;cursor:pointer}
        #view-graph-edit .ge-edge text{fill:var(--text-3);font-size:10px;pointer-events:none;user-select:none;-webkit-user-select:none;
          paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px;stroke-linejoin:round;transition:fill .14s ease,font-size .14s ease,font-weight .14s ease}
        #view-graph-edit .ge-plus{cursor:pointer}
        #view-graph-edit .ge-plus circle{fill:var(--brand);stroke:#fff;stroke-width:2;transition:transform .12s ease,filter .12s ease}
        #view-graph-edit .ge-plus text{fill:#fff;font-size:18px;font-weight:700;pointer-events:none;user-select:none}
        /* +号悬停反馈：放大 + 阴影 + 顶部品牌色光晕 */
        #view-graph-edit .ge-plus:hover{cursor:pointer}
        #view-graph-edit .ge-plus:hover circle{filter:drop-shadow(0 2px 6px rgba(15,118,110,.45));transform-origin:center;transform-box:fill-box}
        #view-graph-edit .ge-plus:hover text{font-size:19px}
        #view-graph-edit .ge-relpop{position:absolute;z-index:9;min-width:132px;padding:6px;border:1px solid var(--border);
          border-radius:10px;background:var(--surface);box-shadow:0 8px 24px rgba(15,23,42,.14)}
        #view-graph-edit .ge-relpop b{display:block;font-size:11px;color:var(--text-3);padding:2px 6px 4px;font-weight:600}
        #view-graph-edit .ge-relpop button{display:flex;align-items:center;gap:6px;width:100%;padding:6px 8px;border:0;border-radius:7px;
          background:transparent;font-size:12.5px;cursor:pointer;text-align:left}
        #view-graph-edit .ge-relpop button:hover{background:var(--surface-2)}
        #view-graph-edit .ge-relpop .dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
        /* 选中节点 → 侧开详情页（右抽屉，覆盖在画布右侧） */
        #view-graph-edit .ge-detail{position:absolute;top:0;right:0;bottom:0;width:320px;max-width:78%;
          background:var(--surface);border-left:1px solid var(--border);box-shadow:-12px 0 32px rgba(15,23,42,.12);
          transform:translateX(100%);transition:transform .22s ease;z-index:6;display:flex;flex-direction:column}
        #view-graph-edit .ge-detail.open{transform:translateX(0)}
        #view-graph-edit .ge-detail__head{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--border);flex:0 0 auto}
        #view-graph-edit .ge-detail__head h4{margin:0;font-size:14px;font-weight:600}
        #view-graph-edit .ge-detail__close{margin-left:auto;border:0;background:transparent;font-size:20px;line-height:1;cursor:pointer;color:var(--text-3)}
        #view-graph-edit .ge-detail__close:hover{color:var(--text)}
        #view-graph-edit .ge-detail__body{padding:14px;overflow:auto;flex:1 1 auto}
        #view-graph-edit .ge-d-stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:2px 0 4px}
        #view-graph-edit .ge-d-stat{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:8px 10px;display:flex;flex-direction:column;gap:2px}
        #view-graph-edit .ge-d-stat b{font-size:18px;font-weight:700;line-height:1.1}
        #view-graph-edit .ge-d-stat span{font-size:11px;color:var(--text-3)}
        #view-graph-edit .ge-d-rel{display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}
      </style>`;

    this.leftTab = 'bank';
    this.sel = null;
    this.linking = null;
    this.hoverId = null;
    this.history = [];
    this.cam = { x: 40, y: 40, k: 1 };
    this._bindShell();
    this._bindKeys();
    this.load();
  },

  _bindShell() {
    U.$('#geRefresh').addEventListener('click', () => this.load());
    U.$('#geSave').addEventListener('click', () => this.save());
    U.$('#geUndo').addEventListener('click', () => this.undo());
    U.$('#geDel').addEventListener('click', () => this.delSel());
    U.$('#geFit').addEventListener('click', () => this.fitView());
    U.$('#geDClose').addEventListener('click', () => this._closeDetail());
    this._syncUndoBtn();

    if (this._ro) this._ro.disconnect();
    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(() => { if (this.data) this.draw(); });
      const box = U.$('#geBoardBox', U.$('#view-graph-edit'));
      if (box) this._ro.observe(box);
    }
    U.$$('.ge-tabs .tab', U.$('#view-graph-edit')).forEach(t => {
      t.addEventListener('click', () => {
        this.leftTab = t.dataset.tab;
        U.$$('.ge-tabs .tab', U.$('#view-graph-edit')).forEach(x => x.classList.toggle('on', x === t));
        this.paintLeft();
      });
    });
  },

  _bindKeys() {
    if (this._keyBound) return;
    this._keyBound = true;
    document.addEventListener('keydown', ev => {
      if (Router.current !== 'graph-edit') return;
      const tag = (ev.target && ev.target.tagName) || '';
      if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
        ev.preventDefault();
        this.undo();
      }
      if (ev.key === 'Escape') this._cancelLinking();
    });
  },

  /* ------------------------------------------------------------------ */
  /* 数据                                                                 */
  /* ------------------------------------------------------------------ */
  load() {
    const loadToken = ++this._loadToken;
    const courseId = API.config.activeCourseId;
    API.teacher.kpTopology().then(d => {
      // 切换课程或重新加载后，旧课程的请求不能覆盖当前图谱。
      if (loadToken !== this._loadToken || courseId !== API.config.activeCourseId) return;
      this.data = d;
      this.sel = null;
      this.linking = null;
      this.history = [];
      this.paintLeft();
      this.paintBanner();
      this.paintLegend();
      this.autoPlacePending();
      // 立即适配一次（fitView 内部对「尺寸未就绪」有 setTimeout 重试），
      // 再补一帧兜底：避免依赖 rAF 在后台标签页/无头环境被节流导致首屏空白。
      this.fitView();
      requestAnimationFrame(() => this.fitView());
    }).catch(err => {
      if (loadToken !== this._loadToken || courseId !== API.config.activeCourseId) return;
      Toast.error('加载图谱失败', (err && err.message) || '');
    });
  },

  autoPlacePending() {
    if (!this.data) return;
    const nodes = this.data.nodes || [];
    const placed = nodes.filter(n => n.x != null && n.y != null);
    const pending = nodes.filter(n => n.x == null || n.y == null || !n.placed);
    let baseY = 80;
    if (placed.length) baseY = Math.max(...placed.map(n => n.y)) + 90;
    const baseX = 80;
    pending.forEach((n, i) => {
      n.x = baseX + (i % 8) * 72;
      n.y = baseY + Math.floor(i / 8) * 72;
      n.placed = false;
      n._auto = true;
    });
  },

  /** 章节 → 颜色（左栏色点 / 画布节点 / 图例 同源） */
  chapterColor(chapter) {
    const chapters = [...new Set((this.data && this.data.nodes ? this.data.nodes : []).map(n => n.chapter || '未分类'))];
    const idx = Math.max(0, chapters.indexOf(chapter || '未分类'));
    return this.COLORS[idx % this.COLORS.length];
  },

  paintLegend() {
    const box = U.$('#geLegend');
    if (!box || !this.data) return;
    const REL = this._REL();
    const chapters = [...new Set((this.data.nodes || []).map(n => n.chapter || '未分类'))];
    const relLegend = Object.keys(REL).map(k =>
      `<span class="lg"><i style="background:${REL[k].color}"></i>${REL[k].label}</span>`).join('');
    const chLegend = chapters.length
      ? '<span class="fz-11 t-dim" style="margin-left:6px">章节配色：</span>' + chapters.map(c =>
        `<span class="lg"><i style="background:${this.chapterColor(c)}"></i>${U.esc(c)}</span>`).join('')
      : '';
    // 仿学生端：关系配色 + ◆ 重难点（琥珀色边框）= 与知识图谱一致的图例语义
    box.innerHTML = relLegend
      + `<span class="lg" style="margin-left:6px"><i style="border:2px solid var(--warn);background:transparent"></i>◆ 重难点</span>`
      + chLegend;
  },

  paintBanner() {
    const n = (this.data && this.data.pendingCount) || (this.data.nodes || []).filter(x => !x.placed).length;
    const box = U.$('#geBanner');
    const badge = U.$('#gePendingBadge');
    if (badge) badge.textContent = String(n);
    if (!box) return;
    if (n > 0) {
      box.style.display = '';
      box.innerHTML = `<b>请更新图谱</b>：课程目录中有 <b>${n}</b> 个知识点尚未纳入图谱布点。` +
        `可在左侧「待更新」加入画布并连线，保存后同步学生端知识图谱。` +
        `若刚在「课程目录与资源」新增了 KP，请点「从目录刷新」。`;
    } else {
      box.style.display = 'none';
    }
  },

  paintLeft() {
    const box = U.$('#geLeft');
    if (!box || !this.data) return;
    const nodes = this.data.nodes || [];
    if (this.leftTab === 'pending') {
      const pending = nodes.filter(n => !n.placed);
      box.innerHTML = pending.length
        ? `<div class="ge-ch">尚未布点（${pending.length}）</div>` + pending.map(n => `
            <div class="ge-item" data-id="${n.id}">
              <span class="swatch" style="background:${this.chapterColor(n.chapter)}"></span>
              <span>${U.esc(n.name)}</span><span class="id">${n.id}</span>
            </div>`).join('')
        : `<p class="fz-12 t-dim" style="padding:12px">全部知识点已布点，图谱已是最新。</p>`;
    } else {
      const byCh = {};
      nodes.forEach(n => {
        const ch = n.chapter || '未分类';
        (byCh[ch] = byCh[ch] || []).push(n);
      });
      box.innerHTML = Object.keys(byCh).map(ch => `
        <div class="ge-ch">${U.esc(ch)}</div>
        ${byCh[ch].map(n => `
          <div class="ge-item" data-id="${n.id}" title="${!n.placed ? '待加入图谱' : '已在画布'}">
            <span class="swatch" style="background:${this.chapterColor(n.chapter)}"></span>
            <span>${U.esc(n.name)}</span>
            ${!n.placed ? '<span class="badge badge--warn" style="margin-left:auto">新</span>' : ''}
            <span class="id">${n.id}</span>
          </div>`).join('')}
      `).join('') || `<p class="fz-12 t-dim" style="padding:12px">当前课程暂无知识点，请先在「课程目录与资源」创建。</p>`;
    }
    U.$$('.ge-item', box).forEach(el => {
      el.addEventListener('click', () => this.focusOrAdd(el.dataset.id));
    });
  },

  focusOrAdd(id) {
    const n = (this.data.nodes || []).find(x => x.id === id);
    if (!n) return;
    if (n.x == null || n.y == null) {
      this._pushHistory();
      n.x = 160 + Math.random() * 200;
      n.y = 160 + Math.random() * 160;
      n._auto = true;
      this.paintBanner();
      this.paintLeft();
      this.draw();
      Toast.ok('已加入画布', '调整位置后保存');
      return;
    }
    this.sel = { type: 'node', id };
    this.draw();
    const svg = U.$('#geBoard');
    if (svg) {
      const w = this._w, h = this._h;
      this.cam.x = w / 2 - n.x * this.cam.k;
      this.cam.y = h / 2 - n.y * this.cam.k;
      this.paintGeom();
    }
  },

  /* ------------------------------------------------------------------ */
  /* 绘制：draw() 建树（结构变化） / paintGeom() 只改属性（拖拽·平移·缩放）  */
  /* ------------------------------------------------------------------ */
  draw() {
    const board = U.$('#geBoard');
    if (!board || !this.data) return;
    this._bindBoardOnce();

    const rect = board.getBoundingClientRect();
    this._w = Math.max(200, Math.floor(rect.width || board.clientWidth || 800));
    this._h = Math.max(200, Math.floor(rect.height || board.clientHeight || 520));
    board.setAttribute('viewBox', `0 0 ${this._w} ${this._h}`);

    const nodes = (this.data.nodes || []).filter(n => n.x != null && n.y != null);
    const edges = (this.data.edges || []).filter(e =>
      nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target));
    const REL = this._REL();

    const markers = Object.keys(REL).map(k => `
      <marker id="ge-ar-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10z" fill="${REL[k].color}"/>
      </marker>
      <marker id="ge-ar-${k}-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10z" fill="${REL[k].color}" stroke="#fff" stroke-width="2.2" stroke-linejoin="round" paint-order="stroke fill"/>
      </marker>`).join('');

    board.innerHTML = `<defs>${markers}</defs>
      <path id="geGrid" fill="none" stroke="rgba(100,116,139,.12)" stroke-width="1"/>
      <g id="geCam">
        <g id="geEdges"></g>
        <g id="geNodes"></g>
        <path id="geLinkPreview" class="link-preview" d="" style="display:none"/>
      </g>`;

    const gE = board.querySelector('#geEdges');
    const gN = board.querySelector('#geNodes');
    this._edgeEls = [];
    this._nodeEls = new Map();

    gE.innerHTML = edges.map((e, i) => {
      const r = REL[e.relation] || REL.pre;
      return `<g class="ge-edge" data-edge="${i}">
        <path class="hit" d=""/>
        <path class="halo" d=""/>
        <path class="line" d="" stroke="${r.color}" stroke-dasharray="${r.dash}" marker-end="url(#ge-ar-${e.relation || 'pre'})" ${e.relation === 'parallel' ? 'marker-start="url(#ge-ar-parallel)"' : ''}/>
        <text text-anchor="middle"></text>
      </g>`;
    }).join('');
    [...gE.children].forEach((g, i) => {
      this._edgeEls.push({
        g, hit: g.querySelector('.hit'), halo: g.querySelector('.halo'),
        line: g.querySelector('.line'),
        text: g.querySelector('text'), e: edges[i], key: this._edgeKey(edges[i]),
      });
    });

    gN.innerHTML = nodes.map(n => {
      const color = this.chapterColor(n.chapter);          // 清单 6-3：按章着色
      const r = n.isKey ? 17 : 13;
      const label = (n.name || '').length > 10 ? (n.name || '').slice(0, 10) + '…' : (n.name || '');
      return `<g class="ge-node" data-node="${n.id}">
        <circle class="core ${n.isKey ? 'key' : ''}" r="${r}" fill="${color}"/>
        <circle class="hit" r="${r + 8}" fill="transparent"/>
        <text class="lab" x="0" y="${r + 13}" text-anchor="middle">${U.esc(label)}</text>
        <g class="ge-plus" data-plus="${n.id}" style="display:none">
          <circle r="13"/>
          <text y="0" text-anchor="middle" dominant-baseline="central">+</text>
        </g>
      </g>`;
    }).join('');
    [...gN.children].forEach((g, i) => {
      const n = nodes[i];
      this._nodeEls.set(n.id, { g, plus: g.querySelector('.ge-plus'), r: n.isKey ? 17 : 13 });
    });

    this.paintGeom();
    this._syncSel();
    this._linkPreview = board.querySelector('#geLinkPreview');
    this._applyDim();
  },

  /** 只更新几何属性，不重建 DOM —— 拖拽/平移/缩放走这里 */
  paintGeom() {
    const board = U.$('#geBoard');
    if (!board || !this.data) return;
    const camG = board.querySelector('#geCam');
    if (!camG) return;
    camG.setAttribute('transform', `translate(${this.cam.x},${this.cam.y}) scale(${this.cam.k})`);

    const grid = board.querySelector('#geGrid');
    if (grid) grid.setAttribute('d', this._gridPath());

    const byId = Object.fromEntries((this.data.nodes || []).map(n => [n.id, n]));
    const inv = 1 / this.cam.k;
    this._nodeEls.forEach((el, id) => {
      const n = byId[id];
      if (!n) return;
      el.g.setAttribute('transform', `translate(${n.x},${n.y})`);
      if (el.plus) {
        // 「+」放在节点正上方（不遮节点本体、不偏离视觉重心）：
        // 偏移 = -(r + plusR + gap)，使加号圆(plusR=13)最近点距圆心 r+gap+2，
        // 完全在节点圆面之上、并保持约 3px 视觉间隙。
        const plusR = 13, gap = 3;
        const offY = -(el.r + plusR + gap);
        el.plus.setAttribute('transform', `translate(0,${offY}) scale(${inv})`);
      }
    });
    this._edgeEls.forEach(o => {
      const a = byId[o.e.source], b = byId[o.e.target];
      if (!a || !b) return;
      const g = this._edgeGeom(a, b);
      o.hit.setAttribute('d', g.d);
      o.halo.setAttribute('d', g.d);
      o.line.setAttribute('d', g.d);
      o.text.setAttribute('x', g.lx);
      o.text.setAttribute('y', g.ly);
      o.text.textContent = (this._REL()[o.e.relation] || this._REL().pre).label;
    });
  },

  _rafGeom() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = 0;
      this.paintGeom();
    });
  },

  _gridPath() {
    const step = 28 * this.cam.k;
    let d = '';
    if (step > 8) {
      for (let x = this.cam.x % step; x < this._w; x += step) d += `M${x} 0 V${this._h}`;
      for (let y = this.cam.y % step; y < this._h; y += step) d += `M0 ${y} H${this._w}`;
    }
    return d;
  },

  _syncSel() {
    if (!this._nodeEls) return;
    this._nodeEls.forEach((el, id) => {
      const on = this.sel && this.sel.type === 'node' && this.sel.id === id;
      const src = this.linking && this.linking.src === id;
      el.g.classList.toggle('on', !!on);
      el.g.classList.toggle('src', !!src);
    });
    this._edgeEls.forEach(o => {
      const on = this.sel && this.sel.type === 'edge' && this.sel.id === o.key;
      o.g.classList.toggle('on', !!on);
      // 选中态箭头换为放大并带白边的版本（marker-end / marker-start），与文字加粗、染品牌色形成统一高亮。
      // 线宽、命中区颜色等其它视觉态均由 CSS（.ge-edge.on）控制；箭头粗细通过 marker 切换实现，
      // 不使用 drop-shadow 滤镜，避免箭头周围出现割裂阴影。
      const rel = o.e.relation || 'pre';
      const mk = on ? `url(#ge-ar-${rel}-on)` : `url(#ge-ar-${rel})`;
      o.line.setAttribute('marker-end', mk);
      if (o.e.relation === 'parallel') o.line.setAttribute('marker-start', mk);
    });
  },

  _edgeKey(e) { return `${e.source}|${e.target}|${e.relation}`; },

  // 关系唯一性按两个知识点的无向组合判断，与发起连线的方向无关。
  _pairKey(source, target) {
    return source < target ? `${source}|${target}` : `${target}|${source}`;
  },

  _edgeGeom(a, b) {
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const clip = (x, y, sx, sy) => {
      const tx = sx ? 16 / Math.abs(sx) : 1e9;
      const ty = sy ? 16 / Math.abs(sy) : 1e9;
      const t = Math.min(tx, ty) + 3;
      return { x: x + sx * t, y: y + sy * t };
    };
    const p1 = clip(a.x, a.y, ux, uy);
    const p2 = clip(b.x, b.y, -ux, -uy);
    const cy = (p1.y + p2.y) / 2;
    const off = Math.min(36, len * 0.15);
    const mx = (p1.x + p2.x) / 2, my = cy - off;
    // 标签贴线：Q 曲线 t=0.5 的实际顶点在「弦中点与控制点的中点」处，
    // 基线再上抬 6px，让文字紧贴线段而不是浮在控制点（离线 ~18px）
    return { d: `M${p1.x} ${p1.y} Q${mx} ${my} ${p2.x} ${p2.y}`, lx: mx, ly: (cy + my) / 2 - 6 };
  },

  _toWorld(e) {
    const r = U.$('#geBoard').getBoundingClientRect();
    return {
      x: (e.clientX - r.left - this.cam.x) / this.cam.k,
      y: (e.clientY - r.top - this.cam.y) / this.cam.k,
    };
  },

  /* ------------------------------------------------------------------ */
  /* 事件：画布级委托，只绑一次                                            */
  /* ------------------------------------------------------------------ */
  _bindBoardOnce() {
    const board = U.$('#geBoard');
    if (!board || board._geBound) return;
    board._geBound = true;

    board.addEventListener('pointerdown', ev => {
      const plus = this._closest(ev.target, '[data-plus]');
      if (plus) { ev.stopPropagation(); this._openRelPop(plus.dataset.plus); return; }
      const nodeEl = this._closest(ev.target, '[data-node]');
      if (nodeEl) { ev.stopPropagation(); this._nodeDown(ev, nodeEl.dataset.node); return; }
      const edgeEl = this._closest(ev.target, '[data-edge]');
      if (edgeEl) { ev.stopPropagation(); this._edgeDown(edgeEl); return; }
      // 空白处：平移 + 取消选中/连线
      this._pan = { x: ev.clientX - this.cam.x, y: ev.clientY - this.cam.y };
      this.sel = null;
      this._cancelLinking(true);
      this._syncSel();
      this._closeDetail();
      try { board.setPointerCapture(ev.pointerId); } catch (e) {}
    });

    board.addEventListener('pointermove', ev => {
      // 连线进行中：橡皮筋线段跟随鼠标
      if (this.linking) { this._updateLinkPreview(ev); return; }
      if (this._drag) {
        const n = (this.data.nodes || []).find(x => x.id === this._drag.id);
        if (!n) return;
        const w = this._toWorld(ev);
        n.x = w.x - this._drag.ox;
        n.y = w.y - this._drag.oy;
        n._auto = false;
        this._drag.moved = true;
        this._rafGeom();
        return;
      }
      if (this._pan) {
        this.cam.x = ev.clientX - this._pan.x;
        this.cam.y = ev.clientY - this._pan.y;
        this._rafGeom();
      }
    });

    const endPointer = () => {
      if (this._drag) {
        if (this._drag.moved) {
          this.history.push(this._drag.before);
          if (this.history.length > 60) this.history.shift();
          this._syncUndoBtn();
        } else {
          // 单击节点（未拖动）→ 侧开详情页
          this._openDetail(this._drag.id);
        }
        this._drag = null;
      }
      this._pan = null;
    };
    board.addEventListener('pointerup', endPointer);
    board.addEventListener('pointercancel', endPointer);

    // 悬停显示「+」
    board.addEventListener('pointerover', ev => {
      const nodeEl = this._closest(ev.target, '[data-node]');
      const id = nodeEl ? nodeEl.dataset.node : null;
      if (id === this.hoverId) return;
      this.hoverId = id;
      this._paintPlus();
      this._applyDim();
    });
    board.addEventListener('pointerleave', () => {
      this.hoverId = null;
      this._paintPlus();
      this._applyDim();
    });

    board.addEventListener('wheel', ev => {
      ev.preventDefault();
      const r = board.getBoundingClientRect();
      const mx = ev.clientX - r.left, my = ev.clientY - r.top;
      const wx = (mx - this.cam.x) / this.cam.k, wy = (my - this.cam.y) / this.cam.k;
      const f = ev.deltaY > 0 ? 0.93 : 1.08;
      this.cam.k = Math.min(2.2, Math.max(0.5, this.cam.k * f));
      this.cam.x = mx - wx * this.cam.k;
      this.cam.y = my - wy * this.cam.k;
      this._rafGeom();
    }, { passive: false });
  },

  _closest(el, sel) {
    if (!el || !el.closest) return null;
    try { return el.closest(sel); } catch (e) { return null; }
  },

  _paintPlus() {
    if (!this._nodeEls) return;
    this._nodeEls.forEach((el, id) => {
      const show = this.hoverId === id && !this.linking;
      if (el.plus) el.plus.style.display = show ? '' : 'none';
    });
  },

  /** 悬停某节点 → 虚化其他节点与无关连线（仿学生端 emphasis.focus:'adjacency'） */
  _applyDim() {
    const board = U.$('#geBoard');
    if (!board) return;
    const active = this.hoverId && !this.linking ? this.hoverId : null;
    if (!active || !this._nodeEls || !this._edgeEls) {
      board.classList.remove('ge-dim');
      this._nodeEls && this._nodeEls.forEach(el => el.g.classList.remove('is-active'));
      this._edgeEls && this._edgeEls.forEach(o => o.g.classList.remove('is-active'));
      return;
    }
    board.classList.add('ge-dim');
    const nb = new Set([active]);
    this._edgeEls.forEach(o => {
      if (o.e.source === active || o.e.target === active) {
        nb.add(o.e.source); nb.add(o.e.target);
        o.g.classList.add('is-active');
      } else {
        o.g.classList.remove('is-active');
      }
    });
    this._nodeEls.forEach((el, id) => el.g.classList.toggle('is-active', nb.has(id)));
  },

  /** 连线预览：从源节点中心到当前鼠标位置的橡皮筋线段 */
  _updateLinkPreview(ev) {
    if (!this.linking || !this.data || !this._linkPreview) return;
    const src = (this.data.nodes || []).find(n => n.id === this.linking.src);
    if (!src) return;
    const w = this._toWorld(ev);
    this._linkPreview.setAttribute('d', `M${src.x} ${src.y} L${w.x} ${w.y}`);
  },

  _showLinkPreview(show) {
    if (!this._linkPreview) return;
    this._linkPreview.style.display = show ? '' : 'none';
    if (!show) {
      this._linkPreview.setAttribute('d', '');
      this._linkPreview.style.stroke = '';
      this._linkPreview.style.strokeDasharray = '';
    }
  },

  _nodeDown(ev, id) {
    const board = U.$('#geBoard');
    const n = (this.data.nodes || []).find(x => x.id === id);
    if (!n) return;

    // 连线进行中：本次点击 = 目标节点
    if (this.linking) {
      if (this.linking.src === id) { this._cancelLinking(); return; }
      this._finishLink(id);
      return;
    }

    this.sel = { type: 'node', id };
    const w = this._toWorld(ev);
    this._drag = { id, ox: w.x - n.x, oy: w.y - n.y, before: this._snapshot(), moved: false };
    this._syncSel();
    try { board.setPointerCapture(ev.pointerId); } catch (e) {}
  },

  _edgeDown(el) {
    const idx = Number(el.dataset.edge);
    const o = this._edgeEls[idx];
    if (!o) return;
    this.sel = { type: 'edge', id: o.key, idx };
    this._syncSel();
  },

  /* ------------------------------------------------------------------ */
  /* 连线：悬停节点 → + → 选关系 → 点目标（Visio 方式）                     */
  /* ------------------------------------------------------------------ */
  _openRelPop(id) {
    const n = (this.data.nodes || []).find(x => x.id === id);
    if (!n) return;
    const pop = U.$('#geRelPop');
    const box = U.$('#geBoardBox');
    if (!pop || !box) return;
    const REL = this._REL();
    pop.innerHTML = '<b>选择连线关系</b>' + Object.keys(REL).map(k =>
      `<button type="button" data-rel="${k}"><span class="dot" style="background:${REL[k].color}"></span>${REL[k].label}</button>`
    ).join('') + `<button type="button" data-rel=""><span class="dot" style="background:transparent;border:1px solid var(--border)"></span>取消</button>`;

    // 定位到节点的屏幕坐标（画布盒内）
    const sx = this.cam.x + n.x * this.cam.k;
    const sy = this.cam.y + n.y * this.cam.k;
    const bw = box.clientWidth || this._w, bh = box.clientHeight || this._h;
    pop.style.display = 'block';
    const pw = pop.offsetWidth || 140, ph = pop.offsetHeight || 130;
    pop.style.left = Math.max(4, Math.min(bw - pw - 4, sx - pw / 2)) + 'px';
    pop.style.top = Math.max(4, Math.min(bh - ph - 4, sy - ph - 12)) + 'px';

    const close = () => { pop.style.display = 'none'; pop.onclick = null; };
    pop.onclick = ev => {
      const b = ev.target.closest('[data-rel]');
      if (!b) return;
      const rel = b.dataset.rel;
      close();
      if (!rel) return;
      this.linking = { src: id, rel };
      this.hoverId = null;
      this._paintPlus();
      this._syncSel();
      this._showLinkPreview(true);
      // 连线态线段颜色 = 选中关系颜色（与画出的边保持一致）
      if (this._linkPreview) {
        this._linkPreview.style.stroke = REL[rel].color;
        this._linkPreview.style.strokeDasharray = REL[rel].dash || '6 4';
      }
      this._applyDim();
      U.$('#geHint').textContent = `连线中：关系「${REL[rel].label}」，请点击目标节点（Esc 取消）`;
      Toast.info('请选择目标节点', `关系：${REL[rel].label}`);
    };
    this._relPopClose = close;
  },

  _closeRelPop() {
    const pop = U.$('#geRelPop');
    if (pop) { pop.style.display = 'none'; pop.onclick = null; }
  },

  _cancelLinking(silent) {
    if (!this.linking && !silent) return;
    this.linking = null;
    this._closeRelPop();
    const hint = U.$('#geHint');
    if (hint) hint.textContent = '拖拽节点调整位置；悬停节点点「+」连线';
    this._syncSel();
    this._paintPlus();
    this._showLinkPreview(false);
    this._applyDim();
  },

  _finishLink(targetId) {
    const { src, rel } = this.linking;
    const pairKey = this._pairKey(src, targetId);
    const exists = (this.data.edges || []).some(e =>
      this._pairKey(e.source, e.target) === pairKey);
    if (exists) {
      Toast.warn('两个知识点之间只允许一种关系');
      this._cancelLinking();
      return;
    }
    this._pushHistory();
    this.data.edges = (this.data.edges || []).concat([{ source: src, target: targetId, relation: rel }]);
    const label = this._REL()[rel].label;
    this._cancelLinking();
    this.draw();
    Toast.ok('已连线', label);
  },

  /* ------------------------------------------------------------------ */
  /* 选中节点 → 侧开详情页                                                 */
  /* ------------------------------------------------------------------ */
  _openDetail(id) {
    const n = (this.data.nodes || []).find(x => x.id === id);
    if (!n) return;
    const panel = U.$('#geDetail');
    const body = U.$('#geDBody');
    if (!panel || !body) return;
    panel.classList.add('open');
    if (U.$('#geDName', panel)) U.$('#geDName', panel).textContent = n.name || '知识点详情';
    body.innerHTML = '<p class="fz-12 t-dim" style="padding:8px 0">加载中…</p>';
    API.teacher.kpDetail({ kpId: id }).then(d => this._renderDetail(d)).catch(() => {
      // 兜底：至少展示拓扑节点已有的基础信息
      this._renderDetail({ kpId: id, name: n.name, chapter: n.chapter, isKey: n.isKey, hours: n.hours });
      Toast.warn('详情加载不完整', '仅显示基础信息');
    });
  },

  _renderDetail(d) {
    const panel = U.$('#geDetail');
    const body = U.$('#geDBody');
    if (!panel || !body) return;
    const id = d.kpId || d.id;
    const relTags = (arr) => (arr || []).length
      ? (arr || []).map(r => `<span class="badge badge--outline">${U.esc(r.name || r.id || '')}</span>`).join('')
      : '<span class="fz-12 t-dim">无</span>';
    const stat = (v) => (v == null ? '—' : v);
    body.innerHTML = `
      <div class="stack" style="gap:12px">
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点名称</span>
          <input class="input" id="geDName_i" value="${U.esc(d.name || '')}"></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">所属章节</span>
          <input class="input" id="geDChap_i" value="${U.esc(d.chapter || '')}" disabled></label>
        <div class="row" style="gap:12px;align-items:flex-end">
          <label class="stack" style="gap:4px;flex:1"><span class="fz-12 t-dim">学时</span>
            <input class="input" id="geDHours_i" type="number" min="0" value="${d.hours || 0}"></label>
          <label class="row" style="gap:6px;padding-bottom:8px">
            <input type="checkbox" id="geDKey_i" ${d.isKey ? 'checked' : ''}> <span>重点</span></label>
        </div>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点介绍</span>
          <textarea class="input" id="geDSum_i" rows="4" placeholder="一句话讲清这个知识点">${U.esc(d.summary || '')}</textarea></label>

        <div class="ge-d-stats">
          <div class="ge-d-stat"><b>${d.resourceCount || 0}</b><span>关联资源</span></div>
          <div class="ge-d-stat"><b>${d.questionCount || 0}</b><span>关联题目</span></div>
          <div class="ge-d-stat"><b>${stat(d.courseAvgMastery)}</b><span>平均掌握度</span></div>
          <div class="ge-d-stat"><b>${stat(d.courseAvgCompletion)}</b><span>平均完成度</span></div>
        </div>

        <div class="stack" style="gap:8px">
          <div class="ge-d-rel"><span class="fz-12 t-dim" style="align-self:center">前置：</span>${relTags(d.pre)}</div>
          <div class="ge-d-rel"><span class="fz-12 t-dim" style="align-self:center">后继：</span>${relTags(d.post)}</div>
          <div class="ge-d-rel"><span class="fz-12 t-dim" style="align-self:center">并列：</span>${relTags(d.parallel)}</div>
          <div class="ge-d-rel"><span class="fz-12 t-dim" style="align-self:center">进阶：</span>${relTags(d.advance)}</div>
        </div>

        <div class="row" style="gap:8px;flex-wrap:wrap;margin-top:4px">
          <button class="btn btn--primary" id="geDSave" type="button">保存修改</button>
          <button class="btn btn--danger" id="geDDel" type="button">删除知识点</button>
        </div>
      </div>`;
    if (U.$('#geDName', panel)) U.$('#geDName', panel).textContent = d.name || '知识点详情';

    U.$('#geDSave', body).addEventListener('click', () => {
      const name = U.$('#geDName_i', body).value.trim();
      if (!name) { Toast.warn('请输入知识点名称'); return; }
      const payload = {
        name,
        hours: parseInt(U.$('#geDHours_i', body).value, 10) || 0,
        isKey: U.$('#geDKey_i', body).checked,
        summary: (U.$('#geDSum_i', body).value || '').trim(),
      };
      API.teacher.updateKp(id, payload).then(() => {
        Toast.ok('知识点已更新', name);
        // 同步本地节点（名称/重点）→ 图谱标签与边框即时刷新
        const n = (this.data.nodes || []).find(x => x.id === id);
        if (n) { n.name = name; n.isKey = payload.isKey; n.hours = payload.hours; }
        this.draw();
        this.paintLeft();
        if (U.$('#geDName', panel)) U.$('#geDName', panel).textContent = name;
      }).catch(err => Toast.error('保存失败', (err && err.message) || ''));
    });

    U.$('#geDDel', body).addEventListener('click', () => {
      if (!confirm(`确定删除知识点「${d.name || id}」？\n若仍挂有资源或题目，将无法删除。`)) return;
      API.teacher.deleteKp(id).then(() => {
        Toast.ok('已删除知识点', d.name);
        this._closeDetail();
        this.load();
      }).catch(err => Toast.error('删除失败', (err && err.message) || ''));
    });
  },

  _closeDetail() {
    const panel = U.$('#geDetail');
    if (panel) panel.classList.remove('open');
  },

  /* ------------------------------------------------------------------ */
  /* 撤回                                                                 */
  /* ------------------------------------------------------------------ */
  _snapshot() {
    return {
      nodes: (this.data.nodes || []).map(n => ({ id: n.id, x: n.x, y: n.y, placed: n.placed })),
      edges: (this.data.edges || []).map(e => ({ source: e.source, target: e.target, relation: e.relation })),
    };
  },

  _pushHistory() {
    if (!this.data) return;
    this.history.push(this._snapshot());
    if (this.history.length > 60) this.history.shift();
    this._syncUndoBtn();
  },

  _applySnapshot(s) {
    const byId = Object.fromEntries((this.data.nodes || []).map(n => [n.id, n]));
    (s.nodes || []).forEach(item => {
      const n = byId[item.id];
      if (!n) return;
      n.x = item.x; n.y = item.y; n.placed = item.placed;
    });
    this.data.edges = (s.edges || []).map(e => ({ source: e.source, target: e.target, relation: e.relation }));
    if (this.sel && this.sel.type === 'edge' &&
        !this.data.edges.some(e => this._edgeKey(e) === this.sel.id)) this.sel = null;
    this.paintLeft();
    this.paintBanner();
    this.draw();
  },

  undo() {
    if (!this.history.length) { Toast.warn('没有可撤回的操作'); return; }
    this._applySnapshot(this.history.pop());
    this._syncUndoBtn();
    Toast.ok('已撤回');
  },

  _syncUndoBtn() {
    const b = U.$('#geUndo');
    if (!b) return;
    b.disabled = !this.history.length;
    b.style.opacity = this.history.length ? '' : '0.5';
  },

  /* ------------------------------------------------------------------ */
  /* 删除 / 适配 / 保存                                                    */
  /* ------------------------------------------------------------------ */
  delSel() {
    if (!this.sel) { Toast.warn('请先选中节点或边'); return; }
    this._pushHistory();
    if (this.sel.type === 'node') {
      const n = (this.data.nodes || []).find(x => x.id === this.sel.id);
      if (n) { n.x = null; n.y = null; n.placed = false; }
      this.data.edges = (this.data.edges || []).filter(e => e.source !== this.sel.id && e.target !== this.sel.id);
      Toast.ok('已移出画布', '知识点仍保留在课程目录');
    } else {
      const key = this.sel.id;
      this.data.edges = (this.data.edges || []).filter(e => this._edgeKey(e) !== key);
      Toast.ok('已删除连线');
    }
    this.sel = null;
    this.paintBanner();
    this.paintLeft();
    this.draw();
  },

  fitView() {
    const board = U.$('#geBoard');
    if (!board || !this.data) return;
    const nodes = (this.data.nodes || []).filter(n => n.x != null && n.y != null);
    if (!nodes.length) {
      this.cam = { x: 40, y: 40, k: 1 };
      this.draw();
      return;
    }
    const rect = board.getBoundingClientRect();
    const w = rect.width || board.clientWidth || 800;
    const h = rect.height || board.clientHeight || 500;
    if (w < 20 || h < 20) { setTimeout(() => this.fitView(), 50); return; }
    const pad = 56;
    const minX = Math.min(...nodes.map(n => n.x)) - 36;
    const maxX = Math.max(...nodes.map(n => n.x)) + 36;
    const minY = Math.min(...nodes.map(n => n.y)) - 36;
    const maxY = Math.max(...nodes.map(n => n.y)) + 36;
    const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
    const k = Math.min((w - pad * 2) / bw, (h - pad * 2) / bh, 1.6);
    this.cam.k = Math.max(0.35, k);
    this.cam.x = (w - bw * this.cam.k) / 2 - minX * this.cam.k;
    this.cam.y = (h - bh * this.cam.k) / 2 - minY * this.cam.k;
    this.draw();
  },

  save() {
    const nodes = (this.data.nodes || [])
      .filter(n => n.x != null && n.y != null)
      .map(n => ({ id: n.id, x: n.x, y: n.y }));
    const edges = (this.data.edges || []).map(e => ({
      source: e.source, target: e.target, relation: e.relation,
    }));
    API.teacher.saveKpTopology({ nodes, edges }).then(() => {
      Toast.ok('图谱已保存', `节点 ${nodes.length} · 边 ${edges.length}`);
      this.load();
    }).catch(err => Toast.error('保存失败', (err && err.message) || ''));
  },
};

window.TeacherGraphEdit = TeacherGraphEdit;
Router.register('graph-edit', {
  title: '知识图谱编排',
  mount: () => {
    TeacherGraphEdit.render();
    setTimeout(() => TeacherGraphEdit._bindBoardOnce(), 0);
  },
});
