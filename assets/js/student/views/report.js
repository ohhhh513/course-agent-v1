'use strict';

/* ================================================================
   视图 8 · 学情报告（学生自助）
   生成 / 查看 / 导出**当前登录学生自己**的报告。
   接口走 /student/reports/*（与教师端的 /report/* 不是同一组；
   教师前缀对学生一律 403，归属校验在学生侧这组接口里做）。
   报告正文由后端按真实学情统计拼装，前端只负责渲染与下载。
   ================================================================ */

/** 把导出接口返回的 blob 存成文件（与教师端报告页同一实现） */
function saveMyReportFile(file, fallbackName) {
  if (!file || !file.blob) throw new Error('导出接口未返回文件');
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename || fallbackName;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const MyReport = {
  render() {
    const el = U.$('#view-report');
    el.innerHTML = `
    <div class="grid g-21" style="margin-bottom:16px">
      <div class="card">
        <div class="card__head"><h3>${icon('file')} 个人学情报告</h3><span class="spacer"></span>
          <button class="btn btn--primary btn--sm" id="genMyReport">${icon('sparkle')} 生成报告</button></div>
        <div class="card__body">
          <div class="row fz-12 t-dim"><span>统计范围</span><span class="spacer"></span><span>本人 · 当前课程</span></div>
        </div>
      </div>
      <div class="card">
        <div class="card__head"><h3>${icon('calendar')} 历史归档</h3></div>
        <div class="card__body card__body--flush"><div class="list report-archive-list" id="myRepList"></div></div>
      </div>
    </div>`;

    U.$('#genMyReport').addEventListener('click', () => this.generate());
    if (!API.config.activeCourseId) {
      U.$('#myRepList').innerHTML = `<div class="empty" style="padding:30px;text-align:center"><b>尚未创建或选择课程</b></div>`;
      return;
    }
    this.loadArchive();
  },

  loadArchive() {
    const listEl = U.$('#myRepList');
    if (!listEl) return Promise.resolve();
    return API.student.report.list({}).then(r => {
      const list = Array.isArray(r && r.list) ? r.list : [];
      if (!list.length) {
        listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">暂无报告</div>`;
        return;
      }
      listEl.innerHTML = list.map(rp => `
        <div class="list__item list__item--clickable" data-rid="${rp.reportId}">
          <span class="list__lead" style="color:var(--brand-400)">${icon('file')}</span>
          <div class="list__main"><b>${U.esc(rp.title)}</b>
            <p>${U.esc(rp.scope || '全课程')} · ${U.esc(rp.createdAt || '')} 生成 · ${rp.pages || 0} 页</p></div>
          <div class="list__trail"><span class="badge badge--ok">可查看</span></div>
        </div>`).join('');
      U.$$('[data-rid]', listEl).forEach(b => b.addEventListener('click', () => this.openDetail(b.dataset.rid)));
    }).catch(() => {
      listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">历史报告加载失败</div>`;
    });
  },

  generate() {
    if (this._generating) return this._generating;
    const btn = U.$('#genMyReport');
    if (!API.config.activeCourseId) { Toast.warn('请先选择课程'); return Promise.resolve(false); }
    const courseId = API.config.activeCourseId;
    const login = JSON.stringify(Auth.getSession());
    const isCurrent = () => courseId === API.config.activeCourseId && login === JSON.stringify(Auth.getSession()) && Router.current === 'report';
    if (btn) { btn.disabled = true; btn.textContent = '生成中…'; }
    this._generating = API.student.report.generate()
      .then(async r => {
        const reportId = r && r.reportId;
        if (!reportId) { if (isCurrent()) Toast.warn('报告生成失败，请稍后重试'); return false; }
        if (isCurrent()) {
          Toast.ok('报告已生成');
          await this.loadArchive();
          if (isCurrent()) await this.openDetail(reportId);
        }
        return true;
      })
      .catch(err => { if (isCurrent()) Toast.warn('报告生成失败：' + (err && err.message || err)); return false; })
      .finally(() => {
        this._generating = null;
        if (btn) { btn.disabled = false; btn.innerHTML = `${icon('sparkle')} 生成报告`; }
      });
    return this._generating;
  },

  openDetail(reportId) {
    const courseId = API.config.activeCourseId, login = JSON.stringify(Auth.getSession());
    return API.student.report.detail({ reportId }).then(raw => {
      if (courseId !== API.config.activeCourseId || login !== JSON.stringify(Auth.getSession()) || Router.current !== 'report') return;
      const detail = raw && raw.detail && typeof raw.detail === 'object' ? raw.detail : (raw || {});
      if (detail.error) return Toast.warn(detail.error);
      const meta = detail.meta || {};
      const sections = Array.isArray(detail.sections) ? detail.sections : [];
      const title = raw.title || detail.title || '个人学情报告';
      Modal.open({
        title: U.esc(title), size: 'wide',
        body: `<div class="report">
          <div class="report__hd"><h2>${U.esc(title)}</h2>
            <div class="report__meta">
              <span>课程：${U.esc(meta.courseName || meta.className || '—')}</span>
              <span>学号：${U.esc(meta.studentNo || '—')}</span>
              <span>章节：${U.esc(meta.chapter || '全课程')}</span>
              <span>生成者：${U.esc(meta.generator || '系统')}</span>
              <span>${U.esc(meta.generatedAt || '—')}</span></div></div>
          ${sections.map(s => `
            <h3>${U.esc(s.title)}</h3>
            ${(s.paragraphs || []).map(p => `<p>${U.esc(p)}</p>`).join('')}
            ${s.bullets && s.bullets.length ? `<ul>${s.bullets.map(b => `<li>${U.esc(b)}</li>`).join('')}</ul>` : ''}`).join('')}
        </div>`,
        footer: `<button class="btn" data-close>关闭</button>
          <button class="btn btn--outline" id="myExPdf">${icon('download')} 导出 PDF</button>
          <button class="btn btn--primary" id="myExHtml">${icon('download')} 导出网页</button>`,
        onMount(ov) {
          const exportFile = (format, selector, label) => {
            const button = U.$(selector, ov);
            const original = button.innerHTML;
            button.disabled = true;
            button.textContent = '生成中…';
            API.student.report.exportReport({ reportId, format })
              .then(file => {
                saveMyReportFile(file, `report_${reportId}.${format}`);
                Toast.ok(label + '已下载', '文件已保存到浏览器默认下载目录');
              })
              .catch(err => Toast.warn(label + '失败：' + (err && err.message || err)))
              .finally(() => { button.disabled = false; button.innerHTML = original; });
          };
          U.$('#myExPdf', ov).addEventListener('click', () => exportFile('pdf', '#myExPdf', 'PDF'));
          U.$('#myExHtml', ov).addEventListener('click', () => exportFile('html', '#myExHtml', '网页'));
        }
      });
    }).catch(err => Toast.warn('报告加载失败：' + (err && err.message || err)));
  }
};

Router.register('report', { title: '学情报告', mount: () => MyReport.render() });
