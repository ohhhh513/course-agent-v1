'use strict';

  /* ================================================================
     视图 7 · 预警与提醒中心
     ================================================================ */
  const Alerts = {
    level: 'all',
    render() {
      const el = U.$('#view-alerts');
      el.innerHTML = `
      <div class="grid g-3" style="margin-bottom:16px" id="aStats"></div>
      <div class="card">
        <div class="card__head">
          <h3>${icon('bell')} 预警列表</h3>
          <span class="spacer"></span>
          <div class="chips" id="aChips">
            <button class="chip is-active" data-l="all">全部</button>
            <button class="chip" data-l="red"><i class="dot dot--danger"></i>紧急</button>
            <button class="chip" data-l="yellow"><i class="dot dot--warn"></i>关注</button>
            <button class="chip" data-l="green"><i class="dot dot--ok"></i>已解除</button>
          </div>
        </div>
        <div class="card__body stack" id="aList">${U.skeleton(300)}</div>
      </div>`;
      U.$$('#aChips .chip', el).forEach(c => c.addEventListener('click', () => {
        U.$$('#aChips .chip', el).forEach(x => x.classList.remove('is-active'));
        c.classList.add('is-active'); this.level = c.dataset.l; this.load();
      }));
      this.load();
    },
    load() {
      API.student.alerts({ level: this.level }).then(r => {
        // 统计卡：用后端返回的全量 stats（不受 level 筛选影响）
        const S = r.stats || { red: 0, yellow: 0, green: 0 };
        U.$('#aStats').innerHTML = `
          <div class="stat stat--link" data-l="red" style="--_c:var(--danger)"><div class="stat__label">紧急预警</div>
            <div class="stat__value">${S.red}</div>
            <div class="stat__hint">需立即处理</div></div>
          <div class="stat stat--link" data-l="yellow" style="--_c:var(--warn)"><div class="stat__label">关注预警</div>
            <div class="stat__value">${S.yellow}</div>
            <div class="stat__hint">建议本周内处理</div></div>
          <div class="stat stat--link" data-l="green" style="--_c:var(--ok)"><div class="stat__label">已解除</div>
            <div class="stat__value">${S.green}</div>
            <div class="stat__hint">补救有效，掌握率回升</div></div>`;

        // 三类预警统计卡 → 点击切换到对应等级筛选
        U.$$('#aStats .stat--link').forEach(card => {
          card.addEventListener('click', () => {
            const lvl = card.dataset.l;
            U.$$('#aChips .chip').forEach(x => x.classList.toggle('is-active', x.dataset.l === lvl));
            this.level = lvl; this.load();
            const t = window.document.getElementById('aList');
            if (t && t.scrollIntoView) { try { t.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {} }
          });
        });

        const typeIcon = { mastery_low: 'target', progress_lag: 'clock', error_cluster: 'alert', resolved: 'checkCircle' };
        U.$('#aList').innerHTML = r.list.map(a => `
        <div class="alert-card ${U.alertCard[a.level]}">
          <div class="alert-card__head">
            <div class="alert-card__ico">${icon(typeIcon[a.type] || 'alert')}</div>
            <div class="alert-card__body">
              <div class="row" style="margin-bottom:3px">
                <span class="badge ${U.alertBadge[a.level]}">${U.alertName[a.level]}</span>
                <span class="badge badge--outline mono">${a.alertId}</span>
                <span class="spacer"></span>
                <span class="fz-11 t-dim">${a.createdAt}</span>
              </div>
              <h4>${U.esc(a.title)}</h4>
              <p>${U.esc(a.desc)}</p>
            </div>
          </div>
          <div class="alert-card__sug">
            <div class="sug-box">
              <div class="sug-box__title">${icon('bulb')} 改进建议（系统已适配你的学情）</div>
              <ul>${a.suggestions.map(s => `<li>${U.esc(s.text)}</li>`).join('')}</ul>
            </div>
          </div>
          <div class="alert-card__foot">
            <button class="btn btn--sm" data-detail="${a.alertId}">${icon('eye')} 查看详情</button>
            ${a.status === 'open' ? `
              <button class="btn btn--sm btn--primary" data-fix="${a.alertId}">${icon('target')} 去补救</button>` : ''}
            <span class="spacer"></span>
            <span class="fz-11 t-dim">${({ open: '待处理', read: '已读', reviewed: '已复核', ignored: '已忽略', closed: a.level === 'green' ? '已解除' : '已关闭' })[a.status] || '已关闭'}</span>
          </div>
        </div>`).join('') || R.empty('暂无该类型预警', '', 'checkCircle');

        U.$$('[data-detail]').forEach(b => b.addEventListener('click', () => {
          const a = r.list.find(x => x.alertId === b.dataset.detail);
          Modal.open({
            title: a.title, size: 'wide',
            body: `<div class="kv" style="margin-bottom:16px">
                ${Object.entries(a.detail).map(([k, v]) => {
              const label = { current: '当前正确率', threshold: '达标线(绿)', redBelow: '预警线(红)', classAvg: '班级平均', errorCount: '错题数', relatedQuestions: '关联题量', planned: '计划进度', actual: '实际进度', lagHours: '滞后学时', total: '作答总数', wrong: '错误数', mainErrorType: '主要错误类型', concentration: '集中度', before: '补救前', after: '补救后', days: '稳定天数' }[k] || k;
              return `<div class="kv__row"><span>${label}</span><span>${v}</span></div>`;
            }).join('')}
              </div>
              <div class="divider"></div>
              <p class="fz-12 t-dim" style="margin-bottom:8px">补救练习</p>
              <div class="stack" style="gap:8px">
                ${a.suggestions.map(s => `<div class="file-item">${icon('pencil')}
                  <b>${U.esc(s.text)}</b>${s.kpId ? `<button class="btn btn--xs btn--outline" data-fix-detail="${U.esc(s.kpId)}">开始</button>` : ''}</div>`).join('')}
              </div>`,
            onMount: (ov, close) => {
              const btn = ov.querySelector('[data-fix-detail]');
              if (btn) btn.addEventListener('click', () => {
                if (typeof Practice !== 'undefined') Practice._pendingTarget = { kpId: btn.dataset.fixDetail, kpName: a.kp };
                close();
                Router.go('practice');
              });
            }
          });
        }));
        U.$$('[data-fix]').forEach(b => b.addEventListener('click', () => {
          // 按该预警的知识点，直接开一组靶向练习
          const a = r.list.find(x => x.alertId === b.dataset.fix);
          if (typeof Practice !== 'undefined') {
            Practice._pendingTarget = { kpId: (a && a.kpId) || '', kpName: (a && a.kp) || '' };
          }
          Router.go('practice');
          Toast.ok('已按该知识点组卷', (a && a.kp) ? `靶向练习：${a.kp}` : '');
        }));
      });
    }
  };

Router.register('alerts', { title: '预警与提醒中心', mount: () => Alerts.render() });
