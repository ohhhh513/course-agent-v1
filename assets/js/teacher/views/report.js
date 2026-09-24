'use strict';

  function formatDateInput(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function saveDownloadedFile(file, fallbackName) {
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
            <p class="fz-13 t-2" style="line-height:1.8">基于课程 / 章节 / 时间段，自动汇总<b>整体掌握度、共性短板、个体预警、目标达成度</b>，支持 PDF / 网页导出，便于教研与上报。</p>
            <div class="divider"></div>
            <div class="row fz-12 t-dim"><span>数据来源</span><span class="spacer"></span><span>当前课程真实学情记录</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card__head"><h3>${icon('calendar')} 历史归档</h3></div>
          <div class="card__body card__body--flush"><div class="list report-archive-list" id="repList"></div></div>
        </div>
      </div>`;

      U.$('#genReport').addEventListener('click', () => this.openGen());
      if (!API.config.activeCourseId) {
        U.$('#repList').innerHTML = `<div class="empty" style="padding:30px;text-align:center"><b>尚未创建或选择课程</b></div>`;
        return;
      }
      this.loadArchive();
    },

    loadArchive() {
      const listEl = U.$('#repList');
      if (!listEl) return Promise.resolve();
      return API.report.list({}).then(r => {
        const list = Array.isArray(r && r.list) ? r.list : [];
        if (!list.length) {
          listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">暂无历史报告</div>`;
          return;
        }
        listEl.innerHTML = list.map(rp => `
          <div class="list__item list__item--clickable" data-rid="${rp.reportId}">
            <span class="list__lead" style="color:var(--brand-400)">${icon('file')}</span>
            <div class="list__main"><b>${U.esc(rp.title)}</b>
              <p>${U.esc(rp.scope || '全课程')} · ${U.esc(rp.period || '')} · 由 ${U.esc(rp.creator || '系统')} 生成 · ${rp.pages || 0} 页</p></div>
            <div class="list__trail"><span class="badge ${rp.status === 'ready' ? 'badge--ok' : 'badge--outline'}">${rp.status === 'ready' ? '可查看' : '归档'}</span></div>
          </div>`).join('');
        U.$$('[data-rid]', listEl).forEach(b => b.addEventListener('click', () => this.openDetail(b.dataset.rid)));
      }).catch(() => {
        listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">历史报告加载失败</div>`;
      });
    },

    async openGen() {
      const reportView = this;
      const [courses, kps] = await Promise.all([
        API.course.my().then(r => Array.isArray(r) ? r : []).catch(() => []),
        API.teacher.resourceKps().then(d => (d && d.chapters) || []).catch(() => [])
      ]);
      const currentCourseId = API.config.activeCourseId || (courses[0] && courses[0].courseId) || '';
      const courseOptions = courses.length ? courses : (currentCourseId ? [{ courseId: currentCourseId, name: currentCourseId }] : []);
      // 统计范围（章节）以真实图谱章节为准，按「第N章」归一去重，避免短名与全名同显造成重复。
      const normKey = ch => { const m = /第\s*(\d+)\s*章/.exec(ch || ''); return m ? '第' + m[1] + '章' : (ch || ''); };
      const seen = new Set();
      const scopeOptions = [];
      (kps || []).map(c => c.chapter).filter(Boolean).forEach(ch => {
        const k = normKey(ch);
        if (k && !seen.has(k)) { seen.add(k); scopeOptions.push({ value: k, label: ch }); }
      });
      if (!scopeOptions.length) scopeOptions.push({ value: '全课程', label: '全课程' });
      const today = new Date();
      const maxDate = formatDateInput(today);
      const minDateObj = new Date(today);
      minDateObj.setFullYear(today.getFullYear() - 1);
      const minDate = formatDateInput(minDateObj);
      const defaultStartObj = new Date(today);
      defaultStartObj.setDate(today.getDate() - 30);
      const defaultStart = formatDateInput(defaultStartObj < minDateObj ? minDateObj : defaultStartObj);
      Modal.open({
        title: '生成学情分析报告',
        body: `<div class="stack" style="gap:14px">
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">选择课程</p>
            <select class="select" id="rgCourse">${courseOptions.map(c => `<option value="${U.esc(c.courseId)}"${c.courseId === currentCourseId ? ' selected' : ''}>${U.esc(c.name || c.courseId)}</option>`).join('') || '<option value="">（暂无课程）</option>'}</select></div>
          <div>
            <p class="fz-12 t-dim" style="margin-bottom:6px">统计范围（可多选章节，默认全选）</p>
            <div class="report-scope-list" id="rgScope">
              ${scopeOptions.map(c => `<label class="report-scope-option" title="${U.esc(c.label)}">
                <input type="checkbox" name="rgCourse" value="${U.esc(c.value)}" checked>
                <span>${U.esc(c.label)}</span>
              </label>`).join('')}
            </div>
            <div class="report-scope-foot"><span id="rgScopeCount">已选 ${scopeOptions.length} 个章节</span><span>可多选</span></div>
          </div>
          <div class="grid g-2 report-date-grid"><div>
            <p class="fz-12 t-dim" style="margin-bottom:6px">开始日期</p>
            <input class="input" id="rgStart" type="date" min="${minDate}" max="${maxDate}" value="${defaultStart}"></div>
            <div><p class="fz-12 t-dim" style="margin-bottom:6px">结束日期</p>
            <input class="input" id="rgEnd" type="date" min="${minDate}" max="${maxDate}" value="${maxDate}"></div></div>
          <p class="report-date-tip">可选择最近一年内的日期，不能选择未来日期</p>
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">包含章节（可多选）</p>
            <div class="chips" id="rgSec">
              <button class="chip is-active">整体掌握度</button><button class="chip is-active">共性短板归因</button>
              <button class="chip is-active">个体预警</button><button class="chip is-active">目标达成度</button></div></div>
        </div>`,
        footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="rgGo">${icon('sparkle')} 生成</button>`,
        onMount(ov, close) {
          U.$$('#rgSec .chip', ov).forEach(c => c.addEventListener('click', () => c.classList.toggle('is-active')));
          const scopeInputs = U.$$('#rgScope input[name="rgCourse"]', ov);
          const startInput = U.$('#rgStart', ov);
          const endInput = U.$('#rgEnd', ov);
          const updateScopeCount = () => {
            const count = scopeInputs.filter(input => input.checked).length;
            const countEl = U.$('#rgScopeCount', ov);
            const generateButton = U.$('#rgGo', ov);
            if (countEl) countEl.textContent = `已选 ${count} 个章节`;
            if (generateButton) generateButton.disabled = count === 0;
          };
          const syncDateRange = () => {
            if (!startInput || !endInput) return;
            endInput.min = startInput.value || minDate;
            startInput.max = endInput.value || maxDate;
            if (startInput.value && endInput.value && startInput.value > endInput.value) {
              endInput.value = startInput.value;
            }
          };
          scopeInputs.forEach(input => input.addEventListener('change', updateScopeCount));
          startInput && startInput.addEventListener('change', syncDateRange);
          endInput && endInput.addEventListener('change', syncDateRange);
          updateScopeCount();
          syncDateRange();
          U.$('#rgGo', ov).addEventListener('click', () => {
            const selectedCourses = scopeInputs.filter(input => input.checked).map(input => input.value);
            const startDate = startInput && startInput.value;
            const endDate = endInput && endInput.value;
            if (!selectedCourses.length) return Toast.warn('请至少选择一个统计章节');
            if (!startDate || !endDate) return Toast.warn('请选择完整的日期范围');
            if (startDate > endDate) return Toast.warn('开始日期不能晚于结束日期');
            const sections = U.$$('#rgSec .chip.is-active', ov).map(c => c.textContent);
            if (!sections.length) return Toast.warn('请至少选择一个报告部分');
            const courseId = U.$('#rgCourse', ov).value || currentCourseId;
            if (!courseId) return Toast.warn('请先选择或创建课程');
            if (API.setActiveCourse) API.setActiveCourse(courseId);
            API.report.generate({
              classIds: [courseId], chapter: selectedCourses.join('、'),
              startDate, endDate, sections
            }).then(async r => {
              const error = r && r.detail && r.detail.error;
              if (!r || r.status === 'error' || error || !r.reportId) {
                return Toast.warn(error || '报告生成失败，请稍后重试');
              }
              Toast.ok('报告已生成', r.reportId);
              close();
              await reportView.loadArchive();
              reportView.openDetail(r.reportId);
            }).catch(err => Toast.warn('报告生成失败：' + (err.message || err)));
          });
        }
      });
    },

    openDetail(reportId) {
      const load = (id) => API.report.detail({ reportId: id });
      load(reportId).then(raw => {
        // 后端返回 { reportId, title, status, detail: { meta, sections } }，mock 则可能直接返回详情
        const detail = raw && raw.detail && typeof raw.detail === 'object' ? raw.detail : (raw || {});
        if (detail.error) return Toast.warn(detail.error);
        const d = {
          ...detail,
          title: raw.title || detail.title || '学情分析报告',
          meta: detail.meta || {},
          sections: Array.isArray(detail.sections) ? detail.sections : [],
        };
        const meta = d.meta;
        Modal.open({
          title: U.esc(d.title), size: 'wide',
          body: `<div class="report">
            <div class="report__hd"><h2>${U.esc(d.title)}</h2>
              <div class="report__meta">
                <span>课程：${U.esc(meta.courseName || meta.className || '—')}</span>
                <span>人数：${U.esc(meta.studentCount != null && meta.studentCount !== '' ? meta.studentCount : '—')}</span>
                <span>章节：${U.esc(meta.chapter || '全课程')}</span>
                <span>区间：${U.esc(meta.period || ((meta.startDate || '') + (meta.endDate ? ' ~ ' + meta.endDate : '')) || '—')}</span>
                <span>生成者：${U.esc(meta.generator || '系统')}</span>
                <span>${U.esc(meta.generatedAt || '—')}</span></div></div>
            ${d.sections.map(s => `
              <h3>${U.esc(s.title)}</h3>
              ${(s.paragraphs || []).map(p => `<p>${U.esc(p)}</p>`).join('')}
              ${s.bullets && s.bullets.length ? `<ul>${s.bullets.map(b => `<li>${U.esc(b)}</li>`).join('')}</ul>` : ''}`).join('')}
          </div>`,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="exPdf">${icon('download')} 导出 PDF</button>
            <button class="btn btn--primary" id="exHtml">${icon('download')} 导出网页</button>`,
          onMount(ov, close) {
            const exportFile = (format, selector, label) => {
              const button = U.$(selector, ov);
              const original = button.innerHTML;
              button.disabled = true;
              button.textContent = '生成中…';
              API.report.exportReport({ reportId, format })
                .then(file => {
                  saveDownloadedFile(file, `report_${reportId}.${format}`);
                  Toast.ok(label + '已下载', '文件已保存到浏览器默认下载目录');
                })
                .catch(err => Toast.warn(label + '失败：' + (err.message || err)))
                .finally(() => { button.disabled = false; button.innerHTML = original; });
            };
            U.$('#exPdf', ov).addEventListener('click', () => exportFile('pdf', '#exPdf', 'PDF'));
            U.$('#exHtml', ov).addEventListener('click', () => exportFile('html', '#exHtml', '网页'));
          }
        });
      }).catch(err => Toast.warn('报告加载失败：' + (err.message || err)));
    }
  };



Router.register('report', { title: '学情分析报告', mount: () => Report.render() });
