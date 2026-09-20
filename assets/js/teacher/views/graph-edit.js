/* ==========================================================================
   教师端 · 知识图谱编排（ECharts 版 · 与学生端拖拽体验对齐）
   节点实时来自「课程目录与资源」的 KP；未布点的新 KP 会提醒教师更新图谱。
   - 节点拖拽用 ECharts 原生 draggable（canvas 重绘，不重建 DOM，流畅）
   - 视图（缩放/平移）完全由 ECharts roam 管理：重绘时 setOption 一律不传
     center/zoom（merge 保留视图），杜绝「重绘后整图跳位」
   - 坐标换算只走官方 convertToPixel/convertFromPixel：
     实测（echarts 5.5.1 SSR）series.center = 钉在视口中心的数据坐标，
     zoom=1 时按节点包围自动适配；getItemLayout 返回数据坐标（原生拖拽
     过程中 ECharts 会实时 setItemLayout 写入符号局部坐标）——拖拽结束
     直接把 itemLayout 写回业务 n.x/n.y，绝不能再过坐标变换
   - 默认即「选择 / 拖拽」；悬停节点出现「+」，点「+」选关系后点目标节点连线（Visio 式）
   - 不同章节节点用不同颜色区分；支持撤回；节点文本不可选中
   ========================================================================== */
'use strict';

