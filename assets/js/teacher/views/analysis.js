'use strict';

  /* ================================================================
     视图 3 · 学情归因与错题分析

     2026-09-24 调整：
       1) 移除「知识点关联薄弱链路」与「AI 归因建议」—— 核查确认二者并非真实实现
          （前者只是把掌握率最低的 3 个知识点摆成"链路"，后者是 error_type 的
          GROUP BY + 硬编码文案表），详见 最新bug修改9.23.md 第十三节；
       2) 保留下来的三块（高频错题 / 共性薄弱 / 个性异常）重排为
          「错题排行与标题统计 + 双栏明细」，避免页面空简。
     数值全部来自 GET /analysis/errors 的真实统计（后端未改动）；
     课程名取自 GET /course/my，仅用于展示。
     ================================================================ */

  /** 错误率 / 占比 → 配色与进度条档位（数值越高越需要关注） */
  function anTone(value) {
    const v = Number(value) || 0;
    if (v >= 60) return { c: 'var(--danger)', bg: 'var(--danger-soft)', bar: 'dashRed' };
    if (v >= 30) return { c: 'var(--warn)', bg: 'var(--warn-soft)', bar: 'dashBrown' };
    return { c: 'var(--ok)', bg: 'var(--ok-soft)', bar: 'dashGreen' };
  }

  const Analysis = {
    render() {
      const el = U.$('#view-analysis');
      el.innerHTML = U.skeleton(420);
      if (!API.config.activeCourseId) {
        el.innerHTML = `<div class="card"><div class="card__body"><div class="empty" style="padding:48px;text-align:center"><b>尚未创建或选择课程</b><p class="fz-12 t-dim">请先建课后再查看归因分析。</p></div></div></div>`;
        return;
      }
      API.analysis.errors({}).then(d => {
        const topWrongQuestions = Array.isArray(d.topWrongQuestions) ? d.topWrongQuestions : [];
        const commonVsIndividual = d.commonVsIndividual || { common: [], individual: [] };
        const common = Array.isArray(commonVsIndividual.common) ? commonVsIndividual.common : [];
        const individual = Array.isArray(commonVsIndividual.individual) ? commonVsIndividual.individual : [];

        /* 高频错题标题右侧的三项统计，沿用本页返回的数据口径。 */
        const wrongTimes = topWrongQuestions.reduce((sum, q) => sum + (Number(q.count) || 0), 0);
        const kpCount = new Set(topWrongQuestions.map(q => q.kpId || q.kp).filter(Boolean)).size;
        const stats = [
          { k: '累计答错', v: wrongTimes, u: '次', c: 'var(--warn)' },
          { k: '涉及知识点', v: kpCount, u: '个', c: 'var(--brand-500)' },
          { k: '待关注学生', v: individual.length, u: '人', c: 'var(--accent-500)' },
        ];

        const wrongItem = (q, i) => {
          const rate = Number(q.wrongRate) || 0;
          const t = anTone(rate);
          return `
          <div class="an-item" data-wrong="${i}" role="button" tabindex="0" title="查看题目">
            <span class="an-rank" style="background:${t.bg};color:${t.c}">${i + 1}</span>
            <div class="an-main">
              <b class="an-stem clamp-2">${U.esc(q.stem || '')}</b>
              <div class="an-meta">
                <span class="badge badge--outline">${U.esc(q.kp || '未标注知识点')}</span>
                <span title="难度 ${Number(q.difficulty) || 0} / 5">${U.stars(Number(q.difficulty) || 0)}</span>
                <span class="an-sep">·</span>
                <span>主要错项 <b class="mono">${U.esc(q.mainWrongOption || '—')}</b></span>
                <span class="an-qid mono">${U.esc(q.qId || '')}</span>
              </div>
            </div>
            <div class="an-trail">
              <div class="an-rate" style="color:${t.c}"><b>${rate}</b><small>% 错误率</small></div>
              ${U.bar(rate, t.bar, 'sm')}
              <span class="an-count">${Number(q.count) || 0} 次答错</span>
            </div>
          </div>`;
        };

        const commonRow = c => {
          const ratio = Number(c.ratio) || 0;
          const t = anTone(ratio);
          return `
          <div class="an-row">
            <div class="an-row__main">
              <div class="an-row__head">
                <b>${U.esc(c.kp || '未标注知识点')}</b>
                <span class="badge" style="background:${t.bg};color:${t.c}">${Number(c.affected) || 0}/${Number(c.startedCount) || 0} 人出错</span>
              </div>
              <div class="an-row__desc">${U.esc(c.desc || '')}</div>
              <div class="an-row__bar">${U.bar(ratio, t.bar, 'sm')}</div>
            </div>
            <div class="an-row__pct" style="color:${t.c}"><b>${ratio}</b><small>%</small></div>
          </div>`;
        };

        const individualRow = s => {
          const issue = s.issue || '需关注';
          const t = /滞后|极低/.test(issue)
            ? { c: 'var(--danger)', bg: 'var(--danger-soft)' }
            : { c: 'var(--warn)', bg: 'var(--warn-soft)' };
          const name = (s.student || '').trim();
          return `
          <div class="an-row">
            <span class="an-avatar" style="background:${t.bg};color:${t.c}">${U.esc(name.charAt(0) || '?')}</span>
            <div class="an-row__main">
              <div class="an-row__head">
                <b>${U.esc(name)}</b>
                <span class="badge" style="background:${t.bg};color:${t.c}">${U.esc(issue)}</span>
              </div>
              <div class="an-row__desc">${U.esc(s.desc || '')}</div>
            </div>
            <button class="btn btn--xs btn--outline" data-uid="${U.esc(s.userId || '')}">查看学情</button>
          </div>`;
        };

        el.innerHTML = `
        <style>
          #view-analysis .an-ranking-head{flex-wrap:wrap;gap:12px}
          #view-analysis .an-summary{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px;margin-left:auto}
          #view-analysis .an-summary__item{display:flex;align-items:baseline;gap:6px;white-space:nowrap;font-size:13px;color:var(--text-3)}
          #view-analysis .an-summary__item b{font-family:var(--font-num);font-size:20px;line-height:1.2}
          #view-analysis .an-summary__item small{font-size:12px}
          @media(max-width:720px){#view-analysis .an-summary{width:100%;margin-left:0;justify-content:space-between;gap:10px}}
          #view-analysis .an-item{display:flex;gap:12px;align-items:flex-start;padding:13px 16px;border-bottom:1px solid var(--border-soft);cursor:pointer}
          #view-analysis .an-item:last-child{border-bottom:none}
          #view-analysis .an-item:hover{background:var(--surface-2)}
          #view-analysis .an-rank{flex:0 0 24px;height:24px;border-radius:var(--r-full);display:grid;place-items:center;font-family:var(--font-num);font-size:13.5px;font-weight:700}
          #view-analysis .an-main{flex:1;min-width:0}
          #view-analysis .an-stem{display:block;font-size:14.5px;font-weight:600;line-height:1.6;color:var(--text)}
          #view-analysis .an-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:7px;font-size:12.5px;color:var(--text-3)}
          #view-analysis .an-meta .an-sep{opacity:.6}
          #view-analysis .an-qid{margin-left:auto;font-size:12px;opacity:.75}
          #view-analysis .an-trail{flex:0 0 132px;display:flex;flex-direction:column;align-items:flex-end;gap:5px}
          #view-analysis .an-trail .bar{width:100%}
          #view-analysis .an-rate{display:flex;align-items:baseline;gap:2px;font-family:var(--font-num)}
          #view-analysis .an-rate b{font-size:18px;font-weight:700;line-height:1}
          #view-analysis .an-rate small{font-size:11.5px;color:var(--text-3)}
          #view-analysis .an-count{font-size:12px;color:var(--text-3)}
          #view-analysis .an-row{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border-soft)}
          #view-analysis .an-row:last-child{border-bottom:none}
          #view-analysis .an-row__main{flex:1;min-width:0}
          #view-analysis .an-row__head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
          #view-analysis .an-row__head b{font-size:14px}
          #view-analysis .an-row__desc{font-size:13px;color:var(--text-2);margin-top:4px;line-height:1.6}
          #view-analysis .an-row__bar{margin-top:8px;max-width:320px}
          #view-analysis .an-row__pct{flex:0 0 auto;display:flex;align-items:baseline;gap:1px;font-family:var(--font-num)}
          #view-analysis .an-row__pct b{font-size:19px;font-weight:700}
          #view-analysis .an-row__pct small{font-size:12px;color:var(--text-3)}
          #view-analysis .an-avatar{flex:0 0 34px;height:34px;border-radius:var(--r-full);display:grid;place-items:center;font-size:15px;font-weight:600}
          #view-analysis .an-scroll{max-height:360px;overflow-x:hidden;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--brand-300) var(--surface-3)}
          #view-analysis .an-scroll::-webkit-scrollbar{width:6px}
          #view-analysis .an-scroll::-webkit-scrollbar-track{background:var(--surface-3);border-radius:var(--r-full)}
          #view-analysis .an-scroll::-webkit-scrollbar-thumb{background:var(--brand-300);border-radius:var(--r-full)}
        </style>

        <div class="card" style="margin-bottom:16px">
          <div class="card__head an-ranking-head">
            <h3>${icon('alert')} 高频错题 Top 5</h3>
            <div class="an-summary" aria-label="错题分析统计">
              ${stats.map(s => `<div class="an-summary__item"><span>${s.k}</span><b style="color:${s.c}" data-cnt="${s.v}">0</b><small>${s.u}</small></div>`).join('')}
            </div>
          </div>
          <div class="card__body card__body--flush">
            ${topWrongQuestions.length
              ? topWrongQuestions.map(wrongItem).join('')
              : R.empty('本课程暂无错题记录', '学生在智能练习中答错后，会按答错次数排序显示在这里（最多 5 道）', 'checkCircle')}
          </div>
        </div>

        <div class="grid g-2">
          <div class="card" style="min-height:212px">
            <div class="card__head">
              <h3>${icon('users')} 共性薄弱（班级层面）</h3>
              <span class="spacer"></span>
              <span class="badge ${common.length ? 'badge--danger' : 'badge--ok'}">${common.length ? common.length + ' 个知识点' : '正常'}</span>
            </div>
            <div class="card__body card__body--flush an-scroll">
              ${common.length
                ? common.map(commonRow).join('')
                : R.empty('暂无共性薄弱知识点', '判定线：学习过该知识点的学生中，出现错题 ≥2 人且占比 ≥30%；当前没有知识点达到', 'target')}
            </div>
          </div>
          <div class="card" style="min-height:212px">
            <div class="card__head">
              <h3>${icon('user')} 个性异常（个体层面）</h3>
              <span class="spacer"></span>
              <span class="badge ${individual.length ? 'badge--warn' : 'badge--ok'}">${individual.length ? individual.length + ' 名学生' : '正常'}</span>
            </div>
            <div class="card__body card__body--flush an-scroll">
              ${individual.length
                ? individual.map(individualRow).join('')
                : R.empty('暂无个体异常学生', '判定线：有效学习点 ≥3 个的学生中，平均掌握率 <40% 或完成率 <30%；当前没有学生达到', 'user')}
            </div>
          </div>
        </div>`;

        U.$$('[data-cnt]', el).forEach(s => U.countUp(s, +s.dataset.cnt, 0));
        U.$$('[data-uid]', el).forEach(b => b.addEventListener('click', () => Monitor.openProfile(b.dataset.uid)));
        this._topWrong = topWrongQuestions;
        U.$$('[data-wrong]', el).forEach(row => row.addEventListener('click', () => {
          this.openWrongDetail(this._topWrong[Number(row.dataset.wrong)]);
        }));
      }).catch(err => {
        el.innerHTML = `<div class="card"><div class="card__body" style="padding:24px;text-align:center;color:var(--danger)">
          ${icon('alert')}<h3 style="margin:0">加载失败</h3><p class="fz-12 t-dim">${U.esc(err.message || err)}</p></div></div>`;
      });
    },

    openWrongDetail(summary) {
      const qId = summary && summary.qId;
      if (!qId) return;
      API.question.bank({ keyword: qId, page: 1, size: 50 }).then(r => {
        const full = ((r && r.list) || []).find(item => item.qId === qId);
        if (!full) {
          Toast.warn('题库里没有这道题', '可能已移入回收站');
          return;
        }
        const typeName = { single: '单选题', multi: '多选题', multiple: '多选题', blank: '填空题', judge: '判断题', essay: '简答题' };
        const blank = full.type === 'blank';
        const options = Array.isArray(full.options) ? full.options : [];
        const optionHtml = blank
          ? `<div class="callout">参考答案：${U.esc(full.answer || '未填写')}</div>`
          : `<div class="opts opts--readonly">${options.map(option => `
              <div class="opt${option.right ? ' is-right' : ''}">
                <span class="opt__key">${U.esc(option.key || '')}</span>
                <span style="flex:1">${U.esc(option.text || '')}</span>
                ${option.right ? '<span class="opt__flag badge badge--ok">正确答案</span>' : ''}
              </div>`).join('') || '<div class="t-dim fz-13">没有选项</div>'}</div>`;
        const rate = Number(summary.wrongRate) || 0;
        Modal.open({
          title: '题目详情 · ' + qId,
          size: 'wide',
          body: `
            <div class="stack" style="gap:12px">
              <div class="row row--wrap fz-12 t-dim">
                <span class="badge badge--outline mono">${U.esc(qId)}</span>
                <span class="badge badge--brand">${U.esc(typeName[full.type] || full.type || '题目')}</span>
                <span class="badge badge--outline">${U.esc(full.kp || summary.kp || '未标注知识点')}</span>
                <span class="badge badge--outline">难度 ${U.stars(full.difficulty)}</span>
                <span class="badge badge--danger">错误率 ${rate}%</span>
                <span class="badge badge--outline">${Number(summary.count) || 0} 次答错</span>
              </div>
              <div>
                <div class="fz-12 t-dim" style="margin-bottom:6px">题干</div>
                <div class="callout" style="white-space:pre-wrap">${U.esc(full.stem || '')}</div>
              </div>
              <div id="wrongFig"></div>
              <div>
                <div class="fz-12 t-dim" style="margin-bottom:6px">${blank ? '填空答案' : '选项'}</div>
                ${optionHtml}
              </div>
              <div>
                <div class="fz-12 t-dim" style="margin-bottom:6px">解析</div>
                <div class="callout" style="white-space:pre-wrap">${U.esc(full.analysis || '暂无解析')}</div>
              </div>
            </div>`,
          onMount() {
            const figure = full.figureJson;
            const figEl = U.$('#wrongFig');
            if (!figEl || !figure) return;
            if (figure.imageUrl || figure.image_url) U.mountQuestionImage(figEl, figure.imageUrl || figure.image_url);
            else if (figure.graph && window.DsFigure) DsFigure.mount(figEl, figure.graph);
          },
        });
      }).catch(err => Toast.err('加载题目失败', err && err.message));
    }
  };

Router.register('analysis', { title: '归因与错题分析', mount: () => Analysis.render() });
