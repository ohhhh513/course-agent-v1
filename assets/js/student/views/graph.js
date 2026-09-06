'use strict';

  /* ================================================================
     视图 2 · 课程图谱导航（三图谱）
     ================================================================ */
  const GraphView = {
    type: 'knowledge',
    meta: {
      knowledge: { name: '知识图谱', desc: '将课程拆分为相互关联的知识点，精准构建前置 / 后置 / 并列 / 进阶逻辑关系，实现「前有根基，后有进阶，逐级推进」。', legend: [['前置关系', 'var(--brand-500)'], ['进阶关系', 'var(--accent-500)'], ['并列关系', 'var(--text-3)']] },
      problem: { name: '问题图谱', desc: '以问题为牵引构建高阶学习框架：驱动问题 → 子问题拆解 → 映射知识点 → 关联高频错题簇，渐进式培养解决问题的能力。', legend: [['问题拆解', 'var(--accent-500)'], ['知识映射', 'var(--info)'], ['错题关联', 'var(--danger)']] },
      goal: { name: '目标图谱', desc: '基于 OBE 成果导向教育理念，将知识点与能力目标逐级绑定，形成「看得见、看得清」的达成主线，支撑专业目标达成。', legend: [['目标支撑', 'var(--info)']] }
    },

    render() {
      const el = U.$('#view-graph');
      const mt = this.meta[this.type];
      el.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="graph-toolbar">
          <div class="seg" id="graphSeg">
            <button data-t="knowledge" class="${this.type === 'knowledge' ? 'is-active' : ''}">知识图谱</button>
            <button data-t="problem" class="${this.type === 'problem' ? 'is-active' : ''}">问题图谱</button>
            <button data-t="goal" class="${this.type === 'goal' ? 'is-active' : ''}">目标图谱</button>
          </div>
          <div class="divider divider--v"></div>
          <span class="fz-12 t-dim">${mt.name}</span>
          <span class="spacer"></span>
          <button class="btn btn--sm" id="graphReset">${icon('refresh')} 重置视图</button>
        </div>
        <div class="graph-box" id="graphBox">
          <div class="graph-hint">滚轮缩放 · 拖拽平移 · 点击节点查看详情</div>
          <div class="graph-legend">
            ${mt.legend.map(([n, c]) => `<div class="row"><i class="lg-line" style="border-color:${c}"></i><span>${n}</span></div>`).join('')}
            ${this.type === 'knowledge' ? `<div class="row" style="margin-top:2px"><i class="lg-dot" style="background:var(--warn)"></i><span>◆ 边框 = 重难点</span></div>` : ''}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card__head"><h3>${icon('award')} 重难点清单</h3><span class="spacer"></span><span class="badge badge--warn" id="keyCount"></span></div>
        <div class="card__body card__body--flush"><div class="list" id="keyList" style="max-height:300px;overflow-y:auto"></div></div>
      </div>`;

      U.$$('#graphSeg button', el).forEach(b => b.addEventListener('click', () => {
        this.type = b.dataset.t; this.render();
      }));

      API.graph.get({ type: this.type }).then(g => {
        Charts.graph('#graphBox', g, (node) => this.openNode(node, g));
        U.$('#graphReset').addEventListener('click', () => Charts.graph('#graphBox', g, (n) => this.openNode(n, g)));

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
          return `<div class="list__item list__item--clickable" data-node="${n.id}">
            <span class="list__lead" style="width:8px;height:8px;border-radius:50%;background:${g.categories[n.category].color};margin-top:7px"></span>
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

    openNode(node, g) {
      // 目标 / 问题类节点：轻量弹窗
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

      // 知识点详情抽屉
      API.graph.kpDetail({ kpId: node.id }).then(k => {
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
        });
      });
    }
  };

Router.register('graph', { title: '课程图谱导航', mount: () => GraphView.render() });
