/* ==========================================================================
   课程智能体系统 · 图表工厂（基于 ECharts 5）
   所有图表随主题自动重绘，颜色取自 CSS 变量
   ========================================================================== */
const Charts = (function () {

  const store = new Map();   // el -> { instance, builder }
  // 图谱「松手」兜底监听的当前处理器：图表重建时先摘掉旧的，避免重复绑定
  // （zrender 的鼠标释放多数情况已能收到，这里只兜底画布外释放）
  let graphWinUp = null;

  function cssVar(n) {
    return getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  }

  function tokens() {
    return {
      text: cssVar('--text'),
      text2: cssVar('--text-2'),
      dim: cssVar('--chart-axis'),
      split: cssVar('--chart-split'),
      surface: cssVar('--surface'),
      surface2: cssVar('--surface-2'),
      surface3: cssVar('--surface-3'),
      border: cssVar('--border'),
      brand: cssVar('--brand-500') || '#6366f1',
      accent: cssVar('--accent-500') || '#8b5cf6',
      ok: cssVar('--ok') || '#22c55e',
      warn: cssVar('--warn') || '#f59e0b',
      danger: cssVar('--danger') || '#ef4444',
      info: cssVar('--info') || '#38bdf8',
      // 图谱关系配色：统一取自 refresh.css 的 --rel-*，
      // 与教师端图谱编排共用同一套变量，杜绝两端颜色漂移
      relPre: cssVar('--rel-pre') || '#0d9488',
      relAdvance: cssVar('--rel-advance') || '#a21caf',
      relParallel: cssVar('--rel-parallel') || '#718793',
      relSplit: cssVar('--rel-split') || '#a21caf',
      relMap: cssVar('--rel-map') || '#2f7fc1',
      relError: cssVar('--rel-error') || '#dc4f58',
      relSupport: cssVar('--rel-support') || '#2f7fc1'
    };
  }

  /** 关系类型 → 颜色 / 名称（集中一处，图表与图例复用） */
  function relPalette(t) {
    return {
      color: {
        pre: t.relPre, advance: t.relAdvance, parallel: t.relParallel,
        split: t.relSplit, map: t.relMap, error: t.relError, support: t.relSupport
      },
      name: { pre: '前置', advance: '进阶', parallel: '并列', split: '拆解', map: '映射', error: '错题', support: '支撑' }
    };
  }

  // SPA 切换、卡片布局变化或字体加载完成后，图表容器的尺寸可能还会继续变化。
  // 监听容器尺寸，避免 ECharts 按初始的窄尺寸完成布局后一直挤在左上角。
  function watchSize(el, inst) {
    const resize = () => {
      if (!inst || (inst.isDisposed && inst.isDisposed())) return;
      inst.resize();
    };

    requestAnimationFrame(resize);
    setTimeout(resize, 60);
    setTimeout(resize, 240);

    if (typeof ResizeObserver === 'undefined') return null;
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    return observer;
  }

  function baseTooltip(t) {
    return {
      backgroundColor: t.surface,
      borderColor: t.border,
      borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12 },
      extraCssText: 'box-shadow:0 8px 28px rgba(0,0,0,.3);border-radius:8px;padding:9px 12px;'
    };
  }

  /** 渲染并登记（主题切换后自动重绘）
   *  onClick / onReady 会随实例一起登记：redrawAll() 重建实例时会自动重新绑定，
   *  否则任何一次主题重绘（页面加载时的 themechange 也算）都会让图表点击/悬停失效。 */
  function render(sel, builder, onClick, onReady) {
    const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (!el || !window.echarts) return null;
    let rec = store.get(el);
    if (rec && rec.observer) rec.observer.disconnect();
    if (rec && rec.instance) rec.instance.dispose();
    const inst = echarts.init(el, null, { renderer: 'canvas' });
    inst.setOption(builder(tokens()), true);
    if (onClick) inst.on('click', onClick);
    const next = { instance: inst, builder, onClick: onClick || null, onReady: onReady || null, observer: null };
    store.set(el, next);
    if (onReady) onReady(inst);
    next.observer = watchSize(el, inst);
    return inst;
  }

  function resizeAll() { store.forEach(r => r.instance && r.instance.resize()); }
  function redrawAll() {
    store.forEach((r, el) => {
      if (!document.body.contains(el)) {
        if (r.observer) r.observer.disconnect();
        if (r.instance) r.instance.dispose();
        store.delete(el);
        return;
      }
      if (r.observer) r.observer.disconnect();
      r.instance.dispose();
      const inst = echarts.init(el, null, { renderer: 'canvas' });
      inst.setOption(r.builder(tokens()), true);
      if (r.onClick) inst.on('click', r.onClick);   // 重建后必须重绑，否则点击处理器随旧实例一起消失
      const next = { instance: inst, builder: r.builder, onClick: r.onClick || null, onReady: r.onReady || null, observer: null };
      store.set(el, next);
      if (r.onReady) r.onReady(inst);               // 悬停等非 click 事件同样要重绑并恢复当前状态
      next.observer = watchSize(el, inst);
    });
  }
  window.addEventListener('resize', resizeAll);
  window.addEventListener('themechange', () => setTimeout(redrawAll, 60));

  /* ============ 视图冻结：几何变了，用户看到的视图不许跟着变 ============
     背景（实测 echarts 5.5.1，无头 Chrome 量 convertToPixel）：
     graph 系列在**每一次 setOption** 都会按「节点包围盒 → 视图矩形」重建一次 View
     坐标系，适配倍率 = min(视口/包围盒)。所以只要节点坐标变了（拖拽落点回写 option、
     撤回/重做、增删节点），整图的缩放比例就会跟着变：
       · 学生端把某节点外移 (+120,-200)：像素/数据单位 1.003 → 0.782（整图缩小 22%）
       · 教师端同一操作：0.883 → 0.914；再移一个节点：0.883 → 0.719
     用户看到的就是「移动后界面的比例异常缩小/放大」。

     所以凡「改节点坐标」的 setOption 都必须配一对 keep/restore：
       const keep = Charts.viewMetrics(chart);   // ① 改几何前量
       chart.setOption({ series: [{ data: ... }] });  // ② 改几何（视图会被重新适配）
       Charts.restoreView(chart, keep);          // ③ 把比例/平移补偿回去

     补偿原理：视图 = 适配倍率 × zoom，且实测「center 每 +1 数据单位 → 原点像素 -S」
     （S = 当前每数据单位像素）。故 ①按比例反算 zoom，②残余平移 Δcenter = -ΔO/S。
     通常一次 setOption 即精确到 0px；为防 ECharts 内部 setCenter/setZoom 的先后
     副作用，这里最多再迭代一次做兜底。
     注意：本流程是「保住用户当前视图」，**有意**改视图的操作（fitView/聚焦节点）
     必须先改视图、再走本流程，顺序反了会被一起冻掉。 */

  /** 量当前视图：S = 每数据单位像素；O = 数据原点 [0,0] 的像素；zoom = 当前缩放 */
  function viewMetrics(chart) {
    if (!chart || (chart.isDisposed && chart.isDisposed())) return null;
    try {
      const o = chart.convertToPixel({ seriesIndex: 0 }, [0, 0]);
      const ax = chart.convertToPixel({ seriesIndex: 0 }, [100, 0]);
      const ay = chart.convertToPixel({ seriesIndex: 0 }, [0, 100]);
      if (!o || !ax || !ay) return null;
      const s = (ax[0] - o[0]) / 100;
      if (!isFinite(s) || s <= 0 || !isFinite(o[0]) || !isFinite(o[1])) return null;
      const cs = chart.getModel().getSeriesByIndex(0).coordinateSystem;
      let z = cs && cs.getZoom ? cs.getZoom() : chart.getOption().series[0].zoom;
      z = Number(z);
      return { s, ox: o[0], oy: o[1], zoom: (isFinite(z) && z) ? z : 1 };
    } catch (e) { return null; }
  }

  /** 把视图还原到 keep 时的样子（几何已变），见上方「视图冻结」说明 */
  function restoreView(chart, keep, seriesRef) {
    if (!chart || !keep) return;
    const ref = seriesRef || {};
    for (let i = 0; i < 2; i++) {
      const now = viewMetrics(chart);
      if (!now) return;
      const k = now.s > 0 ? keep.s / now.s : 1;
      const dx = keep.ox - now.ox, dy = keep.oy - now.oy;
      const needZoom = Math.abs(k - 1) > 0.0005;
      const needShift = Math.hypot(dx, dy) > 1;
      if (!needZoom && !needShift) return;              // 已冻结，无需再动
      const patch = {};
      let zoom = now.zoom;
      if (needZoom) { zoom = now.zoom * k; patch.zoom = zoom; }
      if (needShift) {
        const c = currentViewCenter(chart) || [0, 0];
        // 补偿后每数据单位像素（center→像素 系数即 -S）
        const sAfter = now.s * (zoom / now.zoom);
        patch.center = [c[0] - dx / sAfter, c[1] - dy / sAfter];
      }
      chart.setOption({ series: [Object.assign({}, ref, patch)] });
    }
  }

  /** 当前视图中心（钉在视口中心的数据坐标）；未显式设置时返回包围盒中心 */
  function currentViewCenter(chart) {
    try {
      const cs = chart.getModel().getSeriesByIndex(0).coordinateSystem;
      if (cs && typeof cs.getCenter === 'function') {
        const c = cs.getCenter();
        if (c && isFinite(c[0]) && isFinite(c[1])) return c;
      }
    } catch (e) {}
    return null;
  }

  /* ================= 1. 三大图谱（力导向关系图） ================= */
  function graph(sel, data, onClick) {
    // 关系标签默认隐藏：只有「悬停」或「选中」某个节点时，才显示与该节点相连的那些边
    // 的关系标签（前置/进阶/并列…），避免标签压在节点上、多条关系挤在一起看不清。
    //
    // 为什么不用 ECharts 的 emphasis/select 状态：实测本仓库的 echarts 5.5.1
    // 对 graph 的边标签状态解析不生效 —— series.emphasis.edgeLabel /
    // select.edgeLabel 在「高亮节点 / 高亮边 / 真实 mousemove」三种触发下
    // 都不改变边标签（links[].label.show=false 时标签元素根本不创建）。
    // 因此改为「增量 setOption(只传 links)」切换：
    // 实测两种布局（none / force）下节点坐标逐次完全一致、roam 视图与 zoom 不被重置，
    // 因为 setOption 不传 center/zoom，且节点数组原样未动。
    // ⚠ 但这个「不被重置」的前提是**节点坐标没变**：一旦 setOption 里带了新的
    //   data[].x/y，视图就会被按新包围盒重新适配 → 见下方「视图冻结」。
    const rel = relPalette(tokens());
    const REL_REL = rel.name, REL_COLOR = rel.color;

    let hoverIdx = -1;      // 鼠标悬停的节点下标
    let hoverEdgeIdx = -1;  // 鼠标悬停的边下标（-1 = 无）
    let pinnedIdx = -1;     // 点击选中的节点下标（移开鼠标后仍保持）
    let applied = null;     // 已写入的可见边签名，避免重复 setOption
    let chart = null;
    let pressing = false;   // 画布按压/拖拽中：期间一律不做悬停驱动的增量刷新（见 sync）
    let hiddenCats = new Set();   // 「区分」：被隐藏的知识点类别（按类别名）。用透明度隐藏而非移除，
                                  // 避免 ECharts 因节点集合变化触发非均匀重排（实测移除式隐藏会位移 ~150px）。

    /** 关系边选项；showSet = 需要显示标签的边下标集合 */
    const buildLinks = (t, showSet) => {
      // 隐藏类节点的连线一并隐藏（透明度），避免悬空连线
      const hiddenIds = new Set();
      data.nodes.forEach(n => {
        const cn = (data.categories[n.category] || {}).name;
        if (hiddenCats.has(cn)) hiddenIds.add(n.id != null ? n.id : n.name);
      });
      return data.links.map((l, i) => {
        const lc = REL_COLOR[l.relation] || t.dim;
        const hide = hiddenIds.has(l.source) || hiddenIds.has(l.target);
        return {
          source: l.source, target: l.target, relation: l.relation,
          // 并列 = 双向并列关系 → 两端都画箭头（与教师端图谱编排一致）
          symbol: l.relation === 'parallel' ? ['arrow', 'arrow'] : ['none', 'arrow'],
          // 连线关系文字 chip（前置/进阶/并列/拆解…），按关系着色；opacity:1 抵消继承的半透明
          label: {
            show: !hide && showSet.has(i), formatter: () => REL_REL[l.relation] || '',
            fontSize: 11, opacity: 1,
            color: lc, backgroundColor: t.surface,
            borderColor: lc, borderWidth: 1, borderRadius: 6, padding: [2, 6]
          },
          lineStyle: {
            color: lc,
            width: l.relation === 'pre' ? 1.5 : 0.9,
            curveness: 0.14,
            opacity: hide ? 0 : 0.62,
            type: l.relation === 'parallel' ? 'dashed' : 'solid'
          }
        };
      });
    };

    /** 与第 i 个节点相连的边下标集合（节点 id 优先，缺 id 时退回 name） */
    const adjacentEdges = (i) => {
      const set = new Set();
      const n = data.nodes[i];
      if (!n) return set;
      const key = n.id != null ? n.id : n.name;
      data.links.forEach((l, k) => { if (l.source === key || l.target === key) set.add(k); });
      return set;
    };

    /** 当前该显示标签的边集合：悬停节点 > 悬停边 > 选中节点 */
    const activeEdges = () => {
      if (hoverIdx >= 0) return adjacentEdges(hoverIdx);
      if (hoverEdgeIdx >= 0) return new Set([hoverEdgeIdx]);
      if (pinnedIdx >= 0) return adjacentEdges(pinnedIdx);
      return new Set();
    };

    const sync = () => {
      if (!chart) return;
      // 拖拽/平移中不刷新关系标签 —— 这是「节点滑动不丝滑」的根因（实测）：
      // 拖拽期间 zrender 仍会派发 mouseout/mouseover（光标掠过别的节点、连线），
      // 每次都走到这里 → setOption(links)。而 ECharts 的每一次 setOption 都要
      // 重跑静态布局 + 整套 update 动画（animationDurationUpdate: 420）+ 标签防重叠重排，
      // 一次 20 步的拖拽实测被打断 5~7 次 → 掉帧、节点跟手发飘。
      // 松手后再按落点补一次（见 onReady 的 finishDrag），标签状态不会丢。
      if (pressing) return;
      const set = activeEdges();
      const sig = [...set].sort((a, b) => a - b).join(',');
      if (sig === applied) return;
      applied = sig;
      chart.setOption({ series: [{ links: buildLinks(tokens(), set) }] });
    };

    const isKnowledge = data.graphType === 'knowledge';
    // 教师已布点 → 静态坐标（layout:'none'）。此时节点坐标是「教师编排结果」，
    // 只读展示；学生可临时拖动看清局部，再用「重置视图」还原。
    const staticLayout = isKnowledge && data.nodes.some(n => n.x != null && n.y != null);

    /**
     * 节点选项数组 —— **唯一**的节点构造入口。
     * 首次渲染（builder）与「拖拽后回写坐标」都必须走它：两者若各写一份，
     * option 里的 x/y 就会与 data.nodes 漂移，见 onReady 里 zr 'mouseup' 的注释。
     */
    const buildNodes = (t) => data.nodes.map(n => {
      // 颜色随节点状态（category 下标）取；越界时退回「未开始」的灰，避免白屏
      const cat = data.categories[n.category] || data.categories[3] || { color: t.dim };
      const color = cat.color;
      const val = n.mastery !== undefined ? n.mastery : (n.achieve !== undefined ? n.achieve : 60);
      // 「区分」：被隐藏类别的节点整体透明。节点仍保留在布局中（集合不变），ECharts 不会重排，
      // 因此隐藏/恢复都不会让其它节点位置漂移（修复点击图例恢复时整图位移 ~150px 的 bug）。
      const hidden = hiddenCats.has((data.categories[n.category] || {}).name);
      const item = Object.assign({}, n, {
        value: val,
        symbolSize: n.category === 0 && !isKnowledge ? 46 : (n.isKey ? 34 : 26),
        label: { show: (!isKnowledge || n.isKey || n.category === 0 || n.category === 4) && !hidden },
        // 节点标签防重叠放在「节点」上（而不是 series.labelLayout）：
        // series 级会把连线关系标签也卷进 LabelManager，导致「前置/进阶…」丢失
        // graph 视图组平移而错位到画布原点。逐节点配置即可只作用于节点标签。
        labelLayout: { hideOverlap: true, moveOverlap: 'shiftY' },
        category: n.category,
        silent: hidden,
        itemStyle: {
          color,
          // ⚠️ 隐藏必须写进 itemStyle.opacity：数据项顶层 opacity 会被模型接受
          // （getItemModel().get('opacity')===0）但**不参与渲染**（像素取证实测节点原样画出）
          opacity: hidden ? 0 : 1,
          borderColor: n.isKey ? t.warn : 'transparent',
          borderWidth: n.isKey ? 2 : 0,
          shadowBlur: 12, shadowColor: color + '55'
        }
      });
      // 有教师坐标时写入 ECharts 坐标（layout:none）
      if (n.x != null && n.y != null) {
        item.x = n.x;
        item.y = n.y;
        item.fixed = true;
      }
      return item;
    });

    return render(sel, (t) => {
      const catColors = data.categories.map(c => c.color);

      return {
        tooltip: Object.assign(baseTooltip(t), {
          formatter(p) {
            if (p.dataType === 'edge') {
              return `<b>${REL_REL[p.data.relation] || '关联'}关系</b><br/>${p.data.source} → ${p.data.target}`;
            }
            const d = p.data;
            let html = `<b style="font-size:13px">${d.name}</b>`;
            if (d.mastery !== undefined) {
              html += `<br/>学习完成率：<b style="color:${d.itemStyle.color}">${d.mastery}%</b>`;
              html += `<br/>难度：${'★'.repeat(d.difficulty || 0)}`;
              html += `<br/>学时：${d.hours || 0} 学时`;
              if (d.isKey) html += `<br/><span style="color:${t.warn}">◆ 重难点</span>`;
            }
            if (d.achieve !== undefined) html += `<br/>达成度：<b>${d.achieve}%</b><br/>权重：${d.weight}%`;
            if (d.errorRate !== undefined) html += `<br/>错误率：<b style="color:${t.danger}">${d.errorRate}%</b><br/>关联知识点：${d.relatedKp} 个`;
            if (d.count !== undefined) html += `<br/>累计错题：<b>${d.count}</b> 人次`;
            return html + `<br/><span style="color:${t.dim};font-size:11px">点击查看详情</span>`;
          }
        }),
        // 分类「区分」不再用 ECharts 原生图例：其隐藏会**移除节点**、触发 graph 系列非均匀重排
        // （实测恢复显示时参考节点位移 ~150px）。改为我们自己的透明度分类隐藏控件（见 onReady
        // 内的 mountCatChips）：节点集合不变、仅 opacity 变化，ECharts 不会重排，位置零漂移。
        legend: { show: false },
        animation: true,
        animationDuration: 680,
        animationEasing: 'cubicOut',
        animationDurationUpdate: 420,
        series: [{
          type: 'graph',
          // 教师已布点则用静态坐标（无弹力）；否则退回力导向但关闭布局动画
          layout: staticLayout ? 'none' : 'force',
          roam: true,
          // 允许拖动微调（配合「重置视图」）。拖拽结果必须回写 data.nodes，
          // 否则下一次增量 setOption 会把节点弹回原位 —— 见 onReady 里的说明。
          draggable: true,
          zoom: isKnowledge ? 0.92 : 1,
          categories: data.categories.map(c => ({ name: c.name, itemStyle: { color: c.color } })),
          force: {
            repulsion: isKnowledge ? 340 : 420,
            edgeLength: isKnowledge ? [70, 150] : [90, 180],
            gravity: 0.09,
            friction: 0.6,
            layoutAnimation: false
          },
          label: {
            show: !isKnowledge, position: 'bottom', distance: 8, color: t.text, fontSize: 11.5,
            backgroundColor: t.surface, borderColor: t.border, borderWidth: 1, borderRadius: 4, padding: [2, 5],
            formatter: (p) => p.data.name.length > 10 ? p.data.name.slice(0, 10) + '…' : p.data.name
          },
          // 注意：series.labelLayout 会把连线（edge）标签也纳入 LabelManager 接管，
          // 导致关系标签丢失 graph 视图组的平移而错位到画布原点，故改为逐节点配置（见下方 data.labelLayout）

          emphasis: {
            focus: 'adjacency',
            scale: 1.08,
            label: { show: true, fontSize: 12.5, fontWeight: 'bold' },
            lineStyle: { width: 2.3 }
          },
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: 5.5,
          data: buildNodes(t),
          links: buildLinks(t, activeEdges())
        }]
      };
    }, (p) => {
      // 点击节点 = 选中：常亮该节点的相连关系标签；再点一次取消
      if (p.dataType !== 'node') return;
      pinnedIdx = pinnedIdx === p.dataIndex ? -1 : p.dataIndex;
      hoverIdx = -1;
      sync();
      if (onClick) onClick(p.data);
    }, (inst) => {
      chart = inst;
      applied = null;   // 新实例：builder 已按当前状态渲染，这里补一次以保证签名同步
      const edgeOffset = data.nodes.length;   // graph 的 dataIndex：节点在前，边在后
      inst.on('mouseover', (p) => {
        if (p.dataType === 'node') { hoverIdx = p.dataIndex; hoverEdgeIdx = -1; sync(); }
        else if (p.dataType === 'edge') { hoverEdgeIdx = p.dataIndex - edgeOffset; sync(); }
      });
      inst.on('mouseout', (p) => {
        if (p.dataType === 'node' && hoverIdx === p.dataIndex) { hoverIdx = -1; sync(); }
        else if (p.dataType === 'edge' && hoverEdgeIdx === p.dataIndex - edgeOffset) { hoverEdgeIdx = -1; sync(); }
      });
      inst.on('globalout', () => { hoverIdx = -1; hoverEdgeIdx = -1; sync(); });
      // 拖拽收尾：ECharts 原生拖拽只把新坐标写进**内部 itemLayout**，option 里的
      // data[].x/y 与 data.nodes 都还是旧值。而 graph(layout:'none') 在**每一次
      // setOption** 都会按 option 里的 x/y 重跑静态布局 —— 于是松手后任何一次
      // 增量刷新（悬停/点击刷关系标签）都会把节点弹回原位，表现为「能拖但固定不住」。
      // 所以拖完立刻把当前坐标回写 data.nodes + option，让三者恒等。
      const zr = inst.getZr();
      zr.on('mousedown', () => { pressing = true; });   // 拖拽/平移开始：冻结标签刷新
      const finishDrag = () => {
        if (!pressing) return;
        pressing = false;
        // 拖拽期间被压制的标签刷新，在落点重算一次（否则标签停在拖动前的节点上）
        applied = null;
        if (staticLayout) {
          let sData = null;
          try { sData = inst.getModel().getSeriesByIndex(0).getData(); } catch (e) { sData = null; }
          if (sData) {
            const keep = viewMetrics(inst);   // 必须在改几何之前量（见文件内「视图冻结」说明）
            let moved = false;
            data.nodes.forEach((n, i) => {
              let l = null;
              try { l = sData.getItemLayout(i); } catch (e) {}
              if (!l || !isFinite(l[0]) || !isFinite(l[1])) return;
              if (n.x == null || n.y == null || Math.abs(n.x - l[0]) > 0.01 || Math.abs(n.y - l[1]) > 0.01) {
                n.x = l[0]; n.y = l[1]; n.fixed = true; moved = true;
              }
            });
            if (moved) {
              // 坐标 + 标签合成同一次 setOption：松手时少跑一整轮更新管线，手感更利落。
              //
              // ⚠️ 视图冻结（为什么这么绕）：graph(layout:'none') 在**每一次 setOption
              // 都按新包围盒 re-fit** 整图比例与居中。所以拖拽落点一旦回写 option，
              // 整图缩放会被重新适配（实测 zoom 0.92→1.0187、整图明显跳动、用户看到「节点乱跑」）。
              //
              // 补偿要点：
              //   · 单独的 `setOption({zoom,center})` 会被 ECharts 二次 re-fit 覆盖、根本不生效，
              //     必须把 zoom/center **和 data 放进同一份 setOption** 才会被采用；
              //   · 但 re-fit 后每数据单位像素 s 已变成新值（fit 因子随包围盒变了），
              //     若直接把旧 zoom 传回去，比例仍会差一截（实测约 6px 漂移）。
              //     所以先「只改几何」re-fit 一次、量出新 s，再按 k=keep.s/now.s 反算该传的 zoom，
              //     连同 data 一起提交（第二次 setOption 包围盒不变，fit 因子不变，比例精确还原）。
              let center = null;
              try { const cs = inst.getModel().getSeriesByIndex(0).coordinateSystem; if (cs && cs.getCenter) center = cs.getCenter(); } catch (e) {}
              const t = tokens();
              const set = activeEdges();
              applied = [...set].sort((a, b) => a - b).join(',');
              // ① 只改几何 → re-fit（zoom 仍是 option 里的旧值，用于反算）
              inst.setOption({ series: [{ data: buildNodes(t), links: buildLinks(t, set) }] });
              const now = viewMetrics(inst);
              const z = (keep && now && now.s > 0) ? keep.zoom * (keep.s / now.s) : (keep ? keep.zoom : 1);
              // ② 把「按比例反算的 zoom」+ 拖拽前的 center 与 data 一起提交 → 视图精确冻结
              const viewPatch = (keep && center) ? { zoom: z, center: [center[0], center[1]] } : {};
              inst.setOption({ series: [{ data: buildNodes(t), links: buildLinks(t, set), ...viewPatch }] });
              return;
            }
          }
        }
        sync();
      };
      zr.on('mouseup', finishDrag);
      // 「区分」分类隐藏：用透明度隐藏，而非 ECharts 原生「移除节点」。
      // 原因：原生图例隐藏会把节点从图集中移除，触发 graph 系列非均匀重排（实测恢复显示时
      // 参考节点位移 ~150px）；而只改 opacity（节点集合不变）ECharts 不会重排，故再次点击
      // 恢复时位置零漂移。连线的隐藏也在 buildLinks 里随类别一并透明。
      const applyHidden = () => {
        const keep = viewMetrics(inst);
        inst.setOption({ series: [{ data: buildNodes(tokens()), links: buildLinks(tokens(), activeEdges()) }] });
        if (keep) restoreView(inst, keep);   // 防御性冻结（opacity 变更本不触发重排，零成本保险）
      };
      (function mountCatChips() {
        const styleId = 'graph-cat-chips-style';
        if (!document.getElementById(styleId)) {
          const st = document.createElement('style');
          st.id = styleId;
          st.textContent = '.graph-cat-chips{position:absolute;top:10px;right:12px;z-index:6;display:flex;flex-wrap:wrap;gap:6px;max-width:62%;justify-content:flex-end}' +
            '.graph-cat-chips .cat-chip{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border:1px solid var(--border);border-radius:999px;background:var(--surface);color:var(--text-2);font-size:11.5px;line-height:1.6;cursor:pointer;transition:border-color .15s,color .15s,opacity .15s}' +
            '.graph-cat-chips .cat-chip:hover{border-color:var(--brand);color:var(--text)}' +
            '.graph-cat-chips .cat-chip.is-off{opacity:.4;text-decoration:line-through}' +
            '.graph-cat-chips .cat-dot{width:9px;height:9px;border-radius:50%;flex:none}';
          document.head.appendChild(st);
        }
        const box = inst.getDom();
        if (!box) return;
        const old = box.querySelector('.graph-cat-chips');
        if (old) old.remove();
        const bar = document.createElement('div');
        bar.className = 'graph-cat-chips';
        bar.innerHTML = (data.categories || []).map((c, i) =>
          `<button type="button" class="cat-chip${hiddenCats.has(c.name) ? ' is-off' : ''}" data-cat="${i}">` +
          `<i class="cat-dot" style="background:${c.color}"></i><span>${c.name}</span></button>`).join('');
        box.appendChild(bar);
        bar.querySelectorAll('.cat-chip').forEach(btn => {
          btn.addEventListener('click', () => {
            const c = data.categories[+btn.dataset.cat];
            if (!c) return;
            if (hiddenCats.has(c.name)) hiddenCats.delete(c.name); else hiddenCats.add(c.name);
            btn.classList.toggle('is-off', hiddenCats.has(c.name));
            applyHidden();
          });
        });
      })();
      // 画布外释放兜底：万一 zrender 的指针捕获没覆盖到（如拖到画布外的 UI 上释放），
      // 也要把 pressing 复位，否则之后悬停再也不刷新关系标签。
      if (graphWinUp) window.removeEventListener('mouseup', graphWinUp);
      graphWinUp = () => { if (pressing) finishDrag(); };
      window.addEventListener('mouseup', graphWinUp);
      sync();
    });
  }

  /* ================= 2. 能力雷达图 ================= */
  function radar(sel, data) {
    return render(sel, (t) => ({
      tooltip: baseTooltip(t),
      legend: { bottom: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 12, itemHeight: 8, itemGap: 16 },
      radar: {
        indicator: data.indicators,
        center: ['50%', '46%'], radius: '62%',
        axisName: { color: t.text2, fontSize: 11.5 },
        splitLine: { lineStyle: { color: t.split } },
        splitArea: { areaStyle: { color: ['transparent', 'rgba(99,102,241,.035)'] } },
        axisLine: { lineStyle: { color: t.split } }
      },
      series: [{
        type: 'radar', symbolSize: 4,
        data: data.series.map((s, i) => {
          const colors = [t.brand, t.dim, t.warn];
          return {
            name: s.name, value: s.data,
            lineStyle: { width: i === 0 ? 2.4 : 1.6, color: colors[i], type: i === 2 ? 'dashed' : 'solid' },
            itemStyle: { color: colors[i] },
            areaStyle: i === 0 ? { color: colors[i] + '33' } : (i === 1 ? { color: colors[i] + '18' } : undefined)
          };
        })
      }]
    }));
  }

  /* ================= 3. 成长轨迹 / 趋势折线 ================= */
  function line(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.split } } }),
      legend: { top: 0, right: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 14, itemHeight: 8 },
      grid: { left: o.yAxes ? 18 : 4, right: o.yAxes ? 30 : 8, top: 36, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category', data: data.xAxis, boundaryGap: false,
        axisLine: { lineStyle: { color: t.split } },
        axisTick: { show: false },
        axisLabel: { color: t.dim, fontSize: 11 }
      },
      yAxis: o.yAxes ? o.yAxes.map((axis, i) => ({
        type: 'value',
        min: axis.min !== undefined ? axis.min : 0,
        max: axis.max,
        interval: axis.interval,
        name: axis.name || '',
        nameLocation: 'end',
        nameGap: 8,
        position: axis.position || (i === 0 ? 'left' : 'right'),
        axisLine: { show: !!axis.color, lineStyle: { color: axis.color || t.split } },
        axisTick: { show: false },
        splitLine: { show: i === 0, lineStyle: { color: t.split, type: 'dashed' } },
        nameTextStyle: { color: axis.color || t.dim, fontSize: 10 },
        axisLabel: { color: axis.color || t.dim, fontSize: 11, formatter: axis.fmt || '{value}' }
      })) : {
        type: 'value', min: o.min !== undefined ? o.min : 0, max: o.max,
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: t.split, type: 'dashed' } },
        axisLabel: { color: t.dim, fontSize: 11, formatter: o.fmt || '{value}' }
      },
      series: data.series.map(s => ({
        name: s.name, type: 'line', data: s.data, yAxisIndex: s.yAxisIndex || 0, smooth: true,
        symbol: 'circle', symbolSize: 6,
        // 可选的数值展示格式化（如时长 series 用 分'秒''）
        tooltip: s.valueFormatter ? { valueFormatter: s.valueFormatter } : undefined,
        lineStyle: { width: 2.4, color: s.color, type: s.dashed ? 'dashed' : 'solid' },
        itemStyle: { color: s.color, borderWidth: 2, borderColor: t.surface },
        areaStyle: o.area ? {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: s.color + '3a' }, { offset: 1, color: s.color + '00' }]
          }
        } : undefined,
        markLine: (data.milestones && s === data.series[0]) ? {
          symbol: 'none', silent: true,
          lineStyle: { color: t.warn, type: 'dashed', width: 1 },
          label: { color: t.warn, fontSize: 10.5, formatter: p => p.name },
          data: data.milestones.map(m => ({ xAxis: m.x, name: m.label }))
        } : undefined
      }))
    }));
  }

  /* ================= 4. 柱状图（错误类型分布 / 时间分布） ================= */
  function bar(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => {
      const palette = [t.danger, '#f97316', t.warn, '#a3e635', t.ok, t.info];
      return {
        tooltip: Object.assign(baseTooltip(t), { trigger: 'axis', axisPointer: { type: 'shadow' } }),
        grid: { left: 4, right: o.horizontal ? 40 : 8, top: 18, bottom: 4, containLabel: true },
        xAxis: o.horizontal
          ? { type: 'value', minInterval: o.minInterval, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.split, type: 'dashed' } }, axisLabel: { color: t.dim, fontSize: 11 } }
          : { type: 'category', data: data.map(d => d.name), axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false }, axisLabel: { color: t.dim, fontSize: 11, interval: 0, rotate: o.rotate || 0 } },
        yAxis: o.horizontal
          ? { type: 'category', data: data.map(d => d.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text2, fontSize: 11.5 } }
          : { type: 'value', minInterval: o.minInterval, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.split, type: 'dashed' } }, axisLabel: { color: t.dim, fontSize: 11 } },
        series: [{
          type: 'bar',
          barMaxWidth: o.horizontal ? 16 : 26,
          data: data.map((d, i) => ({
            value: d.value,
            itemStyle: {
              color: o.color || palette[i % palette.length],
              borderRadius: o.horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0]
            }
          })),
          label: o.showLabel ? {
            show: true, position: o.horizontal ? 'right' : 'top',
            color: t.text2, fontSize: 11, fontFamily: 'monospace',
            formatter: o.labelFmt || '{c}'
          } : undefined
        }]
      };
    });
  }

  /* ================= 5. 热力图（知识点 × 学生） ================= */
  function heatmap(sel, data, onClick) {
    // 后端返回: data.data[row][col] = score 二维矩阵, data.startedMask[row][col] = bool
    // ECharts heatmap 期望: [[colIdx, rowIdx, value], ...] 三元组格式
    const rawMatrix = data.data || [];
    const mask = data.startedMask || [];
    const startedData = [];
    const unstartedData = [];
    const studentNames = (data.studentAxis || []).map(s => typeof s === 'object' ? s.name : s);
    const visibleStudentCount = 10;
    const needsStudentScroll = studentNames.length > visibleStudentCount;
    const maxStudentNameLength = studentNames.reduce((max, name) => Math.max(max, String(name || '').length), 0);
    // 给 Y 轴学生姓名预留稳定空间，避免 containLabel 在窄尺寸初始化时把绘图区压成一小条。
    const gridLeft = Math.min(150, Math.max(78, maxStudentNameLength * 13 + 24));
    const gridTop = (data.kpAxis || []).length > 18 ? 96 : 76;
    for (let row = 0; row < rawMatrix.length; row++) {
      for (let col = 0; col < (rawMatrix[row] || []).length; col++) {
        const started = mask[row] ? mask[row][col] : true;
        const val = rawMatrix[row][col];
        if (started) {
          startedData.push([col, row, val]);
        } else {
          // 未学习的格子：value = null → ECharts 渲染为灰色
          unstartedData.push([col, row, 0]);
        }
      }
    }

    const label = data.label || '学习完成率';
    const inst = render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), {
        position: 'top',
        formatter(p) {
          if (p.value[2] == null) {
            return `<b>${data.studentAxis[p.value[1]] || p.value[1]}</b><br/>${data.kpAxis[p.value[0]] || p.value[0]}<br/><span style="color:var(--text-2)">未开始学习</span>`;
          }
          return `<b>${(data.studentAxis[p.value[1]] || {}).name || data.studentAxis[p.value[1]] || p.value[1]}</b><br/>${data.kpAxis[p.value[0]] || p.value[0]}<br/>${label}：<b style="font-size:14px">${p.value[2]}%</b>`;
        }
      }),
      grid: { left: gridLeft, right: 24, top: gridTop, bottom: 18, containLabel: false },
      xAxis: {
        type: 'category', data: data.kpAxis, position: 'top',
        splitArea: { show: true, areaStyle: { color: ['transparent'] } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.text2, fontSize: 10.5, rotate: 38, interval: 0, hideOverlap: true, margin: 10 }
      },
      yAxis: {
        type: 'category',
        data: studentNames,
        splitArea: { show: true, areaStyle: { color: ['transparent'] } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.text2, fontSize: 11.5, margin: 12 }
      },
      dataZoom: needsStudentScroll ? [{
        type: 'slider', yAxisIndex: 0, orient: 'vertical',
        right: 3, top: gridTop, bottom: 18, width: 12,
        startValue: 0, endValue: visibleStudentCount - 1,
        zoomLock: true, brushSelect: false, showDetail: false, showDataShadow: false,
        borderColor: 'transparent', backgroundColor: t.surface3,
        fillerColor: t.brand + '30', handleStyle: { color: t.brand, borderColor: t.brand }
      }, {
        type: 'inside', yAxisIndex: 0, orient: 'vertical',
        startValue: 0, endValue: visibleStudentCount - 1,
        zoomLock: true, zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false
      }] : [],
      visualMap: {
        // 卡片标题右侧已有统一的低-高图例，隐藏 ECharts 内置图例可避免占用绘图区。
        show: false, seriesIndex: 1, min: 0, max: 100, calculable: true, orient: 'horizontal',
        right: 14, top: 8, itemWidth: 12, itemHeight: 92,
        textStyle: { color: t.dim, fontSize: 10.5 },
        inRange: { color: ['#ef4444', '#f97316', '#f59e0b', '#a3e635', '#22c55e'] }
      },
      series: [{
        type: 'heatmap', data: unstartedData, silent: true, z: 0,
        animation: false, progressive: 0,
        itemStyle: { color: t.surface3, borderRadius: 3, borderColor: t.surface, borderWidth: 2 }
      }, {
        type: 'heatmap', data: startedData, z: 1,
        animation: false, progressive: 0,
        label: {
          show: true, color: '#0b1220', fontSize: 9.5, fontWeight: 600,
          formatter: p => p.value[2]
        },
        itemStyle: { borderRadius: 3, borderColor: t.surface, borderWidth: 2 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.4)', borderColor: t.brand, borderWidth: 2 } }
      }]
    }), onClick ? (p => onClick(p.value, data)) : null);
    const chartEl = inst && inst.getDom ? inst.getDom() : null;
    if (chartEl && chartEl._heatmapWheelHandler) {
      chartEl.removeEventListener('wheel', chartEl._heatmapWheelHandler);
      chartEl._heatmapWheelHandler = null;
    }
    if (chartEl && needsStudentScroll) {
      const wheelHandler = (event) => {
        const chart = window.echarts && echarts.getInstanceByDom(chartEl);
        if (!chart || !chart.containPixel({ gridIndex: 0 }, [event.offsetX, event.offsetY])) return;

        const zoom = (chart.getOption().dataZoom || [])[0] || {};
        const step = 100 / Math.max(studentNames.length - 1, 1);
        const windowSize = step * (visibleStudentCount - 1);
        const maxStart = Math.max(0, 100 - windowSize);
        const currentStart = Number.isFinite(Number(zoom.start)) ? Number(zoom.start) : 0;
        const direction = event.deltaY > 0 ? -1 : 1;
        const nextStart = Math.max(0, Math.min(maxStart, currentStart + direction * step));

        event.preventDefault();
        if (Math.abs(nextStart - currentStart) < 0.001) return;
        chart.dispatchAction({
          type: 'dataZoom', dataZoomIndex: 0,
          start: nextStart, end: Math.min(100, nextStart + windowSize)
        });
      };
      chartEl._heatmapWheelHandler = wheelHandler;
      chartEl.addEventListener('wheel', wheelHandler, { passive: false });
    }
    return inst;
  }

  /* ================= 6. 环形占比图（预警构成等） ================= */
  function donut(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'item', formatter: '{b}<br/>{c} 人 ({d}%)' }),
      legend: {
        // 班级学情总览的环形图使用居中布局，避免窄容器下图形被挤到左侧。
        orient: 'horizontal', left: 'center', bottom: 4,
        textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 10, itemHeight: 10, itemGap: 18
      },
      series: [{
        type: 'pie', radius: ['52%', '76%'], center: ['50%', '41%'],
        avoidLabelOverlap: false, padAngle: 2,
        itemStyle: { borderRadius: 5, borderColor: t.surface, borderWidth: 2 },
        label: {
          show: true, position: 'center',
          formatter: () => `{a|${o.centerValue || ''}}\n{b|${o.centerLabel || ''}}`,
          rich: {
            a: { color: t.text, fontSize: 24, fontWeight: 'bold', fontFamily: 'monospace', lineHeight: 30 },
            b: { color: t.dim, fontSize: 11.5, lineHeight: 18 }
          }
        },
        emphasis: { label: { show: true }, scale: true, scaleSize: 6 },
        labelLine: { show: false },
        data: data.map(d => ({ name: d.name, value: d.value, itemStyle: { color: d.color } }))
      }]
    }));
  }

  /* ================= 7. 仪表盘（班级达标率） ================= */
  function gauge(sel, value, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      series: [{
        type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100,
        center: ['50%', '62%'], radius: '96%',
        progress: { show: true, width: 14, roundCap: true, itemStyle: { color: o.color || t.brand } },
        axisLine: { lineStyle: { width: 14, color: [[1, t.split]] } },
        pointer: { show: false },
        axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: { show: true, offsetCenter: [0, '24%'], color: t.dim, fontSize: 11.5 },
        detail: {
          valueAnimation: true, offsetCenter: [0, '-6%'],
          fontSize: 27, fontWeight: 'bold', fontFamily: 'monospace',
          color: t.text, formatter: '{value}%'
        },
        data: [{ value, name: o.name || '' }]
      }]
    }));
  }

  /* ================= 8. 分组柱状（班级对比） ================= */
  function groupBar(sel, data) {
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'axis' }),
      legend: { top: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 12, itemHeight: 8 },
      grid: { left: 4, right: 8, top: 34, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category', data: data.categories,
        axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
        axisLabel: { color: t.dim, fontSize: 10.5, interval: 0, rotate: 18 }
      },
      yAxis: {
        type: 'value', axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: t.split, type: 'dashed' } },
        axisLabel: { color: t.dim, fontSize: 11 }
      },
      series: data.series.map(s => ({
        name: s.name, type: 'bar', data: s.data, barMaxWidth: 18,
        itemStyle: { color: s.color, borderRadius: [4, 4, 0, 0] }
      }))
    }));
  }

  return { render, graph, radar, line, bar, heatmap, donut, gauge, groupBar, resizeAll, redrawAll, tokens, relPalette,
    // 视图冻结：给教师端（graph-edit.js）复用同一实现，避免两处各写一份补偿算法而漂移
    viewMetrics, restoreView };
})();

