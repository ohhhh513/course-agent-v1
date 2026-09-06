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
            <p class="fz-13 t-2" style="line-height:1.8">基于班级 / 章节 / 时间段，自动汇总<b>整体掌握度、共性短板、个体预警、干预效果、目标达成度</b>，支持 PDF / 网页导出，便于教研与上报。</p>
            <div class="divider"></div>
            <div class="row fz-12 t-dim"><span>覆盖章节</span><span class="spacer"></span><span>第1章 ~ 第9章 · 25 个知识点</span></div>
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
      // 与学生端「学习资源」中的课程章节保持完全一致，不能按接口返回的字典序排列，
      // 也不能只依赖当前已有知识点，否则会漏掉暂时还没有数据的章节。
      const CHAPTER_ORDER = [
        ['第1章', '第1章 绪论'], ['第2章', '第2章 线性表'], ['第3章', '第3章 栈和队列'],
        ['第4章', '第4章 串'], ['第5章', '第5章 数组和广义表'], ['第6章', '第6章 树和二叉树'],
        ['第7章', '第7章 图'], ['第8章', '第8章 查找'], ['第9章', '第9章 排序']
      ].map(([value, label]) => ({ value, label }));
      const knownChapters = new Set(CHAPTER_ORDER.map(c => c.value));
      const extraOptions = kps
        .map(c => ({ value: c.chapter, label: c.chapter }))
        .filter((c, i, arr) => c.value && !knownChapters.has(c.value) && arr.findIndex(x => x.value === c.value) === i);
      // 当前报告接口以 chapter 字段承载统计范围；复选框保留多选能力。
      const courseOptions = CHAPTER_ORDER.concat(extraOptions);
      const scopeOptions = courseOptions.length ? courseOptions : [{ value: '全课程', label: '全课程' }];
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
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">选择班级</p>
            <select class="select" id="rgClass">${classes.map(c => `<option value="${U.esc(c.classId)}">${U.esc(c.name)}</option>`).join('')}</select></div>
          <div>
            <p class="fz-12 t-dim" style="margin-bottom:6px">统计范围（可多选课程）</p>
            <div class="report-scope-list" id="rgScope">
              ${scopeOptions.map(c => `<label class="report-scope-option" title="${U.esc(c.label)}">
                <input type="checkbox" name="rgCourse" value="${U.esc(c.value)}" checked>
                <span>${U.esc(c.label)}</span>
              </label>`).join('')}
            </div>
            <div class="report-scope-foot"><span id="rgScopeCount">已选 ${scopeOptions.length} 个课程</span><span>可多选</span></div>
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
              <button class="chip is-active">个体预警</button><button class="chip is-active">干预效果</button><button class="chip is-active">目标达成度</button></div></div>
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
            if (countEl) countEl.textContent = `已选 ${count} 个课程`;
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
            if (!selectedCourses.length) return Toast.warn('请至少选择一个统计课程');
            if (!startDate || !endDate) return Toast.warn('请选择完整的日期范围');
            if (startDate > endDate) return Toast.warn('开始日期不能晚于结束日期');
            const sections = U.$$('#rgSec .chip.is-active', ov).map(c => c.textContent);
            API.report.generate({
              classIds: [U.$('#rgClass', ov).value], chapter: selectedCourses.join('、'),
              startDate, endDate, sections
            }).then(r => { Toast.ok('报告已生成', r.reportId); close(); this.openDetail(r.reportId); });
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
                <span>班级：${U.esc(meta.className || '—')}</span><span>人数：${U.esc(meta.studentCount ?? '—')}</span>
                <span>章节：${U.esc(meta.chapter || '全课程')}</span><span>区间：${U.esc(meta.period || ((meta.startDate || '') + (meta.endDate ? ' ~ ' + meta.endDate : '')) || '—')}</span>
                <span>生成：${U.esc(meta.generatedAt || '—')}</span><span>${U.esc(meta.generator || '系统')}</span></div></div>
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
