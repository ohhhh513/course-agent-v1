'use strict';

  /* ================================================================
     视图 3 · 学情归因与错题分析
     ================================================================ */
  const Analysis = {
    render() {
      const el = U.$('#view-analysis');
      el.innerHTML = U.skeleton(420);
      API.analysis.errors({ classId: state.classId }).then(d => {
        // 防御性检查：确保所有字段存在且为数组
        const topWrongQuestions = Array.isArray(d.topWrongQuestions) ? d.topWrongQuestions : [];
        const causes = Array.isArray(d.causes) ? d.causes : [];
        const scope = d.scope || { chapter: '全部章节', timeRange: '全部', classId: state.classId || 'CL2301' };
        const weakChain = d.weakChain || { root: {}, mid: {}, leaf: {}, explain: '' };
        const commonVsIndividual = d.commonVsIndividual || { common: [], individual: [] };
        const common = Array.isArray(commonVsIndividual.common) ? commonVsIndividual.common : [];
        const individual = Array.isArray(commonVsIndividual.individual) ? commonVsIndividual.individual : [];

        el.innerHTML = `
        <div class="callout callout--brand" style="margin-bottom:16px">${icon('flask')}
          <div><b>分析范围</b>${U.esc(scope.chapter)} · ${U.esc(scope.timeRange)} · ${scope.classId}
          · 系统通过对错题记录聚类与 AI 归因，识别共性薄弱与个性异常。</div></div>

        <div class="card" style="margin-bottom:16px">
          <div class="card__head"><h3>${icon('alert')} 高频错题 Top 5</h3></div>
          <div class="card__body card__body--flush"><div class="list">
            ${topWrongQuestions.map(q => `
              <div class="list__item">
                <div class="list__main"><b class="clamp-2">${U.esc(q.stem)}</b>
                  <p>${U.esc(q.kp)} · 难度 ${U.stars(q.difficulty)} · 主要错项 ${q.mainWrongOption}</p></div>
                <div class="list__trail"><span class="badge badge--danger">错 ${q.wrongRate}%</span><span class="badge badge--outline mono">${q.count}次</span></div>
              </div>`).join('') || '<div class="fz-12 t-dim" style="padding:12px">暂无高频错题</div>'}
          </div></div>
        </div>

        <div class="card" style="margin-bottom:16px">
          <div class="card__head"><h3>${icon('link')} 知识点关联薄弱链路</h3></div>
          <div class="card__body">
            <div class="chain">
              <div class="chain__node chain__node--root"><b>${U.esc(weakChain.root.name || '—')}</b><span>前置 · 完成 ${weakChain.root.mastery || 0}%</span></div>
              <div class="chain__arrow">${icon('chevronRight')}</div>
              <div class="chain__node chain__node--mid"><b>${U.esc(weakChain.mid.name || '—')}</b><span>中间 · 完成 ${weakChain.mid.mastery || 0}%</span></div>
              <div class="chain__arrow">${icon('chevronRight')}</div>
              <div class="chain__node chain__node--leaf"><b>${U.esc(weakChain.leaf.name || '—')}</b><span>目标 · 完成 ${weakChain.leaf.mastery || 0}%</span></div>
            </div>
            <div class="callout callout--warn" style="margin-top:14px">${icon('bulb')}<div>${U.esc(weakChain.explain || '')}</div></div>
          </div>
        </div>

        <div class="card" style="margin-bottom:16px">
          <div class="card__head"><h3>${icon('bulb')} AI 归因建议（成因概率降序）</h3><span class="spacer"></span>
            <span class="badge badge--brand">${causes.length} 类成因</span></div>
          <div class="card__body card__body--flush">
            ${causes.map(c => {
              const evidence = Array.isArray(c.evidence) ? c.evidence : [];
              const advice = Array.isArray(c.advice) ? c.advice : [];
              const isInsufficient = c.title === '数据不足，待补充';
              // 数据不足条目：标题加灰色徽标，level badge 隐藏，避免与真实 AI 结论混淆
              const levelBadge = isInsufficient
                ? '<span class="badge badge--insufficient">数据不足</span>'
                : `<span class="badge ${c.level === 'danger' ? 'badge--danger' : c.level === 'warn' ? 'badge--warn' : 'badge--ok'}">${c.level === 'danger' ? '高优先' : c.level === 'warn' ? '中优先' : '低优先'}</span>`;
              const rootClass = isInsufficient ? 'cause cause--insufficient' : 'cause';
              return `
              <div class="${rootClass}">
                <div class="cause__main">
                  <div class="row"><h4>${U.esc(c.title)}</h4>
                    <span class="spacer"></span>${levelBadge}</div>
                  <p>${U.esc(c.desc || '')}</p>
                  ${evidence.length ? `<div class="fz-12 t-dim" style="margin-bottom:5px">证据</div>
                  <ul class="fz-12" style="margin:0 0 8px;padding-left:16px;color:var(--text-2)">${evidence.map(e => `<li>${U.esc(e)}</li>`).join('')}</ul>` : ''}
                  ${advice.length ? `<div class="callout callout--brand" style="padding:9px 11px">${icon('bulb')}<div><b>教学建议：</b>${advice.map(a => `<span class="badge badge--outline" style="margin:2px 4px 2px 0">${U.esc(a)}</span>`).join('')}</div></div>` : ''}
                </div>
              </div>`;
            }).join('') || '<div class="fz-12 t-dim" style="padding:12px">暂无归因建议</div>'}
          </div>
        </div>

        <div class="grid g-2">
          <div class="card">
            <div class="card__head"><h3>${icon('users')} 共性薄弱（班级层面）</h3></div>
            <div class="card__body stack" style="gap:12px">
              ${common.map(c => {
                // 新字段优先：kpName / wrongRate / wrongCount / level；
                // 兼容旧字段 kp / ratio / affected
                const kpName = c.kpName || c.kp || '未知';
                const rate = (c.wrongRate != null ? c.wrongRate : c.ratio) || 0;
                const cnt = c.wrongCount != null ? c.wrongCount : (c.affected || 0);
                const level = c.level || (rate > 80 ? 'danger' : rate >= 50 ? 'warn' : 'ok');
                const barClass = level === 'danger' ? 'bar--danger' : level === 'warn' ? 'bar--warn' : 'bar--ok';
                const badgeClass = level === 'danger' ? 'badge--danger' : level === 'warn' ? 'badge--warn' : 'badge--ok';
                const rateLabel = level === 'danger' ? '高' : level === 'warn' ? '中' : '低';
                return `
                <div class="common-weak">
                  <div class="row fz-13" style="margin-bottom:6px">
                    <b>${U.esc(kpName)}</b>
                    <span class="spacer"></span>
                    <span class="badge ${badgeClass}">${rateLabel} · ${rate}%</span>
                  </div>
                  <div class="common-weak__bar"><div class="common-weak__bar-fill ${barClass}" style="width:${Math.min(rate, 100)}%"></div></div>
                  <div class="fz-12 t-dim" style="margin-top:6px">
                    ${cnt} 名学生出错${c.startedCount ? ` · 学习过该知识点 ${c.startedCount} 人` : ''}
                  </div>
                </div>`;
              }).join('') || '<div class="fz-12 t-dim" style="padding:12px">暂无共性薄弱</div>'}
            </div>
          </div>
          <div class="card">
            <div class="card__head"><h3>${icon('user')} 个性异常（个体层面）</h3></div>
            <div class="card__body stack" style="gap:12px">
              ${individual.map(s => {
                // 新字段：name / avatar / avatarColor / wrongCount / topKp / level；
                // 兼容旧字段 student
                const displayName = s.name || s.student || '—';
                const initial = s.avatar || displayName[0] || '?';
                const color = s.avatarColor || 'indigo';
                const wrongCount = s.wrongCount != null ? s.wrongCount : '';
                const topKp = s.topKp || '—';
                const level = s.level || (s.issue && s.issue.includes('未登录') ? 'danger' : 'warn');
                const cardClass = `indiv indiv--${level}`;
                return `
                <div class="${cardClass}">
                  <div class="indiv__avatar indiv__avatar--${color}">${U.esc(initial)}</div>
                  <div class="indiv__main">
                    <div class="row"><b>${U.esc(displayName)}</b>
                      <span class="spacer"></span>
                      ${wrongCount !== '' ? `<span class="badge badge--danger">错 ${wrongCount} 道</span>` : ''}
                    </div>
                    <div class="fz-12 t-dim">集中于「${U.esc(topKp)}」${s.desc ? ' · ' + U.esc(s.desc) : ''}</div>
                  </div>
                  <button class="btn btn--sm btn--outline" data-uid="${s.userId}">查看</button>
                </div>`;
              }).join('') || '<div class="fz-12 t-dim" style="padding:12px">暂无个性异常</div>'}
            </div>
          </div>
        </div>`;

        U.$$('[data-uid]', el).forEach(b => b.addEventListener('click', () => Monitor.openProfile(b.dataset.uid)));
      }).catch(err => {
        el.innerHTML = `<div class="card"><div class="card__body" style="padding:24px;text-align:center;color:var(--danger)">
          ${icon('alert')}<h3 style="margin:0">加载失败</h3><p class="fz-12 t-dim">${U.esc(err.message || err)}</p></div></div>`;
      });
    }
  };

Router.register('analysis', { title: '归因与错题分析', mount: () => Analysis.render() });