const TeacherGraphEdit = {
  SERIES_ID: 'geGraph',
  data: null,                 // { nodes, edges, pending, pendingCount }
  rel: 'pre',
  sel: null,                  // { type:'node'|'edge', id, edgeIdx }
  _link: null,                // { src, rel } 连线进行中
  _plusId: null,
  _plusTimer: null,           // 悬停「+」延迟收起定时器（留出移动到「+」并点击的时间）
  _pressing: false,           // 画布按压/拖拽中：期间不显示「+」
  _downSnap: null,            // 画布内按下时的快照（拖拽入撤回栈用）
  history: [],
  leftTab: 'bank',
  _kpCache: {},               // kpId → 详情（教师端接口），避免重复请求
  chart: null,
  _ro: null,
  _keyHandler: null,
  _winUp: null,

  /** 章节配色（按章区分，最多 12 章） */
  CHAPTER_COLORS: [
    '#0ea5e9', '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316',
    '#f59e0b', '#10b981', '#14b8a6', '#06b6d4', '#a855f7', '#84cc16',
  ],
  /**
   * 关系配色（与学生端知识图谱共用 refresh.css 的 --rel-* 令牌，杜绝两端色彩漂移）。
   * 旧值 前置 #6366f1 / 进阶 #8b5cf6 色差 ΔE2000≈7.2，肉眼几乎同色；
   * 现值 前置=青绿 #0d9488、进阶=品红 #a21caf，ΔE2000≈45.7，白底对比度 6.32 可读。
   * 用 getter 而非静态对象：主题切换时自动跟随令牌，无需重建视图。
   */
  get REL() {
    const t = this._tokens();
    return {
      pre:      { color: t.relPre      || '#0d9488', label: '前置' },
      advance:  { color: t.relAdvance  || '#a21caf', label: '进阶' },
      parallel: { color: t.relParallel || '#718793', label: '并列' },
    };
  },

  _tokens() {
    try { return (window.Charts && Charts.tokens) ? Charts.tokens() : {}; }
    catch (e) { return {}; }
  },

  chapterColor(ch) {
    return (this.catColor && this.catColor[ch]) ||
      this.CHAPTER_COLORS[(this.chapters || []).indexOf(ch) % this.CHAPTER_COLORS.length] ||
      this.CHAPTER_COLORS[0];
  },

  nodeById(id) { return (this.data && this.data.nodes || []).find(n => n.id === id); },

  _w() { const b = U.$('#geBoard'); return b ? b.clientWidth : 800; },
  _h() { const b = U.$('#geBoard'); return b ? b.clientHeight : 520; },

  /** 已布点且坐标合法的节点（NaN 防御：NaN 节点交给 ECharts 会渲染失败 → “消失”） */
  placedNodes() {
    return (this.data && this.data.nodes || []).filter(n =>
      n.x != null && n.y != null && isFinite(n.x) && isFinite(n.y));
  },

  /** 数据坐标 → 画布像素（只信官方 API；失败返回 null，调用方自行处理） */
  dataToPixel(x, y) {
    if (!this.chart) return null;
    try {
      const p = this.chart.convertToPixel({ seriesIndex: 0 }, [x, y]);
      if (p && p.length === 2 && isFinite(p[0]) && isFinite(p[1])) return p;
    } catch (e) {}
    return null;
  },
  /** 画布像素 → 数据坐标（同上，只信官方 API） */
  pixelToData(px, py) {
    if (!this.chart) return null;
    try {
      const d = this.chart.convertFromPixel({ seriesIndex: 0 }, [px, py]);
      if (d && d.length === 2 && isFinite(d[0]) && isFinite(d[1])) return d;
    } catch (e) {}
    return null;
  },

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
              <button class="btn btn--sm btn--ghost" id="geFit" type="button">适配视图</button>
              <button class="btn btn--sm btn--danger" id="geDel" type="button">删除选中</button>
              <button class="btn btn--sm btn--ghost" id="geUndo" type="button">↶ 撤回</button>
              <span class="spacer"></span>
              <span class="fz-12 t-dim" id="geHint">滚轮缩放 · 长按拖动节点 · 悬停节点看关系标签 / 点「+」连线 · 双击画布取消选中</span>
            </div>
            <div class="ge-board-box">
              <div id="geBoard" class="ge-board"></div>
              <div class="ge-overlay">
                <div class="ge-plus" id="gePlus" title="连线">+</div>
                <div class="ge-rel-menu" id="geRelMenu">
                  <button data-rel="pre"><i class="dot" style="background:var(--rel-pre)"></i>前置</button>
                  <button data-rel="advance"><i class="dot" style="background:var(--rel-advance)"></i>进阶</button>
                  <button data-rel="parallel"><i class="dot" style="background:var(--rel-parallel)"></i>并列</button>
                </div>
              </div>
              <div class="ge-rel-legend">
                <div class="row"><i class="ln" style="border-color:var(--rel-pre)"></i>前置</div>
                <div class="row"><i class="ln" style="border-color:var(--rel-advance)"></i>进阶</div>
                <div class="row"><i class="ln" style="border-color:var(--rel-parallel);border-top-style:dashed"></i>并列（双向）</div>
              </div>
            </div>
          </section>
          <aside class="ge-side" id="geSide"></aside>
        </div>
      </div>
      <style>
        .view.is-active#view-graph-edit{display:block;height:calc(100vh - var(--topbar-h) - 44px);min-height:0}
        #view-graph-edit .ge-root{
          height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;margin:0;
        }
        #view-graph-edit .ge-head{flex:0 0 auto;flex-shrink:0}
        #view-graph-edit .ge-shell{
          display:grid;grid-template-columns:240px minmax(0,1fr) 330px;
          flex:1 1 auto;min-height:0;height:0;
        }
        #view-graph-edit .ge-panel{
          border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;overflow:hidden;
        }
        #view-graph-edit .ge-tabs{display:flex;gap:6px;padding:8px 10px;flex-shrink:0}
        #view-graph-edit .ge-tabs .tab{
          flex:1;height:30px;border-radius:8px;border:1px solid var(--border);
          background:var(--surface-2);font-size:12px;cursor:pointer;
        }
        #view-graph-edit .ge-tabs .tab.on{background:rgba(15,118,110,.12);border-color:#5eead4;color:var(--brand)}
        #view-graph-edit .ge-list{flex:1;overflow:auto;padding:0 10px 12px;min-height:0}
        #view-graph-edit .ge-ch{font-size:11px;color:var(--text-3);margin:10px 2px 6px;font-weight:600}
        #view-graph-edit .ge-item{
          display:flex;align-items:center;gap:8px;padding:8px 10px;
          border:1px solid var(--border);border-radius:10px;background:var(--surface-2);
          margin-bottom:6px;cursor:pointer;font-size:12.5px;user-select:none;
        }
        #view-graph-edit .ge-item:hover{border-color:#5eead4}
        #view-graph-edit .ge-item .swatch{width:10px;height:10px;border-radius:50%;flex-shrink:0}
        #view-graph-edit .ge-item .id{margin-left:auto;font-size:10px;color:var(--text-3);font-family:ui-monospace,monospace}
        #view-graph-edit .ge-canvas-wrap{
          display:flex;flex-direction:column;min-width:0;min-height:0;position:relative;overflow:hidden;
        }
        #view-graph-edit .ge-tools{
          display:flex;align-items:center;gap:8px;padding:8px 12px;
          border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0;z-index:4;background:var(--surface);
        }
        #view-graph-edit .ge-board-box{
          position:relative;flex:1 1 auto;min-height:0;overflow:hidden;
          /* 网格底纹与学生端 .graph-box 一致 */
          background:
            linear-gradient(var(--grid-line) 1px,transparent 1px) 0 0/26px 26px,
            linear-gradient(90deg,var(--grid-line) 1px,transparent 1px) 0 0/26px 26px,
            var(--bg);
        }
        #view-graph-edit .ge-board{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none;user-select:none}
        #view-graph-edit .ge-overlay{position:absolute;inset:0;pointer-events:none;z-index:2}
        #view-graph-edit .ge-plus{
          position:absolute;display:none;align-items:center;justify-content:center;
          width:22px;height:22px;border-radius:50%;background:var(--brand-500,#6366f1);color:#fff;
          font-size:17px;line-height:1;cursor:pointer;pointer-events:auto;box-shadow:0 2px 8px rgba(0,0,0,.28);
          transform:translate(0,-50%);user-select:none;
        }
        #view-graph-edit .ge-plus:hover{background:var(--brand,#4f46e5)}
        #view-graph-edit .ge-rel-menu{
          position:absolute;display:none;background:var(--surface);border:1px solid var(--border);
          border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);padding:6px;pointer-events:auto;z-index:3;min-width:108px;
        }
        #view-graph-edit .ge-rel-menu button{
          display:flex;align-items:center;gap:8px;width:100%;padding:7px 9px;border:0;background:transparent;
          border-radius:7px;cursor:pointer;font-size:12.5px;color:var(--text);user-select:none;
        }
        #view-graph-edit .ge-rel-menu button:hover{background:var(--surface-2)}
        #view-graph-edit .ge-rel-menu .dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
        #view-graph-edit .ge-rel-legend{
          position:absolute;left:12px;bottom:10px;display:flex;gap:12px;
          background:var(--surface);border:1px solid var(--border);border-radius:8px;
          padding:6px 10px;font-size:11px;color:var(--text-2);pointer-events:none;z-index:1;user-select:none;
        }
        #view-graph-edit .ge-rel-legend .row{display:flex;align-items:center;gap:5px}
        #view-graph-edit .ge-rel-legend .ln{width:16px;height:0;border-top:2px solid var(--text-3)}
        /* ---- 右侧知识点详情面板 ---- */
        #view-graph-edit .ge-side{
          border-left:1px solid var(--border);display:flex;flex-direction:column;
          min-height:0;overflow:hidden;background:var(--surface);
        }
        #view-graph-edit .ge-side__empty{padding:44px 18px;text-align:center;color:var(--text-3);font-size:12.5px;line-height:1.9}
        #view-graph-edit .ge-side__head{padding:14px 14px 10px;border-bottom:1px solid var(--border-soft)}
        #view-graph-edit .ge-side__head h3{font-size:15px;line-height:1.4;margin-bottom:8px}
        #view-graph-edit .ge-side__body{flex:1;min-height:0;overflow-y:auto;padding:12px 14px 16px}
        #view-graph-edit .ge-sec{margin-bottom:16px}
        #view-graph-edit .ge-sec__t{
          display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700;color:var(--text-2);margin-bottom:8px;
        }
        #view-graph-edit .ge-sec__t::before{content:'';width:3px;height:13px;border-radius:2px;background:var(--brand)}
        #view-graph-edit .ge-sec__note{font-size:11px;color:var(--text-3);font-weight:400;margin-left:auto}
        #view-graph-edit .ge-text{font-size:12.5px;line-height:1.85;color:var(--text-2);position:relative}
        #view-graph-edit .ge-text.is-clamped{max-height:5.6em;overflow:hidden}
        #view-graph-edit .ge-text.is-clamped::after{
          content:'';position:absolute;left:0;right:0;bottom:0;height:2.2em;
          background:linear-gradient(transparent,var(--surface-2));
        }
        #view-graph-edit .ge-intro{
          background:var(--surface-2);border:1px solid var(--border);
          border-radius:var(--r-md);padding:10px 12px;
        }
        #view-graph-edit .ge-intro--empty{
          border-style:dashed;background:transparent;color:var(--text-3);
          font-size:12px;line-height:1.7;
        }
        #view-graph-edit .ge-more{margin-top:6px;font-size:11.5px;color:var(--brand);cursor:pointer;background:none;border:0;padding:0}
        #view-graph-edit .ge-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
        #view-graph-edit .ge-stat{
          border:1px solid var(--border);border-radius:var(--r-md);padding:9px 6px;text-align:center;background:var(--surface-2);
        }
        #view-graph-edit .ge-stat b{display:block;font-size:16px;font-family:ui-monospace,monospace;line-height:1.35}
        #view-graph-edit .ge-stat span{font-size:11px;color:var(--text-3)}
        #view-graph-edit .ge-stat--avg{background:transparent;border-style:dashed}
        #view-graph-edit .ge-stat--avg b{font-size:14px;color:var(--text-2)}
        #view-graph-edit .ge-side__foot{
          display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--border-soft);
          background:var(--surface-2);flex-shrink:0;
        }
        #view-graph-edit .ge-side__foot .btn{flex:1;justify-content:center}
      </style>`;

    this.leftTab = 'bank';
    this.sel = null;
    this._link = null;
    this._downSnap = null;
    this.history = [];
    this._bindShell();
    this._bindChart();
    this.paintSideEmpty();
    this.load();
  },

  _bindShell() {
    U.$('#geRefresh').addEventListener('click', () => this.load());
    U.$('#geSave').addEventListener('click', () => this.save());
    U.$('#geFit').addEventListener('click', () => this.fitView());
    U.$('#geDel').addEventListener('click', () => this.delSel());
    U.$('#geUndo').addEventListener('click', () => this.doUndo());
    // 悬停「+」：点它打开关系菜单（Visio 式连线第一步；此处必须绑定，否则「+」点了没反应）
    const plusBtn = U.$('#gePlus');
    if (plusBtn) {
      plusBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (this._plusId) this.openRelMenu(this._plusId);
      });
      // 光标移入「+」本身时保持显示（跨过节点与「+」之间的空隙不会被收起）
      plusBtn.addEventListener('mouseenter', () => this._clearPlusTimer());
      plusBtn.addEventListener('mouseleave', () => this.hidePlusSoon());
    }
    // 关系菜单
    U.$$('#geRelMenu button').forEach(b => b.addEventListener('click', () => {
      if (this._relSrc) this.startLink(this._relSrc, b.dataset.rel);
      this._hideRelMenu();
    }));
    // 全局快捷键（仅在当前视图激活时生效）
    if (this._keyHandler) document.removeEventListener('keydown', this._keyHandler);
    this._keyHandler = (e) => {
      const view = U.$('#view-graph-edit');
      if (!view || !view.classList.contains('is-active')) return;
      if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); this.doUndo(); }
      else if (e.key === 'Escape') { if (this._link) this.cancelLink(); else this.clearSel(); }
      else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (this.sel) { e.preventDefault(); this.delSel(); }
      }
    };
    document.addEventListener('keydown', this._keyHandler);
    // 左栏 tab
    U.$$('.ge-tabs .tab', U.$('#view-graph-edit')).forEach(t => {
      t.addEventListener('click', () => {
        this.leftTab = t.dataset.tab;
        U.$$('.ge-tabs .tab', U.$('#view-graph-edit')).forEach(x => x.classList.toggle('on', x === t));
        this.paintLeft();
      });
    });
  },

  _initChart() {
    if (!window.echarts) return;
    if (this.chart) { try { this.chart.dispose(); } catch (e) {} }
    this._downSnap = null;
    this._hoverNode = null; this._hoverEdge = null; this._relSig = null;
    this.chart = echarts.init(U.$('#geBoard'), null, { renderer: 'canvas' });
    // 悬停节点 → 显示与之相连线段的关系标签（默认隐藏）；同时就位悬停「+」
    this.chart.on('mouseover', p => {
      if (p.dataType === 'node') {
        this._hoverNode = p.data.id; this._hoverEdge = null;
        this._syncRelLabels();
      } else if (p.dataType === 'edge') {
        this._hoverNode = null; this._hoverEdge = this._edgeIdxOf(p);
        this._syncRelLabels();
      }
      if (!this._link && !this._pressing && p.dataType === 'node') this.showPlus(p.data.id);
    });
    this.chart.on('mouseout', p => {
      if (p.dataType === 'node' && this._hoverNode === p.data.id) { this._hoverNode = null; this._syncRelLabels(); }
      else if (p.dataType === 'edge' && this._hoverEdge === this._edgeIdxOf(p)) { this._hoverEdge = null; this._syncRelLabels(); }
      if (p.dataType === 'node' && !this._link) this.hidePlusSoon();   // 延迟收起，便于点到「+」
    });
    this.chart.on('globalout', () => {
      this._hoverNode = null; this._hoverEdge = null; this._syncRelLabels();
    });
    this.chart.on('click', p => this.onChartClick(p));
    // roam（滚轮缩放/背景平移）后重定位悬停「+」（注意事件名为驼峰 graphRoam）
    this.chart.on('graphRoam', () => this._refreshPlus());
    // 双击画布：取消节点选中（与参考交互一致）
    this.chart.getZr().on('dblclick', () => { if (!this._link) this.clearSel(); });

    // 拖拽收尾统一挂 window mouseup：画布内/外释放都能收到（zrender 内部
    // 拖拽布局更新先于本监听执行，此时 itemLayout 已是最终值）
    const zr = this.chart.getZr();
    zr.on('mousedown', () => {
      this._downSnap = this.snapshot();
      this._pressing = true;        // 按压/拖拽期间不显示「+」
      this.hidePlus();
    });
    const finishMouse = (e) => {
      this._pressing = false;
      if (!this._downSnap && !this._link) return;
      const board = U.$('#geBoard');
      if (!board) { this._downSnap = null; return; }
      const rect = board.getBoundingClientRect();
      const ox = e.clientX - rect.left, oy = e.clientY - rect.top;
      if (this._link) {
        // 连线模式：命中目标节点即连线；点空白取消（半径放宽，覆盖节点标签区域）
        const id = this.nodeAtPixel(ox, oy, 40);
        if (id && id !== this._link.src) {
          const from = this._link.src, rel = this._link.rel;
          this.connect(from, id, rel);
          this.showPlus(id);   // 连线后光标仍在目标节点上，「+」立即就位
        } else if (!id) this.cancelLink();
      } else {
        // 拖拽结束：把 ECharts 内部布局（数据坐标）写回业务数据
        this._syncPositionsFromChart();
        if (this._downSnap && this._moved(this._downSnap)) {
          this.pushHistory(this._downSnap);
        }
        // 悬停「+」重新吸附落点节点（拖拽后节点已移位，否则「+」滞留在原处）
        const hid = this.nodeAtPixel(ox, oy, 26);
        if (hid) this.showPlus(hid);
        else if (this.sel && this.sel.type === 'node') this.clearSel();
        // 拖拽期间禁用了标签刷新 → 松手后按落点重算一次（否则标签停在拖动前的节点上）
        this._hoverNode = hid || null; this._hoverEdge = null; this._relSig = null;
        this._syncRelLabels();
      }
      this._downSnap = null;
    };
    if (this._winUp) window.removeEventListener('mouseup', this._winUp);
    this._winUp = finishMouse;
    window.addEventListener('mouseup', finishMouse);

    // ResizeObserver：容器尺寸变化仅 resize，不重建
    if (this._ro) this._ro.disconnect();
    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(() => { if (this.chart) this.chart.resize(); });
      this._ro.observe(U.$('.ge-board-box', U.$('#view-graph-edit')));
    }
    // 若数据已加载（如视图切换后重进），立即重绘（首次 setOption 不带
    // center/zoom → ECharts 自动适配全部节点）
    if (this.data) { this.paintGraph(); this.fitView(); }
  },

  _bindChart() {
    // 首次渲染时 chart 容器才就绪，延迟一帧初始化
    requestAnimationFrame(() => { this._initChart(); });
  },

  load() {
    API.teacher.kpTopology().then(d => {
      this.data = d;
      // 章节 → 颜色映射（保持顺序稳定，使图例/节点/左栏一致）
      this.chapters = [...new Set((d.nodes || []).map(n => n.chapter || '未分类'))];
      this.catColor = {};
      this.chapters.forEach((c, i) => { this.catColor[c] = this.CHAPTER_COLORS[i % this.CHAPTER_COLORS.length]; });
      this.sel = null; this._link = null; this.history = [];
      this._kpCache = {};
      this.hidePlus(); this._hideRelMenu();
      this.paintLeft();
      this.paintBanner();
      this.paintGraph();
      this.fitView();
      this.paintSideEmpty();
    }).catch(err => Toast.err('加载图谱失败', (err && err.message) || ''));
  },

  /**
   * 适配视图：zoom=1 即 ECharts 的「按节点包围自动适配」（实测 echarts 5.5.1：
   * 适配倍率 = 0.8·min(vw/bw, vh/bh)，bw/bh 为节点中心包围跨度）。
   * 注意 center 必须传数值包围中心——merge setOption 下传 '50%' 会解析成
   * 错误钉点（实测把视图钉到 [5,0] 导致节点跑出视口），数值语义才稳定。
   */
  fitView() {
    if (!this.chart || !this.data) return;
    const nodes = this.placedNodes();
    if (!nodes.length) return;
    const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    this.chart.setOption({ series: [{ id: this.SERIES_ID, zoom: 1, center: [cx, cy] }] });
    this._refreshPlus();
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
        `可在左侧「待更新」点击加入画布并连线，保存后同步学生端知识图谱。` +
        `若刚在「课程目录与资源」新增了 KP，请点「从目录刷新」。`;
    } else { box.style.display = 'none'; }
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
      nodes.forEach(n => { const ch = n.chapter || '未分类'; (byCh[ch] = byCh[ch] || []).push(n); });
      box.innerHTML = Object.keys(byCh).map(ch => `
        <div class="ge-ch">${U.esc(ch)}</div>
        ${byCh[ch].map(n => `
          <div class="ge-item" data-id="${n.id}" title="${!n.placed ? '点击加入画布' : '已在画布'}">
            <span class="swatch" style="background:${this.chapterColor(ch)}"></span>
            <span>${U.esc(n.name)}</span>
            ${!n.placed ? '<span class="badge badge--warn" style="margin-left:auto">新</span>' : ''}
            <span class="id">${n.id}</span>
          </div>`).join('')}
      `).join('') || `<p class="fz-12 t-dim" style="padding:12px">当前课程暂无知识点，请先在「课程目录与资源」创建。</p>`;
    }
    U.$$('.ge-item', box).forEach(el => el.addEventListener('click', () => this.focusOrAdd(el.dataset.id)));
  },

  focusOrAdd(id) {
    const n = this.nodeById(id);
    if (!n || !this.chart) return;
    if (n.x == null || n.y == null || !isFinite(n.x) || !isFinite(n.y)) {
      // 加入画布：放到当前视口中心（像素 → 数据坐标，官方 API）
      const c = this.pixelToData(this._w() / 2, this._h() / 2) || this._viewCenterData() || [0, 0];
      n.x = Math.round(c[0]); n.y = Math.round(c[1]); n.placed = true;
      this.pushHistory(this.snapshot());
      this.paintBanner(); this.paintLeft(); this.paintGraph();
      Toast.ok('已加入画布', '拖拽调整位置后保存');
      return;
    }
    this.sel = { type: 'node', id };
    // 视口居中到该节点：center = 钉在视口中心的数据坐标（实测语义）
    this.chart.setOption({ series: [{ id: this.SERIES_ID, center: [n.x, n.y] }] });
    this.paintGraph();
  },

  /** 当前钉在视口中心的数据坐标（ECharts View 可读） */
  _viewCenterData() {
    try {
      const cs = this.chart.getModel().getSeriesByIndex(0).coordinateSystem;
      if (cs && typeof cs.getCenter === 'function') return cs.getCenter();
    } catch (e) {}
    return null;
  },

  /**
   * 节点选项数组。**唯一**的节点构造入口：buildOption（整图重绘）与
   * _syncPositionsFromChart（拖拽后回写 option）都必须走它，
   * 否则 option 里的 x/y 会与业务数据漂移 —— 见 _syncPositionsFromChart 的注释。
   */
  _buildNodes(t) {
    const nodes = this.placedNodes();
    const catIndex = {}; (this.chapters || []).forEach((c, i) => { catIndex[c] = i; });
    return nodes.map(n => {
      const ci = catIndex[n.chapter || '未分类'] || 0;
      const isSel = this.sel && this.sel.type === 'node' && this.sel.id === n.id;
      const isSrc = this._link && this._link.src === n.id;
      return {
        id: n.id, name: n.name, chapter: n.chapter, isKey: !!n.isKey,
        x: n.x, y: n.y, fixed: true, category: ci,
        symbolSize: n.isKey ? 34 : 26,
        itemStyle: {
          color: this.catColor[n.chapter || '未分类'] || this.CHAPTER_COLORS[0],
          borderColor: isSrc ? '#0ea5e9' : (isSel ? '#0ea5e9' : (n.isKey ? '#f59e0b' : 'transparent')),
          borderWidth: isSrc || isSel ? 3 : (n.isKey ? 2 : 0),
          shadowBlur: 10, shadowColor: (this.catColor[n.chapter || '未分类'] || this.CHAPTER_COLORS[0]) + '55',
        },
      };
    });
  },

  buildOption() {
    const t = this._tokens();
    const categories = (this.chapters || []).map(c => ({
      name: c, itemStyle: { color: this.catColor[c] || this.CHAPTER_COLORS[0] },
    }));
    const data = this._buildNodes(t);
    const links = this._buildLinks(t, this._relShowSet());
    return {
      animation: false, animationDuration: 0, animationDurationUpdate: 0,
      tooltip: {
        backgroundColor: t.surface || '#fff', borderColor: t.border || '#e2e8f0', borderWidth: 1,
        textStyle: { color: t.text || '#0f172a', fontSize: 12 },
        extraCssText: 'box-shadow:0 8px 28px rgba(0,0,0,.3);border-radius:8px;padding:9px 12px;',
        formatter(p) {
          if (p.dataType === 'edge') {
            const rr = TeacherGraphEdit.REL[p.data.relation] || TeacherGraphEdit.REL.pre;
            return `<b>${rr.label}关系</b><br/>${U.esc(p.data.source)} → ${U.esc(p.data.target)}`;
          }
          const d = p.data || {};
          let h = `<b style="font-size:13px">${U.esc(d.name || '')}</b>`;
          if (d.chapter) h += `<br/>${U.esc(d.chapter)}`;
          if (d.isKey) h += `<br/><span style="color:#f59e0b">◆ 重难点</span>`;
          return h + `<br/><span style="color:${t.dim || '#64748b'};font-size:11px">拖拽移动 · 悬停「+」连线</span>`;
        },
      },
      legend: {
        // selectedMode:false —— 图例仅供配色说明，点击不再隐藏章节节点（防误触“节点消失”）
        data: this.chapters || [], selectedMode: false,
        textStyle: { color: t.text2 || '#475569', fontSize: 11.5 },
        top: 8, left: 12, itemWidth: 11, itemHeight: 11, itemGap: 12, icon: 'circle',
      },
      series: [{
        id: this.SERIES_ID,
        type: 'graph', layout: 'none', roam: true,
        draggable: !this._link,
        // 注意：不传 center/zoom —— merge 模式下保留用户当前视图，
        // 仅 fitView/focusOrAdd 显式设置（实测：省略即保留，传错语义会整体错位）
        categories, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 7,
        label: {
          show: true, position: 'right', color: t.text || '#0f172a', fontSize: 11.5,
          formatter: (p) => { const s = p.data.name || ''; return s.length > 9 ? s.slice(0, 9) + '…' : s; },
        },
        emphasis: { focus: 'adjacency', scale: 1.08, label: { fontSize: 12.5, fontWeight: 'bold' }, lineStyle: { width: 3 } },
        lineStyle: { curveness: 0.14 },
        data, links,
      }],
    };
  },

  /**
   * 关系边选项。showSet = 需要显示关系标签（前置/进阶/并列 chip）的边下标集合。
   * 设计：关系标签默认隐藏，只有「悬停/选中某个节点」时才显示与之相连的线段标签，
   * 避免画布上几十个节点时标签糊成一片；连线本身仍按关系着色（前置青绿 / 进阶品红）。
   */
  _buildLinks(t, showSet) {
    const P = this.REL;
    const edges = (this.data && this.data.edges) || [];
    return edges.map((e, idx) => {
      const r = P[e.relation] || P.pre;
      const sel = this.sel && this.sel.type === 'edge' && this.sel.edgeIdx === idx;
      return {
        source: e.source, target: e.target, relation: e.relation,
        // 并列 = 双向并列关系 → 两端都画箭头（ECharts 支持按 link 覆盖 symbol，已实测）
        symbol: e.relation === 'parallel' ? ['arrow', 'arrow'] : ['none', 'arrow'],
        // 连线关系文字 chip（前置/进阶/并列）；opacity:1 抵消继承的半透明
        label: {
          show: showSet.has(idx), formatter: r.label, fontSize: 11, opacity: 1,
          color: r.color, backgroundColor: (t.surface || '#fff'),
          borderColor: r.color, borderWidth: 1, borderRadius: 6, padding: [2, 6],
        },
        lineStyle: {
          color: r.color, width: sel ? 3.4 : 1.8, curveness: 0.14,
          opacity: sel ? 0.95 : 0.62, type: e.relation === 'parallel' ? 'dashed' : 'solid',
          shadowBlur: sel ? 8 : 0, shadowColor: r.color,
        },
      };
    });
  },

  /** 当前应显示标签的边下标集合：悬停节点 > 悬停边 > 选中边 > 选中节点 */
  _relShowSet() {
    const edges = (this.data && this.data.edges) || [];
    const set = new Set();
    const addByNode = (id) => edges.forEach((e, i) => { if (e.source === id || e.target === id) set.add(i); });
    if (this._hoverNode && this.nodeById(this._hoverNode)) addByNode(this._hoverNode);
    else if (this._hoverEdge != null && this._hoverEdge >= 0) set.add(this._hoverEdge);
    else if (this.sel && this.sel.type === 'edge' && this.sel.edgeIdx != null) set.add(this.sel.edgeIdx);
    else if (this.sel && this.sel.type === 'node') addByNode(this.sel.id);
    return set;
  },

  /**
   * 悬停变化→只增量刷新 series.links（不传 nodes/center/zoom）：
   * 节点坐标、roam 视图、缩放、选中态全部保持不动，避免整图重建打断拖拽。
   * 签名与上次一致则跳过，防止同一节点内反复 mousemove 触发无谓重绘。
   */
  _syncRelLabels() {
    if (!this.chart || !this.data || this._pressing) return;
    const set = this._relShowSet();
    const sig = [...set].sort((a, b) => a - b).join(',');
    if (sig === this._relSig) return;
    this._relSig = sig;
    this.chart.setOption(
      { series: [{ id: this.SERIES_ID, links: this._buildLinks(this._tokens(), set) }] }, false);
  },

  /** 由 dataType:'edge' 的事件负载反查边下标（比 dataIndex 偏移更稳） */
  _edgeIdxOf(p) {
    if (!p || !p.data) return -1;
    return (this.data.edges || []).findIndex(e =>
      e.source === p.data.source && e.target === p.data.target && e.relation === p.data.relation);
  },

  paintGraph() {
    if (!this.chart || !this.data) return;
    const keep = this._viewKeep();          // 冻结视图（见 _viewKeep 注释）
    this.chart.setOption(this.buildOption(), false);
    this._relSig = null;   // 整图重建已按当前状态渲染，签名作废，下次悬停重新按需应用
    this._viewRestore(keep);
    this._refreshPlus();   // 重绘后「+」跟随节点（选中/连线/撤回等都会走到这里）
  },

  /**
   * 视图冻结（委托 charts.js 的同一实现，避免两处补偿算法漂移）。
   * 为什么需要：ECharts 对 graph(layout:'none') 在**每次 setOption** 都按节点包围盒
   * 重新适配视图，所以任何「改节点坐标」的重绘（拖拽落点回写、撤回/重做、增删节点）
   * 都会顺带改掉整图的缩放比例 —— 实测把某节点外移 (+120,-200)，像素/数据单位
   * 0.883 → 0.914，用户看到的就是「移动后界面比例异常缩小/放大」。
   * 用法固定为一对：const keep = _viewKeep(); …改几何…; _viewRestore(keep);
   * 有意改视图的操作（fitView / focusOrAdd 的 center）要先改，再进这里，否则会被冻掉。
   */
  _viewKeep() {
    // ⚠ charts.js 里的 Charts 是顶层 const（脚本级词法全局），**不挂在 window 上**：
    //   写 `window.Charts && …` 永远为假 → 冻结被静默跳过（本 bug 第一版就是这样失效的，
    //   实测教师端松手后比例仍从 0.883 变 0.910）。只能用 typeof 判定。
    try {
      return (typeof Charts !== 'undefined' && Charts.viewMetrics) ? Charts.viewMetrics(this.chart) : null;
    } catch (e) { return null; }
  },
  _viewRestore(keep) {
    if (!keep) return;
    try {
      if (typeof Charts !== 'undefined' && Charts.restoreView) {
        Charts.restoreView(this.chart, keep, { id: this.SERIES_ID });
      }
    } catch (e) {}
  },

  /**
   * 拖拽结束：把 ECharts 内部实时布局写回业务数据。
   * 关键（实测 echarts 5.5.1）：graph(layout:none) 原生拖拽时 ECharts 直接
   * setItemLayout(idx, [symbol.x, symbol.y])，itemLayout 即「数据坐标」——
   * 直接写回 n.x/n.y 即可，绝不能再做任何坐标变换（此前把 itemLayout 当
   * 屏幕像素二次逆变换，导致节点每次 mouseup 被平移 → 漂移/异常消失）。
   */
  _syncPositionsFromChart() {
    if (!this.chart || !this.data) return;
    let sData = null;
    try {
      const sModel = this.chart.getModel().getSeriesByIndex(0);
      if (sModel) sData = sModel.getData();
    } catch (e) { return; }
    if (!sData) return;
    const opt = this.chart.getOption();
    const optData = (opt && opt.series && opt.series[0] && opt.series[0].data) || [];
    let moved = false;
    optData.forEach((d, i) => {
      if (!d || d.id == null) return;
      const n = this.nodeById(d.id);
      if (!n) return;
      let lay = null;
      try { lay = sData.getItemLayout(i); } catch (e) {}
      if (lay && isFinite(lay[0]) && isFinite(lay[1])) {
        if (n.x == null || n.y == null || Math.abs(n.x - lay[0]) > 0.01 || Math.abs(n.y - lay[1]) > 0.01) moved = true;
        n.x = lay[0]; n.y = lay[1]; n.placed = true;
      }
    });
    // 关键（本 bug 的根因）：ECharts 对 graph(layout:'none') 在**每一次 setOption**
    // 都会按 option 里的 data[].x/y 重跑静态布局，把原生拖拽期间 setItemLayout
    // 写入的坐标覆盖掉。若只把新坐标写回业务数据而不写回 option，
    // 松手后的任何一次 setOption（悬停刷关系标签 / fitView / 重绘）都会把节点
    // **弹回拖拽前的原位**，直到下一次整图重绘才跳到新位置 —— 用户看到的就是
    // 「能拖但固定不住」。所以这里必须顺手把当前坐标推回 option，令二者恒等。
    if (moved) {
      const keep = this._viewKeep();   // 此刻画布还是「旧包围盒」的视图，正是要保住的基准
      this.chart.setOption({ series: [{ id: this.SERIES_ID, data: this._buildNodes(this._tokens()) }] }, false);
      // 回写新坐标会被 ECharts 按新包围盒重新适配视图（整图比例变化）→ 补偿回来
      this._viewRestore(keep);
    }
  },

  nodeAtPixel(x, y, radius) {
    let best = null, bd = (radius || 24);
    (this.data.nodes || []).forEach(n => {
      if (n.x == null || !isFinite(n.x) || n.y == null || !isFinite(n.y)) return;
      const px = this.dataToPixel(n.x, n.y);
      if (!px) return;
      const d = Math.hypot(px[0] - x, px[1] - y);
      if (d < bd) { bd = d; best = n.id; }
    });
    return best;
  },

  showPlus(id) {
    const n = this.nodeById(id);
    // 节点不存在 / 未布点 / 坐标非法（如刚被移出画布或撤回）→ 直接收起，避免「+」滞留在空白处
    if (!n || n.x == null || n.y == null || !isFinite(n.x) || !isFinite(n.y)) { this.hidePlus(); return; }
    const px = this.dataToPixel(n.x, n.y);
    if (!px) { this.hidePlus(); return; }
    this._clearPlusTimer();
    const r = n.isKey ? 17 : 13;
    const plus = U.$('#gePlus');
    plus.style.left = (px[0] + r + 6) + 'px';
    plus.style.top = (px[1]) + 'px';
    plus.style.display = 'flex';
    this._plusId = id;
  },
  hidePlus() {
    this._clearPlusTimer();
    const p = U.$('#gePlus'); if (p) p.style.display = 'none';
    this._plusId = null;
  },
  /** 延迟收起悬停「+」：节点与「+」之间有 ~20px 空隙，立即收起会来不及移过去点击 */
  hidePlusSoon(delay) {
    this._clearPlusTimer();
    this._plusTimer = setTimeout(() => { this._plusTimer = null; this.hidePlus(); }, delay == null ? 420 : delay);
  },
  _clearPlusTimer() { if (this._plusTimer) { clearTimeout(this._plusTimer); this._plusTimer = null; } },

  /** 视图/节点位置变化后让悬停「+」跟随节点（防止「+」滞留在旧位置）；拖拽中不显示 */
  _refreshPlus() { if (this._plusId && !this._pressing) this.showPlus(this._plusId); },

  _hideRelMenu() { const m = U.$('#geRelMenu'); if (m) m.style.display = 'none'; this._relSrc = null; },

  openRelMenu(id) {
    const plus = U.$('#gePlus'); const box = U.$('#geBoard');
    if (!plus || !box) return;
    const pr = plus.getBoundingClientRect(), br = box.getBoundingClientRect();
    const menu = U.$('#geRelMenu');
    menu.style.left = (pr.right - br.left + 4) + 'px';
    menu.style.top = (pr.top - br.top) + 'px';
    menu.style.display = 'block';
    this._relSrc = id;
  },

  startLink(src, rel) {
    this._link = { src, rel };
    this.hidePlus(); this._hideRelMenu();
    const n = this.nodeById(src);
    U.$('#geHint').textContent = `已选起点「${n ? n.name : src}」，点击目标节点完成「${this.REL[rel].label}」连线（Esc 取消）`;
    this.paintGraph();
  },
  cancelLink() {
    this._link = null;
    U.$('#geHint').textContent = '拖拽移动节点 · 悬停节点看关系标签 / 点「+」连线 · 点击节点/边选中 · 滚轮缩放平移';
    this.paintGraph();
  },

  onChartClick(p) {
    // 连线模式一律由 window mouseup 命中判定（含标签区域、画布外释放），此处只做普通选择
    if (this._link) return;
    if (!p || !p.dataType) { this.clearSel(); return; }
    if (p.dataType === 'node') {
      this.sel = { type: 'node', id: p.data.id };
      this.paintGraph();
      this.paintSide();
    } else if (p.dataType === 'edge') {
      const idx = (this.data.edges || []).findIndex(e =>
        e.source === p.data.source && e.target === p.data.target && e.relation === p.data.relation);
      this.sel = { type: 'edge', edgeIdx: idx };
      this.paintGraph();
      this.paintSide();
    }
  },

  clearSel() { this.sel = null; this.paintGraph(); this.paintSide(); },

  /* ============ 右侧知识点详情面板 ============ */
  paintSideEmpty() {
    const box = U.$('#geSide');
    if (!box) return;
    box.innerHTML = `
      <div class="ge-side__empty">
        <div style="font-size:30px;margin-bottom:10px">🧭</div>
        <b style="color:var(--text-2);font-size:13px;display:block;margin-bottom:6px">知识点详情</b>
        点击画布上的节点<br>查看解释、属性、关系与班级学情
      </div>`;
  },

  paintSide() {
    const box = U.$('#geSide');
    if (!box) return;
    if (!this.sel || this.sel.type !== 'node') { this.paintSideEmpty(); return; }
    if (!API.teacher || typeof API.teacher.kpDetail !== 'function') { this.paintSideEmpty(); return; }
    const id = this.sel.id;
    if (this._kpCache[id]) { this._paintSideData(this._kpCache[id]); return; }
    box.innerHTML = '<div class="ge-side__empty">加载中…</div>';
    let req;
    try { req = API.teacher.kpDetail({ kpId: id }); } catch (e) { this.paintSideEmpty(); return; }
    req.then(d => {
      if (!d) { this.paintSideEmpty(); return; }
      this._kpCache[id] = d;
      if (this.sel && this.sel.type === 'node' && this.sel.id === id) this._paintSideData(d);
    }).catch(err => {
      const b = U.$('#geSide');
      if (b && !b.querySelector('#geSideFocus')) b.innerHTML = '<div class="ge-side__empty">详情加载失败</div>';
      Toast.err('知识点详情加载失败', (err && err.message) || '');
    });
  },

  /** 关系 chips：取当前画布的边（含未保存改动），与图上所见一致 */
  _relChips(id) {
    const nm = (x) => { const n = this.nodeById(x); return n ? n.name : x; };
    const E = this.data.edges || [];
    const uniq = (a) => [...new Set(a)];
    return {
      pre: uniq(E.filter(e => e.target === id && e.relation === 'pre').map(e => nm(e.source))),
      post: uniq(E.filter(e => e.source === id && e.relation === 'pre').map(e => nm(e.target))),
      parallel: uniq(E.filter(e => e.relation === 'parallel' && (e.source === id || e.target === id))
        .map(e => nm(e.source === id ? e.target : e.source))),
    };
  },

  _chips(list, color) {
    return list.length
      ? `<div class="chips">${list.map(n => `<span class="chip" style="border-color:${color};color:${color}">${U.esc(n)}</span>`).join('')}</div>`
      : '<span class="fz-12 t-dim">暂无</span>';
  },

  _paintSideData(d) {
    const box = U.$('#geSide');
    if (!box) return;
    const node = this.nodeById(d.kpId);
    const rel = this._relChips(d.kpId);
    const num = (v, unit) => (v === null || v === undefined || v === '' ? '—' : v + (unit || ''));
    const dur = (m) => (m === null || m === undefined || m === '' ? '—' : U.durMin(m));
    const intro = (d.summary || '').trim();
    box.innerHTML = `
      <div class="ge-side__head">
        <h3>${U.esc(d.name || (node && node.name) || d.kpId)}</h3>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          <span class="badge badge--brand">${U.esc(d.chapter || '未分章')}</span>
          ${d.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}
          <span class="badge badge--outline">难度 ${'★'.repeat(d.difficulty || 0) || '—'}</span>
          <span class="badge badge--outline">${d.hours || 0} 学时</span>
        </div>
      </div>
      <div class="ge-side__body">
        <div class="ge-sec">
          <div class="ge-sec__t">知识点介绍</div>
          ${intro ? `
            <div class="ge-intro"><div class="ge-text is-clamped" id="geText">${U.esc(intro)}</div></div>
            <button class="ge-more" id="geMore" type="button" style="display:none">展开</button>`
          : '<div class="ge-intro ge-intro--empty">该知识点暂无介绍，可在「课程目录与资源 → 知识点详情」中补充</div>'}
        </div>
        <div class="ge-sec">
          <div class="ge-sec__t">学情概览<span class="ge-sec__note">课程平均</span></div>
          <div class="ge-stats">
            <div class="ge-stat"><b>${num(d.courseAvgCompletion, '%')}</b><span>平均完成度</span></div>
            <div class="ge-stat"><b>${num(d.courseAvgMastery, '%')}</b><span>平均掌握度</span></div>
            <div class="ge-stat"><b>${dur(d.courseAvgMinutes)}</b><span>平均时长</span></div>
          </div>
          <p class="fz-11 t-dim" style="margin-top:8px;line-height:1.7">
            分母 = 课程内 ${d.courseStudentCount || 0} 名学生（${d.courseStudiedCount || 0} 人在此知识点有学习记录）。
            学习时长 = 视频观看进度 + 练习作答时长。
          </p>
        </div>
        <div class="ge-sec">
          <div class="ge-sec__t">属性</div>
          <div class="chips">
            <span class="chip">题库 ${d.questionCount || 0} 题</span>
            <span class="chip">资源 ${d.resourceCount || 0} 个</span>
            <span class="chip">${(node && node.placed) ? '已布点' : '未布点'}</span>
          </div>
        </div>
        <div class="ge-sec">
          <div class="ge-sec__t">知识点关系</div>
          <p class="fz-11 t-dim" style="margin:0 0 6px">前置知识点</p>
          ${this._chips(rel.pre, 'var(--rel-pre)')}
          <p class="fz-11 t-dim" style="margin:12px 0 6px">进阶知识点</p>
          ${this._chips(rel.post, 'var(--rel-advance)')}
          <p class="fz-11 t-dim" style="margin:12px 0 6px">并列知识点</p>
          ${this._chips(rel.parallel, 'var(--rel-parallel)')}
        </div>
      </div>
      <div class="ge-side__foot">
        <button class="btn btn--outline btn--sm" id="geSideFocus" type="button">居中显示</button>
        <button class="btn btn--danger btn--sm" id="geSideDel" type="button">移出画布</button>
      </div>`;

    // 介绍：仅当内容确实超出折叠高度时才提供「展开」
    const more = U.$('#geMore', box);
    const txt = U.$('#geText', box);
    if (more && txt) {
      if (txt.scrollHeight - txt.clientHeight > 4) more.style.display = '';
      else txt.classList.remove('is-clamped');
      more.addEventListener('click', () => {
        more.textContent = txt.classList.toggle('is-clamped') ? '展开' : '收起';
      });
    }
    U.$('#geSideFocus', box).addEventListener('click', () => this.focusOrAdd(d.kpId));
    U.$('#geSideDel', box).addEventListener('click', () => {
      this.sel = { type: 'node', id: d.kpId };
      this.delSel();
    });
  },

  connect(src, target, rel) {
    if (src === target) { Toast.warn('不能连接到自身'); return; }
    const exists = (this.data.edges || []).some(e => e.source === src && e.target === target && e.relation === rel);
    if (exists) { Toast.warn('两点之间已有该类型连线'); this._link = null; this.cancelLink(); return; }
    this.pushHistory(this.snapshot());
    this.data.edges.push({ source: src, target, relation: rel });
    this._link = null;
    this.paintGraph();
    Toast.ok('已连线', this.REL[rel].label);
  },

  delSel() {
    if (!this.sel) { Toast.warn('请先选中节点或边'); return; }
    if (this.sel.type === 'node') {
      const n = this.nodeById(this.sel.id);
      if (n) { n.x = null; n.y = null; n.placed = false; }
      this.data.edges = (this.data.edges || []).filter(e => e.source !== this.sel.id && e.target !== this.sel.id);
      Toast.ok('已移出画布', '知识点仍保留在课程目录');
    } else if (this.sel.edgeIdx != null && this.data.edges[this.sel.edgeIdx]) {
      this.data.edges.splice(this.sel.edgeIdx, 1);
      Toast.ok('已删除连线');
    }
    this.pushHistory(this.snapshot());
    this.sel = null;
    this.paintBanner(); this.paintLeft(); this.paintGraph(); this.paintSide();
  },

  /* ============ 撤回 ============ */
  snapshot() {
    return {
      nodes: this.placedNodes().map(n => ({ id: n.id, x: n.x, y: n.y })),
      edges: JSON.parse(JSON.stringify(this.data.edges || [])),
    };
  },
  _moved(snap) {
    const map = {}; snap.nodes.forEach(s => { map[s.id] = s; });
    let changed = false;
    (this.data.nodes || []).forEach(n => {
      const s = map[n.id];
      if (s && (Math.abs(s.x - n.x) > 0.01 || Math.abs(s.y - n.y) > 0.01)) changed = true;
    });
    return changed;
  },
  pushHistory(snap) {
    this.history.push(snap);
    if (this.history.length > 40) this.history.shift();
  },
  doUndo() {
    if (!this.history.length) { Toast.warn('没有可撤回的操作'); return; }
    const s = this.history.pop();
    const ids = new Set(s.nodes.map(x => x.id));
    (this.data.nodes || []).forEach(n => {
      if (n.x != null && !ids.has(n.id)) { n.x = null; n.y = null; n.placed = false; }
    });
    s.nodes.forEach(x => { const n = this.nodeById(x.id); if (n) { n.x = x.x; n.y = x.y; n.placed = true; } });
    this.data.edges = JSON.parse(JSON.stringify(s.edges));
    this.sel = null; this._link = null;
    this.paintBanner(); this.paintLeft(); this.paintGraph(); this.paintSide();
    Toast.ok('已撤回');
  },

  save() {
    const nodes = this.placedNodes().map(n => ({ id: n.id, x: n.x, y: n.y }));
    const edges = (this.data.edges || []).map(e => ({ source: e.source, target: e.target, relation: e.relation }));
    API.teacher.saveKpTopology({ nodes, edges }).then(r => {
      Toast.ok('图谱已保存', `节点 ${nodes.length} · 边 ${edges.length}`);
      this.load();
    }).catch(err => Toast.err('保存失败', (err && err.message) || ''));
  },
};

window.TeacherGraphEdit = TeacherGraphEdit;
Router.register('graph-edit', {
  title: '知识图谱编排',
  mount: () => {
    TeacherGraphEdit.render();
  },
});
