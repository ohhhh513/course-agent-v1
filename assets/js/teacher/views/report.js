'use strict';

  /* ================================================================
     视图 6 · 学情分析报告
     ================================================================ */
  const Report = {
    render() {
      const el = U.$('#view-report');
      el.innerHTML = `
      <div class="grid g-21" style="margin-bottom:16px">
        <div class="card">
          <div class="card__head"><h3>${icon('file')} 学情分析报告</h3><span class="spacer"></span>
            <button class="btn btn--primary btn--sm" id="genReport">${icon('sparkle')} 一键生成报告</button></div>
          <div class="card__body">
            <p class="fz-13 t-2" style="line-height:1.8">基于班级 / 章节 / 时间段，自动汇总<b>整体掌握度、共性短板、个体预警、干预效果、目标达成度</b>，支持 PDF / 网页导出，便于教研与上报。</p>
            <div class="divider"></div>
            <div class="row fz-12 t-dim"><span>覆盖章节</span><span class="spacer"></span><span>第1章 ~ 第5章 · 6 个知识点</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card__head"><h3>${icon('calendar')} 历史归档</h3></div>
          <div class="card__body card__body--flush"><div class="list" id="repList"></div></div>
        </div>
      </div>`;

      U.$('#genReport').addEventListener('click', () => this.openGen());
      API.report.list({ classId: state.classId }).then(r => {
        U.$('#repList').innerHTML = r.list.map(rp => `
          <div class="list__item list__item--clickable" data-rid="${rp.reportId}">
            <span class="list__lead" style="color:var(--brand-400)">${icon('file')}</span>
            <div class="list__main"><b>${U.esc(rp.title)}</b>
              <p>${rp.scope} · ${rp.period} · 由 ${rp.creator} 生成 · ${rp.pages} 页</p></div>
            <div class="list__trail"><span class="badge ${rp.status === 'ready' ? 'badge--ok' : 'badge--outline'}">${rp.status === 'ready' ? '可查看' : '归档'}</span></div>
          </div>`).join('');
        U.$$('[data-rid]', el).forEach(b => b.addEventListener('click', () => this.openDetail(b.dataset.rid)));
      });
    },

    async openGen() {
      const [classes, kps] = await Promise.all([
        API.teacher.classes().then(r => Array.isArray(r) ? r : ((r && r.list) || [])).catch(() => []),
        API.teacher.resourceKps().then(d => (d && d.chapters) || []).catch(() => [])
      ]);
      // 章节下拉从知识图谱动态派生（避免写死导致缺章）；名称表覆盖本课程 7 章
      const CH_NAME = {
        '第1章': '第1章 绪论', '第2章': '第2章 线性表', '第3章': '第3章 栈与队列',
        '第4章': '第4章 树与二叉树', '第5章': '第5章 图', '第6章': '第6章 查找', '第7章': '第7章 排序'
      };
      const chapters = kps.map(c => CH_NAME[c.chapter] || c.chapter).concat(['全课程']);
      Modal.open({
        title: '生成学情分析报告',
        body: `<div class="stack" style="gap:14px">
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">选择班级</p>
            <select class="select" id="rgClass">${classes.map(c => `<option value="${c.classId}">${c.name}</option>`).join('')}</select></div>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">统计范围</p>
            <select class="select" id="rgChapter">${chapters.map(c => `<option>${c}</option>`).join('')}</select></div>
          <div class="grid g-2"><div>
            <p class="fz-12 t-dim" style="margin-bottom:6px">开始日期</p><input class="input" id="rgStart" value="2026-08-15"></div>
            <div><p class="fz-12 t-dim" style="margin-bottom:6px">结束日期</p><input class="input" id="rgEnd" value="2026-08-28"></div></div>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">包含章节（可多选）</p>
            <div class="chips" id="rgSec">
              <button class="chip is-active">整体掌握度</button><button class="chip is-active">共性短板归因</button>
              <button class="chip is-active">个体预警</button><button class="chip is-active">干预效果</button><button class="chip is-active">目标达成度</button></div></div>
        </div>`,
        footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="rgGo">${icon('sparkle')} 生成</button>`,
        onMount(ov, close) {
          U.$$('#rgSec .chip', ov).forEach(c => c.addEventListener('click', () => c.classList.toggle('is-active')));
          U.$('#rgGo', ov).addEventListener('click', () => {
            const sections = U.$$('#rgSec .chip.is-active', ov).map(c => c.textContent);
            API.report.generate({
              classIds: [U.$('#rgClass', ov).value], chapter: U.$('#rgChapter', ov).value,
              startDate: U.$('#rgStart', ov).value, endDate: U.$('#rgEnd', ov).value, sections
            }).then(r => { Toast.ok('报告已生成', r.reportId); close(); this.openDetail(r.reportId); });
          });
        }
      });
    },

    openDetail(reportId) {
      const load = (id) => API.report.detail({ reportId: id });
      load(reportId).then(d => {
        Modal.open({
          title: d.title, size: 'wide',
          body: `<div class="report">
            <div class="report__hd"><h2>${U.esc(d.title)}</h2>
              <div class="report__meta">
                <span>班级：${d.meta.className}</span><span>人数：${d.meta.studentCount}</span>
                <span>章节：${d.meta.chapter}</span><span>区间：${d.meta.period}</span>
                <span>生成：${d.meta.generatedAt}</span><span>${d.meta.generator}</span></div></div>
            ${d.sections.map(s => `
              <h3>${U.esc(s.title)}</h3>
              ${s.paragraphs.map(p => `<p>${U.esc(p)}</p>`).join('')}
              ${s.bullets && s.bullets.length ? `<ul>${s.bullets.map(b => `<li>${U.esc(b)}</li>`).join('')}</ul>` : ''}`).join('')}
          </div>`,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="exPdf">${icon('download')} 导出 PDF</button>
            <button class="btn btn--primary" id="exHtml">${icon('download')} 导出网页</button>`,
          onMount(ov, close) {
            U.$('#exPdf', ov).addEventListener('click', () => API.report.exportReport({ reportId, format: 'pdf' }).then(r => Toast.ok('PDF 已导出', r.url)));
            U.$('#exHtml', ov).addEventListener('click', () => API.report.exportReport({ reportId, format: 'html' }).then(r => Toast.ok('网页版已导出', r.url)));
          }
        });
      });
    }
  };



Router.register('report', { title: '学情分析报告', mount: () => Report.render() });
