/* ==========================================================================
   教师端 · 知识图谱编排（方案 B · 彩色圆形节点）
   节点实时来自「课程目录与资源」的 KP；未布点的新 KP 会提醒教师更新图谱。
   ========================================================================== */
'use strict';

const TeacherGraphEdit = {
  data: null,          // { nodes, edges, pending }
  mode: 'select',      // select | connect
  rel: 'pre',
  sel: null,
  src: null,
  cam: { x: 40, y: 40, k: 1 },
  leftTab: 'bank',
  _drag: null,
  _pan: null,

  COLORS: [
    '#0f766e', '#0284c7', '#7c3aed', '#db2777',
    '#d97706', '#059669', '#4f46e5', '#be185d',
    '#0e7490', '#65a30d', '#9333ea', '#ea580c',
  ],

  /** 与学生端知识图谱同一套分类色（CATEGORY_COLORS.knowledge） */
  categoryColor(category) {
    const colors = ['#22c55e', '#6366f1', '#f59e0b', '#64748b', '#ef4444'];
    const i = Number(category || 0);
    return colors[i] || colors[3];
  },

  chapterColor(chapter) {
    // 兼容左侧色点：仍按章着色便于目录辨识；画布节点用 categoryColor
    const chapters = [...new Set((this.data.nodes || []).map(n => n.chapter || '未分类'))];
    const idx = Math.max(0, chapters.indexOf(chapter || '未分类'));
    return this.COLORS[idx % this.COLORS.length];
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
              <button class="btn btn--sm on" id="geModeSelect" type="button">选择 / 拖拽</button>
              <button class="btn btn--sm" id="geModeConnect" type="button">连线</button>
              <select class="select select--sm" id="geRel" style="width:120px">
                <option value="pre">前置</option>
                <option value="advance">进阶</option>
                <option value="parallel">并列</option>
              </select>
              <button class="btn btn--sm btn--danger" id="geDel" type="button">删除选中</button>
              <button class="btn btn--sm btn--ghost" id="geFit" type="button">适配视图</button>
              <span class="fz-12 t-dim" id="geHint">点击左侧知识点加入画布；连线模式建立关系</span>
            </div>
            <div class="ge-board-box">
              <svg id="geBoard" class="ge-board" xmlns="http://www.w3.org/2000/svg"></svg>
            </div>
          </section>
        </div>
      </div>
      <style>
        .view.is-active#view-graph-edit{display:block;height:calc(100vh - var(--topbar-h) - 44px);min-height:0}
        #view-graph-edit .ge-root{
          height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;
          margin:0;
        }
        #view-graph-edit .ge-head{flex:0 0 auto;flex-shrink:0}
        #view-graph-edit .ge-shell{
          display:grid;grid-template-columns:240px minmax(0,1fr);
          flex:1 1 auto;min-height:0;height:0; /* height:0 + flex 让子项可收缩 */
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
          margin-bottom:6px;cursor:pointer;font-size:12.5px;
        }
        #view-graph-edit .ge-item:hover{border-color:#5eead4}
        #view-graph-edit .ge-item .swatch{width:10px;height:10px;border-radius:50%;flex-shrink:0}
        #view-graph-edit .ge-item .id{margin-left:auto;font-size:10px;color:var(--text-3);font-family:ui-monospace,monospace}
        #view-graph-edit .ge-canvas-wrap{
          display:flex;flex-direction:column;min-width:0;min-height:0;position:relative;overflow:hidden;
        }
        #view-graph-edit .ge-tools{
          display:flex;align-items:center;gap:8px;padding:8px 12px;
          border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0;z-index:1;background:var(--surface);
        }
        /* 关键：绝对定位铺满剩余高度，避免 SVG flex 高度塌陷 */
        #view-graph-edit .ge-board-box{
          position:relative;flex:1 1 auto;min-height:0;overflow:hidden;
          background:radial-gradient(circle at 30% 20%,rgba(15,118,110,.06),transparent 40%),var(--bg);
        }
        #view-graph-edit .ge-board{
          position:absolute;left:0;top:0;right:0;bottom:0;width:100%;height:100%;
          display:block;touch-action:none;
        }
        #view-graph-edit .ge-node circle.core{stroke-width:0}
        #view-graph-edit .ge-node.on circle.core{stroke:var(--brand);stroke-width:2.5}
        #view-graph-edit .ge-node.src circle.core{stroke:#0ea5e9;stroke-width:2.5;stroke-dasharray:4 3}
        #view-graph-edit .ge-node text.lab{
          fill:var(--text);font-size:11.5px;font-weight:500;pointer-events:none;
          dominant-baseline:central;
        }
        #view-graph-edit .ge-edge path.line{fill:none;stroke-width:2.2}
        #view-graph-edit .ge-edge path.hit{stroke:transparent;stroke-width:14;fill:none;cursor:pointer}
        #view-graph-edit .ge-edge text{fill:var(--text-3);font-size:10px;pointer-events:none}
      </style>`;

    this.leftTab = 'bank';
    this.sel = null;
    this.src = null;
    this.mode = 'select';
    this.cam = { x: 40, y: 40, k: 1 };
    this._bindShell();
    this.load();
  },

  _bindShell() {
    U.$('#geRefresh').addEventListener('click', () => this.load());
    U.$('#geSave').addEventListener('click', () => this.save());
    U.$('#geModeSelect').addEventListener('click', () => this.setMode('select'));
    U.$('#geModeConnect').addEventListener('click', () => this.setMode('connect'));
    U.$('#geDel').addEventListener('click', () => this.delSel());
    U.$('#geFit').addEventListener('click', () => this.fitView());
    U.$('#geRel').addEventListener('change', e => { this.rel = e.target.value; });
    if (this._ro) this._ro.disconnect();
    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(() => {
        if (this.data) this.draw();
      });
      const box = U.$('.ge-board-box', U.$('#view-graph-edit'));
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

  setMode(m) {
    this.mode = m;
    this.src = null;
    U.$('#geModeSelect').classList.toggle('on', m === 'select');
    U.$('#geModeConnect').classList.toggle('on', m === 'connect');
    U.$('#geHint').textContent = m === 'connect'
      ? '连线：先点起点圆点，再点终点；可切换关系类型'
      : '拖拽圆形节点调整位置；点击节点/边选中';
    this.draw();
  },

  load() {
    API.teacher.kpTopology().then(d => {
      this.data = d;
      this.sel = null;
      this.src = null;
      this.paintLeft();
      this.paintBanner();
      this.autoPlacePending();
      // 等 DOM 布局完成后再量画布尺寸并适配
      requestAnimationFrame(() => {
        this.fitView();
      });
    }).catch(err => Toast.error('加载图谱失败', (err && err.message) || ''));
  },

  /** 未布点 KP 按章网格摆放（相对已放置节点下方） */
  autoPlacePending() {
    if (!this.data) return;
    const nodes = this.data.nodes || [];
    const placed = nodes.filter(n => n.x != null && n.y != null);
    const pending = nodes.filter(n => n.x == null || n.y == null || !n.placed);
    // 已放置节点包围盒
    let baseY = 80;
    if (placed.length) {
      baseY = Math.max(...placed.map(n => n.y)) + 90;
    }
    let baseX = 80;
    pending.forEach((n, i) => {
      n.x = baseX + (i % 8) * 72;
      n.y = baseY + Math.floor(i / 8) * 72;
      n.placed = false;
      n._auto = true;
    });
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
    if (w < 20 || h < 20) {
      // 尺寸未就绪：延后再试
      setTimeout(() => this.fitView(), 50);
      return;
    }
    const pad = 56;
    const minX = Math.min(...nodes.map(n => n.x)) - 36;
    const maxX = Math.max(...nodes.map(n => n.x)) + 36;
    const minY = Math.min(...nodes.map(n => n.y)) - 36;
    const maxY = Math.max(...nodes.map(n => n.y)) + 36;
    const bw = Math.max(1, maxX - minX);
    const bh = Math.max(1, maxY - minY);
    const k = Math.min((w - pad * 2) / bw, (h - pad * 2) / bh, 1.6);
    this.cam.k = Math.max(0.35, k);
    this.cam.x = (w - bw * this.cam.k) / 2 - minX * this.cam.k;
    this.cam.y = (h - bh * this.cam.k) / 2 - minY * this.cam.k;
    this.draw();
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
          <div class="ge-item ${!n.placed ? '' : ''}" data-id="${n.id}" title="${!n.placed ? '待加入图谱' : '已在画布'}">
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
    // 视口居中
    const svg = U.$('#geBoard');
    if (svg) {
      const w = svg.clientWidth, h = svg.clientHeight;
      this.cam.x = w / 2 - n.x * this.cam.k;
      this.cam.y = h / 2 - n.y * this.cam.k;
      this.draw();
    }
  },

  _REL() {
    return {
      pre: { color: '#0284c7', label: '前置', dash: '' },
      advance: { color: '#7c3aed', label: '进阶', dash: '' },
      parallel: { color: '#64748b', label: '并列', dash: '7 5' },
    };
  },

  draw() {
    const board = U.$('#geBoard');
    if (!board || !this.data) return;
    this._bindBoardOnce();
    const rect = board.getBoundingClientRect();
    const w = Math.max(200, Math.floor(rect.width || board.clientWidth || 800));
    const h = Math.max(200, Math.floor(rect.height || board.clientHeight || 520));
    board.setAttribute('viewBox', `0 0 ${w} ${h}`);
    const nodes = (this.data.nodes || []).filter(n => n.x != null && n.y != null);
    const edges = this.data.edges || [];
    const REL = this._REL();

    let grid = '';
    const step = 28 * this.cam.k;
    if (step > 8) {
      for (let x = this.cam.x % step; x < w; x += step) grid += `M${x} 0 V${h}`;
      for (let y = this.cam.y % step; y < h; y += step) grid += `M0 ${y} H${w}`;
    }

    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    let eHtml = '';
    edges.forEach((e, i) => {
      const a = byId[e.source], b = byId[e.target];
      if (!a || !b) return;
      const r = REL[e.relation] || REL.pre;
      const g = this._edgeGeom(a, b);
      const on = this.sel && this.sel.type === 'edge' && this.sel.id === `${e.source}|${e.target}|${e.relation}`;
      eHtml += `<g class="ge-edge" data-edge="${i}">
        <path class="hit" d="${g.d}"/>
        <path class="line" d="${g.d}" stroke="${r.color}" stroke-dasharray="${r.dash}" marker-end="url(#ge-ar-${e.relation})"/>
        <text x="${g.lx}" y="${g.ly}" text-anchor="middle">${r.label}</text>
      </g>`;
    });

    let nHtml = '';
    nodes.forEach(n => {
      // 与学生端一致：小圆点 + 右侧标签；颜色按 category（已掌握/学习中…）
      const color = this.categoryColor(n.category);
      const on = this.sel && this.sel.type === 'node' && this.sel.id === n.id;
      const isSrc = this.src === n.id;
      const r = n.isKey ? 17 : 13;
      const label = (n.name || '').length > 10 ? (n.name || '').slice(0, 10) + '…' : (n.name || '');
      nHtml += `<g class="ge-node ${on ? 'on' : ''} ${isSrc ? 'src' : ''}" data-node="${n.id}" transform="translate(${n.x},${n.y})">
        <circle class="core" r="${r}" fill="${color}" ${n.isKey ? 'stroke="#f59e0b" stroke-width="2"' : 'stroke="transparent" stroke-width="0"'}/>
        <circle class="hit" r="${r + 8}" fill="transparent"/>
        <text class="lab" x="${r + 8}" y="0" text-anchor="start">${U.esc(label)}</text>
      </g>`;
    });

    let markers = Object.keys(REL).map(k => `
      <marker id="ge-ar-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10z" fill="${REL[k].color}"/>
      </marker>`).join('');

    board.innerHTML = `<defs>${markers}</defs>
      <path d="${grid}" stroke="rgba(100,116,139,.12)" stroke-width="1" fill="none"/>
      <g transform="translate(${this.cam.x},${this.cam.y}) scale(${this.cam.k})">
        <g>${eHtml}</g><g>${nHtml}</g>
      </g>`;
    this._bindBoard(board);
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
    const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2 - Math.min(36, len * 0.15);
    return { d: `M${p1.x} ${p1.y} Q${mx} ${my} ${p2.x} ${p2.y}`, lx: mx, ly: my - 4 };
  },

  _toWorld(e) {
    const r = U.$('#geBoard').getBoundingClientRect();
    return {
      x: (e.clientX - r.left - this.cam.x) / this.cam.k,
      y: (e.clientY - r.top - this.cam.y) / this.cam.k,
    };
  },

  _bindBoard(board) {
    board.querySelectorAll('[data-node]').forEach(el => {
      el.addEventListener('pointerdown', ev => {
        ev.stopPropagation();
        const id = el.dataset.node;
        const n = (this.data.nodes || []).find(x => x.id === id);
        if (!n) return;
        if (this.mode === 'connect') {
          if (!this.src) {
            this.src = id;
            this.sel = { type: 'node', id };
            this.draw();
            Toast.info('已选起点', '请点击终点节点');
            return;
          }
          if (this.src === id) { this.src = null; this.draw(); return; }
          const exists = (this.data.edges || []).some(e =>
            e.source === this.src && e.target === id && e.relation === this.rel);
          if (exists) { Toast.warn('两点之间已有该类型连线'); this.src = null; this.draw(); return; }
          this.data.edges.push({ source: this.src, target: id, relation: this.rel });
          this.src = null;
          this.draw();
          Toast.ok('已连线', this.rel);
          return;
        }
        this.sel = { type: 'node', id };
        const w = this._toWorld(ev);
        this._drag = { id, ox: w.x - n.x, oy: w.y - n.y };
        el.setPointerCapture(ev.pointerId);
        this.draw();
      });
      el.addEventListener('pointermove', ev => {
        if (!this._drag || this._drag.id !== el.dataset.node) return;
        const n = (this.data.nodes || []).find(x => x.id === this._drag.id);
        if (!n) return;
        const w = this._toWorld(ev);
        n.x = w.x - this._drag.ox;
        n.y = w.y - this._drag.oy;
        n._auto = false;
        this.draw();
      });
      el.addEventListener('pointerup', () => { this._drag = null; });
    });
    board.querySelectorAll('[data-edge]').forEach(el => {
      el.addEventListener('pointerdown', ev => {
        ev.stopPropagation();
        if (this.mode !== 'select') return;
        const idx = Number(el.dataset.edge);
        const e = this.data.edges[idx];
        if (!e) return;
        this.sel = { type: 'edge', id: `${e.source}|${e.target}|${e.relation}` };
        this._edgeIdx = idx;
        this.draw();
      });
    });
  },

  _bindBoardOnce() {
    const board = U.$('#geBoard');
    if (!board || board._geBound) return;
    board._geBound = true;
    board.addEventListener('pointerdown', ev => {
      const t = ev.target;
      if (t === board || t.tagName === 'path') {
        this._pan = { x: ev.clientX - this.cam.x, y: ev.clientY - this.cam.y };
        board.setPointerCapture(ev.pointerId);
        this.sel = null;
        this.src = null;
        this.draw();
      }
    });
    board.addEventListener('pointermove', ev => {
      if (this._pan) {
        this.cam.x = ev.clientX - this._pan.x;
        this.cam.y = ev.clientY - this._pan.y;
        this.draw();
      }
    });
    board.addEventListener('pointerup', () => { this._pan = null; });
    board.addEventListener('wheel', ev => {
      ev.preventDefault();
      const r = board.getBoundingClientRect();
      const mx = ev.clientX - r.left, my = ev.clientY - r.top;
      const wx = (mx - this.cam.x) / this.cam.k, wy = (my - this.cam.y) / this.cam.k;
      const f = ev.deltaY > 0 ? 0.93 : 1.08;
      this.cam.k = Math.min(2.2, Math.max(0.5, this.cam.k * f));
      this.cam.x = mx - wx * this.cam.k;
      this.cam.y = my - wy * this.cam.k;
      this.draw();
    }, { passive: false });
  },

  delSel() {
    if (!this.sel) { Toast.warn('请先选中节点或边'); return; }
    if (this.sel.type === 'node') {
      // 仅取消布点位置，不从目录删除 KP
      const n = (this.data.nodes || []).find(x => x.id === this.sel.id);
      if (n) { n.x = null; n.y = null; n.placed = false; }
      this.data.edges = (this.data.edges || []).filter(e => e.source !== this.sel.id && e.target !== this.sel.id);
      Toast.ok('已移出画布', '知识点仍保留在课程目录');
    } else if (this._edgeIdx != null) {
      this.data.edges.splice(this._edgeIdx, 1);
      this._edgeIdx = null;
      Toast.ok('已删除连线');
    }
    this.sel = null;
    this.paintBanner();
    this.paintLeft();
    this.draw();
  },

  save() {
    const nodes = (this.data.nodes || [])
      .filter(n => n.x != null && n.y != null)
      .map(n => ({ id: n.id, x: n.x, y: n.y }));
    const edges = (this.data.edges || []).map(e => ({
      source: e.source, target: e.target, relation: e.relation,
    }));
    API.teacher.saveKpTopology({ nodes, edges }).then(r => {
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
    // 首次进入后再绑画布容器事件（draw 前需 DOM）
    setTimeout(() => TeacherGraphEdit._bindBoardOnce(), 0);
  },
});
