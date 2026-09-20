'use strict';

  /* ================================================================
     视图 2 · 课程图谱导航（三图谱）
     知识图谱：左画布 + 右「知识点详情」面板（概览 / 关联资源）
     ================================================================ */
  const GraphView = {
    type: 'knowledge',
    sideTab: 'overview',      // 右侧面板 Tab：overview | resources
    _graph: null,             // 最近一次渲染用的图谱数据（面板关系 chips 复用）
    _cur: null,               // 当前选中节点
    meta: {
      knowledge: { name: '知识图谱', desc: '将课程拆分为相互关联的知识点，精准构建前置 / 后置 / 并列 / 进阶逻辑关系，实现「前有根基，后有进阶，逐级推进」。', legend: [['前置关系', 'var(--rel-pre)'], ['进阶关系', 'var(--rel-advance)'], ['并列关系', 'var(--rel-parallel)']] },
      problem: { name: '问题图谱', desc: '以问题为牵引构建高阶学习框架：驱动问题 → 子问题拆解 → 映射知识点 → 关联高频错题簇，渐进式培养解决问题的能力。', legend: [['问题拆解', 'var(--rel-split)'], ['知识映射', 'var(--rel-map)'], ['错题关联', 'var(--rel-error)']] },
      goal: { name: '目标图谱', desc: '基于 OBE 成果导向教育理念，将知识点与能力目标逐级绑定，形成「看得见、看得清」的达成主线，支撑专业目标达成。', legend: [['目标支撑', 'var(--rel-support)']] }
    },

    render() {
      const el = U.$('#view-graph');
      const mt = this.meta[this.type];
<<<<<<< Updated upstream
      el.innerHTML = `
      <div class="card" style="margin-bottom:16px">
=======
      const isKnowledge = this.type === 'knowledge';
      // 知识图谱铺满可用区域（其余图谱保持普通卡片流）
      el.classList.toggle('fill', isKnowledge);

      const seg = `
>>>>>>> Stashed changes
        <div class="graph-toolbar">
          <div class="seg" id="graphSeg">
            <button data-t="knowledge" class="${this.type === 'knowledge' ? 'is-active' : ''}">知识图谱</button>
            <button data-t="problem" class="${this.type === 'problem' ? 'is-active' : ''}">问题图谱</button>
            <button data-t="goal" class="${this.type === 'goal' ? 'is-active' : ''}">目标图谱</button>
          </div>
          <div class="divider divider--v"></div>
          <span class="fz-12 t-dim">${mt.name}</span>
          <span class="spacer"></span>
<<<<<<< Updated upstream
          <button class="btn btn--sm" id="graphReset">${icon('refresh')} 重置视图</button>
        </div>
        <div class="graph-box" id="graphBox">
          <div class="graph-hint">滚轮缩放 · 拖拽平移 · 点击节点查看详情</div>
          <div class="graph-legend">
            ${mt.legend.map(([n, c]) => `<div class="row"><i class="lg-line" style="border-color:${c}"></i><span>${n}</span></div>`).join('')}
            ${this.type === 'knowledge' ? `<div class="row" style="margin-top:2px"><i class="lg-dot" style="background:var(--warn)"></i><span>◆ 边框 = 重难点</span></div>` : ''}
=======
          ${isKnowledge ? `<button class="btn btn--sm" id="graphReset">${icon('refresh')} 重置视图</button>` : ''}
        </div>`;

      if (!isKnowledge) {
        const title = this.type === 'problem' ? '问题图谱' : '目标图谱';
        el.innerHTML = `
        <div class="card" style="margin-bottom:16px">${seg}</div>
        <div class="card">
          <div class="card__head"><h3>${icon(this.type === 'problem' ? 'flask' : 'award')} ${title}</h3>
            <span class="badge badge--warn">开发中</span></div>
          <div class="card__body">
            <div class="empty" style="padding:56px 24px;text-align:center">
              <div style="font-size:42px;margin-bottom:12px">🚧</div>
              <b style="font-size:16px;display:block;margin-bottom:8px">${title} · 正在开发</b>
              <p style="color:var(--text-3);font-size:13px;line-height:1.8;max-width:440px;margin:0 auto">
                ${this.type === 'problem'
                  ? '问题驱动的学习框架将按课程真实结构逐步开放，当前不再展示演示节点。'
                  : 'OBE 目标达成图谱将与课程知识点绑定后开放，当前不再展示演示节点。'}
              </p>
              <p class="fz-12 t-dim" style="margin-top:18px">
                请先使用 <b>知识图谱</b>（教师端已可按目录编排，学生端实时同步）
              </p>
            </div>
          </div>
        </div>`;
        U.$$('#graphSeg button', el).forEach(b => b.addEventListener('click', () => {
          this.type = b.dataset.t; this.render();
        }));
        return;
      }

      el.innerHTML = `
      <div class="card graph-card">
        ${seg}
        <div class="graph-layout">
          <div class="graph-box" id="graphBox">
            <div class="graph-hint">滚轮缩放 · 长按拖动 · 双击画布取消选中</div>
            <div class="graph-legend">
              ${mt.legend.map(([n, c]) => `<div class="row"><i class="lg-line" style="border-color:${c}"></i><span>${n}</span></div>`).join('')}
              <div class="row" style="margin-top:2px"><i class="lg-dot" style="background:var(--warn)"></i><span>◆ 边框 = 重难点</span></div>
            </div>
>>>>>>> Stashed changes
          </div>
          <aside class="kp-side" id="kpPanel"></aside>
        </div>
      </div>

      <div class="card key-card">
        <div class="card__head"><h3>${icon('award')} 重难点清单</h3><span class="spacer"></span><span class="badge badge--warn" id="keyCount"></span></div>
        <div class="card__body card__body--flush"><div class="list" id="keyList"></div></div>
      </div>`;

      this.paintSideEmpty();

      U.$$('#graphSeg button', el).forEach(b => b.addEventListener('click', () => {
        this.type = b.dataset.t; this.render();
      }));

      API.graph.get({ type: this.type }).then(g => {
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

        // 重难点 / 关键节点清单
        const keys = this.type === 'knowledge'
          ? g.nodes.filter(n => n.isKey).sort((a, b) => a.mastery - b.mastery)
          : this.type === 'problem'
            ? g.nodes.filter(n => n.category === 0 || n.category === 3)
            : g.nodes.filter(n => n.category === 1);
        U.$('#keyCount').textContent = keys.length + ' 项';
        U.$('#keyList').innerHTML = keys.map(n => {
          const v = n.mastery !== undefined ? n.mastery : (n.achieve !== undefined ? n.achieve : null);
          const lv = v === null ? 'none' : U.level(v);
          const dotColor = (g.categories[n.category] || g.categories[3] || {}).color || 'var(--text-3)';
          return `<div class="list__item list__item--clickable" data-node="${n.id}">
            <span class="list__lead" style="width:8px;height:8px;border-radius:50%;background:${dotColor};margin-top:7px"></span>
            <div class="list__main"><b>${U.esc(n.name)}</b>
              <p>${n.chapter ? U.esc(n.chapter) + ' · ' : ''}${n.difficulty ? '难度 ' + '★'.repeat(n.difficulty) : ''}${n.count ? n.count + ' 人次错题' : ''}${n.errorRate ? '错误率 ' + n.errorRate + '%' : ''}</p></div>
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
      // 目标 / 问题类节点：轻量弹窗（保持原交互）
      if (this.type !== 'knowledge') {
        const pre = g.links.filter(l => l.target === node.id).map(l => g.nodes.find(n => n.id === l.source)).filter(Boolean);
        const post = g.links.filter(l => l.source === node.id).map(l => g.nodes.find(n => n.id === l.target)).filter(Boolean);
        Modal.open({
          title: node.name,
          body: `<div class="kv">
            <div class="kv__row"><span>节点类型</span><span>${g.categories[node.category].name}</span></div>
            ${node.achieve !== undefined ? `<div class="kv__row"><span>达成度</span><span><b class="mono">${node.achieve}%</b> · 权重 ${node.weight}%</span></div>` : ''}
            ${node.errorRate !== undefined ? `<div class="kv__row"><span>错误率</span><span class="t-danger mono">${node.errorRate}%</span></div>` : ''}
            ${node.count !== undefined ? `<div class="kv__row"><span>累计错题</span><span class="mono">${node.count} 人次</span></div>` : ''}
          </div>
          ${node.achieve !== undefined ? `<div style="margin-top:14px">${U.bar(node.achieve, null, 'lg')}</div>` : ''}
          <div class="divider"></div>
          <p class="fz-12 t-dim" style="margin-bottom:8px">上游节点</p>
          <div class="chips">${pre.map(n => `<span class="chip">${U.esc(n.name)}</span>`).join('') || '<span class="t-dim fz-12">无</span>'}</div>
          <p class="fz-12 t-dim" style="margin:14px 0 8px">下游节点</p>
          <div class="chips">${post.map(n => `<span class="chip">${U.esc(n.name)}</span>`).join('') || '<span class="t-dim fz-12">无</span>'}</div>`
        });
        return;
      }

      // 知识图谱：右侧内嵌详情面板（真实学情来自 /graph/kp/{id}）
      this._cur = node.id;
      const rel = this._relOf(node, g);
      const panel = U.$('#kpPanel');
      if (panel) panel.innerHTML = '<div class="kp-side__empty">加载中…</div>';
      API.graph.kpDetail({ kpId: node.id }).then(k => {
<<<<<<< Updated upstream
        const d = Object.assign({}, k, { name: node.name, masteryRate: node.mastery, difficulty: node.difficulty, isKey: node.isKey, hours: node.hours });
        const pre = g.links.filter(l => l.target === node.id).map(l => g.nodes.find(n => n.id === l.source)).filter(Boolean);
        const post = g.links.filter(l => l.source === node.id).map(l => g.nodes.find(n => n.id === l.target)).filter(Boolean);
        const lv = U.level(d.masteryRate);

        Modal.drawer({
          title: '知识点详情',
          body: `
          <div class="node-detail__hero">
            <div class="row" style="margin-bottom:6px">
              <span class="badge badge--brand">${U.esc(node.chapter)}</span>
              ${d.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}
              <span class="badge badge--outline">难度 ${'★'.repeat(d.difficulty)}</span>
              <span class="badge badge--outline">${d.hours} 学时</span>
            </div>
            <h3>${U.esc(d.name)}</h3>
            <p class="fz-13 t-2" style="margin-top:8px;line-height:1.8">${U.esc(d.summary || '本知识点为课程核心内容，已挂载对应教学资源与习题。')}</p>
          </div>

          <div style="padding:18px">
            <div class="grid g-3" style="gap:12px;margin-bottom:16px">
              <div class="card card--flat card--pad" style="text-align:center">
                <b class="mono" style="font-size:22px;display:block">${d.completionRate || 0}%</b><span class="fz-11 t-dim">完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center">
                <b class="mono" style="font-size:22px;display:block;color:${U.levelColor[lv]}">${d.masteryRate}%</b><span class="fz-11 t-dim">学习完成率</span></div>
              <div class="card card--flat card--pad" style="text-align:center">
                <b class="mono" style="font-size:22px;display:block">${d.classAvgMastery || '—'}%</b><span class="fz-11 t-dim">班级平均</span></div>
            </div>

            <p class="fz-12 t-dim" style="margin-bottom:8px">前后置关系链</p>
            <div class="rel-chain" style="margin-bottom:18px">
              ${pre.slice(0, 2).map(n => `<span class="rel-node">${U.esc(n.name)}</span>`).join('<span class="rel-arrow">→</span>')}
              ${pre.length ? '<span class="rel-arrow">→</span>' : ''}
              <span class="rel-node rel-node--cur">${U.esc(d.name)}</span>
              ${post.length ? '<span class="rel-arrow">→</span>' : ''}
              ${post.slice(0, 2).map(n => `<span class="rel-node">${U.esc(n.name)}</span>`).join('<span class="rel-arrow">→</span>')}
            </div>

            <p class="fz-12 t-dim" style="margin-bottom:8px">挂载学习资源（${(d.resources || []).length}）</p>
            <div class="stack" style="gap:8px;margin-bottom:18px">
              ${(d.resources || []).map(r => `
                <div class="file-item res-link" data-res-id="${U.esc(r.resId)}" data-type="${U.esc(r.type)}" data-title="${U.esc(r.title)}" data-duration="${U.esc(r.duration || '')}" data-pages="${r.pages || 0}" data-url="${U.esc(r.url || '')}">
                  <img class="file-item__cov" src="/assets/resources/covers/${r.resId}.jpg" alt="" onerror="this.remove()">
                  ${icon(r.type === 'video' ? 'video' : r.type === 'ppt' ? 'ppt' : 'file')}
                  <b>${U.esc(r.title)}</b>
                  <span class="fz-11 t-dim nowrap">${r.duration || (r.pages + ' 页')}</span>
                  <span class="badge ${r.progress >= 100 ? 'badge--ok' : r.progress > 0 ? 'badge--warn' : 'badge--outline'}">${r.progress}%</span>
                </div>`).join('') || '<span class="fz-12 t-dim">暂无挂载资源</span>'}
            </div>

            ${d.relatedProblems ? `<p class="fz-12 t-dim" style="margin-bottom:8px">关联问题图谱</p>
            <div class="chips" style="margin-bottom:18px">${d.relatedProblems.map(p => `<span class="chip">${U.esc(p)}</span>`).join('')}</div>` : ''}

            <div class="callout ${lv === 'weak' ? 'callout--danger' : 'callout--brand'}">
              ${icon('bulb')}
              <div><b>学习建议</b>${lv === 'weak'
              ? `当前学习完成率低于达标线，建议先补齐前置知识点「${pre[0] ? pre[0].name : '—'}」，再完成 6 道靶向练习。`
              : `已达标，建议保持每周 1 次错题回顾，防止遗忘回落。`}</div>
            </div>
          </div>`,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="dAsk">${icon('bot')} 向 AI 助教提问</button>
            <button class="btn btn--primary" id="dPractice">${icon('pencil')} 开始练习</button>`,
          onMount(ov, close) {
            U.$('#dAsk', ov).addEventListener('click', () => {
              close(); Router.go('ai');
              setTimeout(() => Chat.ask('请讲解「' + d.name + '」这个知识点'), 260);
            });
            U.$('#dPractice', ov).addEventListener('click', () => { close(); Router.go('practice'); });

            // 知识点挂载资源点击打开（复用资源中心的进度续看逻辑）
            U.$$('.res-link', ov).forEach(el => {
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
          }
=======
        if (this._cur !== node.id) return;   // 竞态：期间点了别的节点
        const d = Object.assign({}, k, {
          name: node.name, masteryRate: node.mastery, difficulty: node.difficulty,
          isKey: node.isKey, hours: node.hours,
>>>>>>> Stashed changes
        });
        this.paintSide(d, rel);
      }).catch(err => {
        Toast.err('知识点详情加载失败', (err && err.message) || '请稍后重试');
        if (panel) panel.innerHTML = '<div class="kp-side__empty">详情加载失败，请重试</div>';
      });
    }
  };

Router.register('graph', { title: '课程图谱导航', mount: () => GraphView.render() });
