'use strict';

  /* ================================================================
     视图 2 · 课程图谱导航
     知识图谱：左画布 + 右「知识点详情」面板（概览 / 关联资源）

     2026-09-24 调整：删除「问题图谱 / 目标图谱」两个页签。
     核查结论（两图谱不可用，故从学生端移除）：
       1) 后端 /graph?type=problem|goal 有代码（按 graph_type 查库，problem 用真实
          错题数聚合 errorRate、goal 用 GOAL_KP_MAP 聚合掌握率），但教师端**没有任何
          创建 problem / goal 节点的入口**（建章/建知识点/图谱编排都只处理
          chapter 与 knowledge），真实课程里这两类节点恒为 0 条；
       2) GOAL_KP_MAP 仍是 v1.0 的 KP01/KP11… 编号，与现行 KP001… 体系对不上，
          即便有 goal 节点，达成度也恒为 0；
       3) 前端原本就未接接口：非 knowledge 分支直接渲染「开发中」占位。
     后端接口与 seed 里的演示节点未删。日后要恢复：还原本文件，并先补上
     problem/goal 节点的创建入口与数据。
     ================================================================ */
  const GraphView = {
    sideTab: 'overview',      // 右侧面板 Tab：overview | resources
    _graph: null,             // 最近一次渲染用的图谱数据（面板关系 chips 复用）
    _cur: null,               // 当前选中节点
    meta: {
      knowledge: { name: '知识图谱', desc: '将课程拆分为相互关联的知识点，精准构建前置 / 后置 / 并列 / 进阶逻辑关系，实现「前有根基，后有进阶，逐级推进」。', legend: [['前置关系', 'var(--rel-pre)'], ['进阶关系', 'var(--rel-advance)'], ['并列关系', 'var(--rel-parallel)']] }
    },

    render() {
      const el = U.$('#view-graph');
      const mt = this.meta.knowledge;
      // 知识图谱铺满可用区域
      el.classList.add('fill');

      const toolbar = `
        <div class="graph-toolbar">
          <span class="badge badge--brand">${icon('network')} ${mt.name}</span>
          <div class="divider divider--v"></div>
          <span class="fz-12 t-dim graph-toolbar__desc">${mt.desc}</span>
          <span class="spacer"></span>
          <button class="btn btn--sm" id="graphReset">${icon('refresh')} 重置视图</button>
        </div>`;

      el.innerHTML = `
      <style>#view-graph .graph-toolbar__desc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}</style>
      <div class="card graph-card">
        ${toolbar}
        <div class="graph-layout">
          <div class="graph-box" id="graphBox">
            <div class="graph-hint">滚轮缩放 · 长按拖动 · 双击画布取消选中</div>
            <div class="graph-legend">
              ${mt.legend.map(([n, c]) => `<div class="row"><i class="lg-line" style="border-color:${c}"></i><span>${n}</span></div>`).join('')}
              <div class="row" style="margin-top:2px"><i class="lg-dot" style="background:var(--warn)"></i><span>◆ 边框 = 重难点</span></div>
            </div>
          </div>
          <aside class="kp-side" id="kpPanel"></aside>
        </div>
      </div>

      <div class="card key-card">
        <div class="card__head"><h3>${icon('award')} 重难点清单</h3><span class="spacer"></span><span class="badge badge--warn" id="keyCount"></span></div>
        <div class="card__body card__body--flush"><div class="list" id="keyList"></div></div>
      </div>`;

      this.paintSideEmpty();

      API.graph.get({ type: 'knowledge' }).then(g => {
        if (!el.classList.contains('is-active')) return;   // 竞态：视图已切走
        this._graph = g;
        // 教师布点快照：学生端拖拽会把落点坐标写回 g.nodes（见 charts.js 的「坐标不变量」），
        // 不留底的话「重置视图」就再也回不到教师的编排结果了 —— 只能重置缩放，不能归还布点。
        const basePos = g.nodes.map(n => ({ id: n.id, x: n.x, y: n.y }));
        const draw = () => Charts.graph('#graphBox', g, (node) => this.openNode(node, g));
        draw();
        U.$('#graphReset').addEventListener('click', () => {
          basePos.forEach(p => { const n = g.nodes.find(x => x.id === p.id); if (n) { n.x = p.x; n.y = p.y; n.fixed = p.x != null; } });
          this.paintSideEmpty(); draw();
        });

        // 双击画布：取消节点选中（关闭右侧详情并取消强调）
        U.$('#graphBox').addEventListener('dblclick', () => {
          const inst = window.echarts && echarts.getInstanceByDom(U.$('#graphBox'));
          if (inst) inst.dispatchAction({ type: 'downplay' });
          this._cur = null;
          this.paintSideEmpty();
        });

        // 重难点清单：知识图谱取 isKey 节点，按掌握率升序（最需要补的在前）
        const keys = g.nodes.filter(n => n.isKey).sort((a, b) => a.mastery - b.mastery);
        U.$('#keyCount').textContent = keys.length + ' 项';
        U.$('#keyList').innerHTML = keys.map(n => {
          const v = (n.mastery === undefined || n.mastery === null) ? null : n.mastery;
          const lv = v === null ? 'none' : U.level(v);
          const dotColor = (g.categories[n.category] || g.categories[3] || {}).color || 'var(--text-3)';
          return `<div class="list__item list__item--clickable" data-node="${n.id}">
            <span class="list__lead" style="width:8px;height:8px;border-radius:50%;background:${dotColor};margin-top:7px"></span>
            <div class="list__main"><b>${U.esc(n.name)}</b>
              <p>${n.chapter ? U.esc(n.chapter) + ' · ' : ''}${n.difficulty ? '难度 ' + '★'.repeat(n.difficulty) : ''}</p></div>
            ${v !== null ? `<div class="list__trail"><span class="badge ${U.levelBadge[lv]}">${v}%</span></div>` : ''}
          </div>`;
        }).join('') || R.empty('暂无数据');
        U.$$('[data-node]', el).forEach(r => r.addEventListener('click', () => {
          const n = g.nodes.find(x => x.id === r.dataset.node);
          this.openNode(n, g);
        }));
      });
    },

    /* ---------------- 右侧详情面板 ---------------- */

    paintSideEmpty() {
      const box = U.$('#kpPanel');
      if (!box) return;
      this.sideTab = 'overview';
      box.innerHTML = `
        <div class="kp-side__empty">
          <div style="font-size:30px;margin-bottom:10px">🧭</div>
          <b style="color:var(--text-2);font-size:13px;display:block;margin-bottom:6px">知识点详情</b>
          点击图上的知识点节点<br>查看解释、学情与前后置关系
        </div>`;
    },

    /** 关系 chips：前置 / 后置 / 并列（取图谱真实连线，与画布一致） */
    _relOf(node, g) {
      const nm = (id) => { const n = g.nodes.find(x => x.id === id); return n ? n.name : id; };
      const pre = g.links.filter(l => l.target === node.id && l.relation === 'pre').map(l => nm(l.source));
      const post = g.links.filter(l => l.source === node.id && l.relation === 'pre').map(l => nm(l.target));
      const par = g.links.filter(l => l.relation === 'parallel' && (l.source === node.id || l.target === node.id))
        .map(l => nm(l.source === node.id ? l.target : l.source));
      const adv = g.links.filter(l => l.relation === 'advance' && l.source === node.id).map(l => nm(l.target));
      const uniq = (a) => [...new Set(a)];
      return { pre: uniq(pre), post: uniq(post), parallel: uniq(par), advance: uniq(adv) };
    },

    _chips(list, color) {
      return list.length
        ? `<div class="chips">${list.map(n => `<span class="chip"${color ? ` style="border-color:${color};color:${color}"` : ''}>${U.esc(n)}</span>`).join('')}</div>`
        : '<span class="fz-12 t-dim">暂无</span>';
    },

    _overviewHtml(d, rel) {
      const lv = U.level(d.masteryRate);
      const num = (v, unit) => (v === null || v === undefined || v === '' ? '—' : v + (unit || ''));
      const dur = (m) => (m === null || m === undefined || m === '' ? '—' : U.durMin(m));
      const intro = (d.summary || '').trim();
      return `
      <div class="kp-sec">
        <div class="kp-sec__t">知识点介绍</div>
        ${intro ? `
          <div class="kp-intro"><div class="kp-text is-clamped" id="kpText">${U.esc(intro)}</div></div>
          <button class="kp-more" id="kpMore" type="button" style="display:none">展开</button>`
        : '<div class="kp-intro kp-intro--empty">该知识点暂无介绍</div>'}
      </div>

      <div class="kp-sec">
        <div class="kp-sec__t">学情概览</div>
        <p class="kp-row__t">我的</p>
        <div class="kp-stats">
          <div class="kp-stat"><b>${num(d.completionRate, '%')}</b><span>学习完成度</span></div>
          <div class="kp-stat"><b style="color:${U.levelColor[lv]}">${num(d.masteryRate, '%')}</b><span>知识点掌握度</span></div>
          <div class="kp-stat"><b>${dur(d.studyMinutes)}</b><span>学习时长</span></div>
        </div>
        <p class="kp-row__t" style="margin-top:12px">课程平均</p>
        <div class="kp-stats">
          <div class="kp-stat kp-stat--avg"><b>${num(d.courseAvgCompletion, '%')}</b><span>平均完成度</span></div>
          <div class="kp-stat kp-stat--avg"><b>${num(d.courseAvgMastery, '%')}</b><span>平均掌握度</span></div>
          <div class="kp-stat kp-stat--avg"><b>${dur(d.courseAvgMinutes)}</b><span>平均时长</span></div>
        </div>
        <p class="fz-11 t-dim" style="margin-top:8px;line-height:1.7">
          课程平均分母 = 课程内全部学生（${d.courseStudentCount || 0} 人），其中 ${d.courseStudiedCount || 0} 人在该知识点有学习记录；
          学习时长 = 视频观看进度 + 练习作答时长。
        </p>
      </div>

      <div class="kp-sec">
        <div class="kp-sec__t">属性</div>
        <div class="kp-attrs">
          <span class="chip">${U.esc(d.chapter || '未分章')}</span>
          <span class="chip">难度 ${'★'.repeat(d.difficulty || 0) || '—'}</span>
          <span class="chip">${d.hours || 0} 学时</span>
          ${d.isKey ? '<span class="chip" style="border-color:var(--warn);color:var(--warn)">重点</span>' : ''}
          <span class="chip">题库 ${d.questionCount || 0} 题</span>
          ${d.wrongCount ? `<span class="chip" style="border-color:var(--danger);color:var(--danger)">我的错题 ${d.wrongCount}</span>` : ''}
        </div>
      </div>

      <div class="kp-sec">
        <div class="kp-sec__t">知识点关系</div>
        <p class="fz-11 t-dim" style="margin:0 0 6px">前置知识点</p>
        ${this._chips(rel.pre, 'var(--brand-500)')}
        <p class="fz-11 t-dim" style="margin:12px 0 6px">后置知识点</p>
        ${this._chips(rel.post, 'var(--accent-500)')}
        <p class="fz-11 t-dim" style="margin:12px 0 6px">并列知识点</p>
        ${this._chips(rel.parallel, 'var(--text-2)')}
        ${rel.advance.length ? `<p class="fz-11 t-dim" style="margin:12px 0 6px">进阶知识点</p>${this._chips(rel.advance, 'var(--accent-500)')}` : ''}
        ${(d.relatedProblems || []).length ? `<p class="fz-11 t-dim" style="margin:12px 0 6px">关联问题</p>${this._chips(d.relatedProblems, 'var(--info)')}` : ''}
      </div>`;
    },

    _resourcesHtml(d) {
      const list = d.resources || [];
      return `
      <div class="kp-sec">
        <div class="kp-sec__t">挂载学习资源<span class="kp-sec__note">${list.length} 个</span></div>
        <div class="stack" style="gap:8px">
          ${list.map(r => `
            <div class="file-item res-link" data-res-id="${U.esc(r.resId)}" data-type="${U.esc(r.type)}" data-title="${U.esc(r.title)}" data-duration="${U.esc(r.duration || '')}" data-pages="${r.pages || 0}" data-url="${U.esc(r.url || '')}">
              <img class="file-item__cov" src="/resources/covers/${r.resId}.jpg" alt="" onerror="this.remove()">
              ${icon(r.type === 'video' ? 'video' : r.type === 'ppt' ? 'ppt' : 'file')}
              <b>${U.esc(r.title)}</b>
              <span class="fz-11 t-dim nowrap">${r.duration || (r.pages + ' 页')}</span>
              <span class="badge ${r.progress >= 100 ? 'badge--ok' : r.progress > 0 ? 'badge--warn' : 'badge--outline'}">${r.progress}%</span>
            </div>`).join('') || '<span class="fz-12 t-dim">暂无挂载资源</span>'}
        </div>
      </div>`;
    },

    paintSide(d, rel) {
      const box = U.$('#kpPanel');
      if (!box) return;
      const lv = U.level(d.masteryRate);
      box.innerHTML = `
        <div class="kp-side__head">
          <h3>${U.esc(d.name)}</h3>
          <div class="row" style="gap:6px;flex-wrap:wrap">
            <span class="badge badge--brand">${U.esc(d.chapter || '未分章')}</span>
            ${d.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}
            <span class="badge badge--outline">难度 ${'★'.repeat(d.difficulty || 0) || '—'}</span>
            <span class="badge badge--outline">${d.hours || 0} 学时</span>
          </div>
        </div>
        <div class="kp-tabs">
          <button data-st="overview" class="${this.sideTab === 'overview' ? 'on' : ''}">概览</button>
          <button data-st="resources" class="${this.sideTab === 'resources' ? 'on' : ''}">关联资源</button>
        </div>
        <div class="kp-side__body" id="kpBody">
          ${this.sideTab === 'resources' ? this._resourcesHtml(d) : this._overviewHtml(d, rel)}
        </div>
        <div class="kp-side__foot">
          <button class="btn btn--outline btn--sm" id="dAsk">${icon('bot')} AI 提问</button>
          <button class="btn btn--primary btn--sm" id="dPractice">${icon('pencil')} 开始练习</button>
        </div>
        ${this.sideTab === 'overview' && lv === 'weak' ? `
          <div style="padding:0 14px 14px">
            <div class="callout callout--danger" style="margin:0">${icon('bulb')}
              <div><b>学习建议</b>当前掌握度低于达标线，建议先补齐前置知识点「${rel.pre[0] || '—'}」，再完成 6 道靶向练习。</div>
            </div>
          </div>` : ''}`;

      // Tab 切换
      U.$$('.kp-tabs button', box).forEach(b => b.addEventListener('click', () => {
        this.sideTab = b.dataset.st;
        this.paintSide(d, rel);
      }));
      // 解释展开/收起（仅当内容确实超出折叠高度时才显示按钮）
      const more = U.$('#kpMore', box);
      const txt = U.$('#kpText', box);
      if (more && txt) {
        if (txt.scrollHeight - txt.clientHeight > 4) more.style.display = '';
        else txt.classList.remove('is-clamped');
        more.addEventListener('click', () => {
          more.textContent = txt.classList.toggle('is-clamped') ? '展开' : '收起';
        });
      }
      // 底部动作
      U.$('#dAsk', box).addEventListener('click', () => Chat.draft('请讲解「' + d.name + '」这个知识点'));
      U.$('#dPractice', box).addEventListener('click', () => Router.go('practice'));
      // 资源点击（复用资源中心续看逻辑）
      U.$$('.res-link', box).forEach(el => {
        const res = {
          resId: el.dataset.resId, type: el.dataset.type, title: el.dataset.title,
          kp: el.dataset.kp || '', duration: el.dataset.duration,
          pages: Number(el.dataset.pages || 0), url: el.dataset.url
        };
        el.style.cursor = res.url ? 'pointer' : 'default';
        if (!res.url) return;
        el.addEventListener('click', () => {
          API.student.resourceView({ resId: res.resId }).catch(() => {});
          if (window.ResourceView) ResourceView.openResource(res);
        });
      });
    },

    openNode(node, g) {
      // 知识图谱：右侧内嵌详情面板（真实学情来自 /graph/kp/{id}）
      this._cur = node.id;
      const rel = this._relOf(node, g);
      const panel = U.$('#kpPanel');
      if (panel) panel.innerHTML = '<div class="kp-side__empty">加载中…</div>';
      API.graph.kpDetail({ kpId: node.id }).then(k => {
        if (this._cur !== node.id) return;   // 竞态：期间点了别的节点
        const d = Object.assign({}, k, {
          name: node.name, masteryRate: node.mastery, difficulty: node.difficulty,
          isKey: node.isKey, hours: node.hours,
        });
        this.paintSide(d, rel);
      }).catch(err => {
        Toast.err('知识点详情加载失败', (err && err.message) || '请稍后重试');
        if (panel) panel.innerHTML = '<div class="kp-side__empty">详情加载失败，请重试</div>';
      });
    }
  };

Router.register('graph', {
  title: '课程图谱导航',
  mount: () => GraphView.render(),
  reset: () => {
    GraphView.sideTab = 'overview';
    GraphView._graph = null;
    GraphView._cur = null;
  },
});
