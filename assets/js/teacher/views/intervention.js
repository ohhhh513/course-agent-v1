'use strict';

  /* ================================================================
     视图 5 · 教学干预与策略
     ================================================================ */
  const Intervention = {
    tab: 'list',
    render() {
      const el = U.$('#view-intervention');
      el.innerHTML = `
      <div class="tabs tabs--fill" id="ivTabs" style="margin-bottom:16px">
        <button class="is-active" data-t="list">${icon('route')} 干预建议</button>
        <button data-t="templates">${icon('book')} 策略库</button>
      </div>
      <div id="ivBody"></div>`;
      U.$$('#ivTabs button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#ivTabs button', el).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.tab = b.dataset.t;
        this.tab === 'list' ? this.renderList() : this.renderTemplates();
      }));
      this.renderList();
    },

    renderList() {
      const box = U.$('#ivBody');
      API.intervention.list({ classId: state.classId }).then(r => {
        const stMap = { pending: ['待确认', 'badge--danger'], running: ['执行中', 'badge--warn'], done: ['已完成', 'badge--ok'] };
        box.innerHTML = `
        <div class="callout callout--brand" style="margin-bottom:14px">${icon('info')}
          <div>系统对每条预警自动推荐干预策略；教师可<b>确认执行</b>或<b>自定义</b>后执行，干预后学情变化可量化验证。</div></div>
        <div class="stack" style="gap:14px">
          ${r.list.map(iv => {
            const [lbl, bd] = stMap[iv.status] || ['—', 'badge--outline'];
            return `<div class="iv-card">
              <div class="iv-card__head">
                <div class="todo__ico todo__ico--${iv.level === 'danger' ? 'danger' : iv.level === 'warn' ? 'warn' : 'ok'}">${icon('route')}</div>
                <div style="flex:1;min-width:0">
                  <div class="row" style="margin-bottom:4px">
                    <b style="font-size:14px">${U.esc(iv.title)}</b><span class="spacer"></span>
                    <span class="badge ${bd}">${lbl}</span>
                    <span class="badge badge--outline">${iv.scope === 'common' ? '共性' : '个体'}</span></div>
                  <div class="fz-12 t-dim">${U.esc(iv.target)}</div>
                </div>
              </div>
              <div class="iv-card__body">
                <p class="fz-12 t-2" style="margin-bottom:8px"><b>归因：</b>${U.esc(iv.reason)}</p>
                <div class="iv-steps">${iv.steps.map(s => `<div class="iv-step"><span class="iv-step__n">•</span><span>${U.esc(s)}</span></div>`).join('')}</div>
                ${iv.execution ? `<div class="divider"></div>
                  <div class="grid g-4" style="gap:10px">
                    <div><b class="mono" style="color:var(--ok)">${iv.execution.masteryAfter}%</b><span class="fz-11 t-dim">复测完成率</span></div>
                    <div><b class="mono">${iv.execution.completeRate}%</b><span class="fz-11 t-dim">完成率</span></div>
                    <div><b class="mono">${iv.execution.retestDone}</b><span class="fz-11 t-dim">已复测</span></div>
                    <div><b class="mono t-brand">+${(iv.execution.masteryAfter - iv.execution.masteryBefore).toFixed(1)}pp</b><span class="fz-11 t-dim">提升</span></div>
                  </div>` : `<div class="callout callout--brand" style="margin-top:10px;padding:9px 11px">${icon('bulb')}<div><b>预期效果：</b>${U.esc(iv.expectEffect)}</div></div>`}
              </div>
              <div class="iv-card__foot">
                <button class="btn btn--sm" data-eff="${iv.ivId}">${icon('trend')} 干预效果</button>
                ${iv.status === 'pending' ? `<span class="spacer"></span><button class="btn btn--sm btn--ghost" data-rej="${iv.ivId}">忽略</button><button class="btn btn--sm btn--primary" data-cf="${iv.ivId}">确认执行</button>`
                  : '<span class="spacer"></span><span class="fz-11 t-dim">已处理</span>'}
              </div>
            </div>`;
          }).join('')}
        </div>`;

        U.$$('[data-eff]', box).forEach(b => b.addEventListener('click', () => this.showEffect(b.dataset.eff)));
        U.$$('[data-cf]', box).forEach(b => b.addEventListener('click', () =>
          API.intervention.confirm({ ivId: b.dataset.cf }).then(() => { Toast.ok('干预已确认执行', '资源已推送'); this.renderList(); })));
        U.$$('[data-rej]', box).forEach(b => b.addEventListener('click', () =>
          API.intervention.reject({ ivId: b.dataset.rej }).then(() => { Toast.info('已忽略该建议'); this.renderList(); })));
      });
    },

    showEffect(ivId) {
      API.intervention.effect({ ivId }).then(d => {
        const hasData = d.hasData !== false;
        const body = hasData
          ? `<div class="chart chart--lg" id="effChart"></div>
            <div class="callout callout--ok" style="margin-top:10px">${icon('checkCircle')}<div>${U.esc(d.summary)}</div></div>`
          : `<div class="empty" style="padding:40px 20px;text-align:center">
              ${icon('inbox', 48)}
              <p class="fz-13 t-2" style="margin-top:14px">${U.esc(d.summary)}</p>
            </div>`;
        Modal.open({
          title: '干预前后学情对比', size: 'wide',
          body: body,
          onMount(ov) {
            if (!hasData) return;
            Charts.line('#effChart', {
              xAxis: d.xAxis,
              series: [
                { name: d.series[0].name, data: d.series[0].data, color: d.series[0].color },
                { name: d.series[1].name, data: d.series[1].data, color: d.series[1].color }
              ]
            }, { area: true, max: 100, fmt: '{value}%' });
          }
        });
      });
    },

    renderTemplates() {
      const box = U.$('#ivBody');
      API.intervention.templates({}).then(list => {
        box.innerHTML = `
        <div class="callout callout--brand" style="margin-bottom:14px">${icon('book')}
          <div>策略库沉淀经实践验证有效的干预手段，可一键复用于同类学情场景，形成可复用模板。</div></div>
        <div class="grid g-3">
          ${list.map(t => `
            <div class="tpl">
              <h4>${U.esc(t.name)}</h4>
              <p>${U.esc(t.desc)}</p>
              <div class="chips" style="margin-bottom:10px">${t.tags.map(x => `<span class="badge badge--outline">${x}</span>`).join('')}</div>
              <div class="tpl__stats">
                <div><b>${t.useCount}</b><span>使用次数</span></div>
                <div><b class="t-ok">${t.successRate}%</b><span>成功率</span></div>
                <div><b class="t-brand">+${t.avgLift}</b><span>平均提升(pp)</span></div>
              </div>
              <div class="row" style="margin-top:12px"><span class="fz-11 t-dim">适用场景：${U.esc(t.scene)}</span>
                <span class="spacer"></span><button class="btn btn--sm btn--outline" data-use="${t.tplId}">复用</button></div>
            </div>`).join('')}
        </div>`;
        U.$$('[data-use]', box).forEach(b => b.addEventListener('click', () =>
          API.intervention.saveTemplate({ name: list.find(t => t.tplId === b.dataset.use).name }).then(r =>
            Toast.ok('已复用策略模板', '可在干预建议中一键套用'))));
      });
    }
  };

Router.register('intervention', { title: '教学干预与策略', mount: () => Intervention.render() });
