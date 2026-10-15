'use strict';

  function chaptersOf(courseId) {
    return API.teacher.resourceKps(courseId ? { courseId } : undefined)
      .then(d => (d && d.chapters) || [])
      .catch(() => []);
  }

  function chapterOptions(kps) {
    const normKey = ch => { const m = /第\s*(\d+)\s*章/.exec(ch || ''); return m ? '第' + m[1] + '章' : (ch || ''); };
    const seen = new Set();
    const options = [];
    (kps || []).map(c => c.chapter).filter(Boolean).forEach(ch => {
      const k = normKey(ch);
      if (k && !seen.has(k)) { seen.add(k); options.push({ value: k, label: ch }); }
    });
    return options;
  }

  function defaultReportTitle(courseName, dateText) {
    const name = String(courseName || '').trim();
    return (name ? name + ' · ' : '') + '学情分析报告 ' + dateText;
  }

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

  function _trReportHtml(raw) {
    const detail = raw && raw.detail && typeof raw.detail === 'object' ? raw.detail : (raw || {});
    const meta = detail.meta || {};
    const sections = Array.isArray(detail.sections) ? detail.sections : [];
    const title = raw.title || detail.title || '学情分析报告';
    const period = meta.period || ((meta.startDate || '') + (meta.endDate ? ' ~ ' + meta.endDate : '')) || '—';
    return {
      title,
      error: detail.error,
      html: `<div class="report">
        <div class="report__hd"><h2>${U.esc(title)}</h2>
          <div class="report__meta">
            <span>课程：${U.esc(meta.courseName || meta.className || '—')}</span>
            <span>人数：${U.esc(meta.studentCount != null && meta.studentCount !== '' ? meta.studentCount : '—')}</span>
            <span>章节：${U.esc(meta.chapter || '全课程')}</span>
            <span>区间：${U.esc(period)}</span>
            <span>生成者：${U.esc(meta.generator || '系统')}</span>
            <span>${U.esc(meta.generatedAt || '—')}</span></div></div>
        ${sections.map(s => `
          <h3>${U.esc(s.title)}</h3>
          ${(s.paragraphs || []).map(p => `<p>${U.esc(p)}</p>`).join('')}
          ${s.bullets && s.bullets.length ? `<ul>${s.bullets.map(b => `<li>${U.esc(b)}</li>`).join('')}</ul>` : ''}`).join('')}
      </div>`
    };
  }

  /* ================================================================
     视图 6 · 学情分析报告
     版式对齐学生端学情报告：左栏预览正文，右栏历史归档 + 快捷入口。
     生成仍走教师端配置弹窗（标题 / 章节 / 时间段 / 包含部分），课程取顶栏当前课。
     ================================================================ */
  const Report = {
    _viewingId: '',

    render() {
      const el = U.$('#view-report');
      if (!el) return;
      this._viewingId = '';
      el.innerHTML = `
      <div class="sr-page">
        <div class="grid g-21 sr-body">
          <div class="card sr-main">
            <div class="card__head"><h3>${icon('file')} 学情分析报告</h3>
              <span class="spacer"></span>
              <span class="fz-12 t-dim nowrap" id="srScope">当前课程 · 班级学情</span>
              <button class="btn btn--outline btn--sm" id="exPdf" type="button" hidden>${icon('download')} 导出 PDF</button>
              <button class="btn btn--outline btn--sm" id="exHtml" type="button" hidden>${icon('download')} 导出网页</button>
              <button class="btn btn--primary btn--sm" id="genReport" type="button">${icon('sparkle')} 生成报告</button></div>
            <div class="card__body" id="srPreview">${U.skeleton ? U.skeleton(220) : ''}</div>
          </div>
          <div class="card sr-side">
            <div class="card__head"><h3>${icon('calendar')} 历史归档</h3>
              <span class="spacer"></span>
              <span class="badge badge--outline" id="srArcBadge">—</span></div>
            <div class="card__body card__body--flush"><div class="list report-archive-list" id="repList"></div></div>
            <div class="sr-shortcuts">
              <button type="button" data-go="monitor">${icon('grid')} 打开学情监测看板<span>热力图 / 预警</span></button>
              <button type="button" data-go="analysis">${icon('flask')} 打开归因与错题分析<span>共性短板</span></button>
              <button type="button" data-go="dashboard">${icon('home')} 打开教学驾驶舱<span>班级概览</span></button>
            </div>
          </div>
        </div>
      </div>`;

      U.$('#genReport').addEventListener('click', () => this.openGen());
      U.$$('.sr-shortcuts [data-go]', el).forEach(b => {
        b.addEventListener('click', () => Router.go(b.dataset.go));
      });
      this._bindExport();
      this._paintEmpty('正在加载报告…', false);

      if (!API.config.activeCourseId) {
        U.$('#repList').innerHTML = `<div class="empty" style="padding:30px;text-align:center"><b>尚未创建或选择课程</b></div>`;
        this._paintEmpty('请先选择课程后再生成报告', false);
        return;
      }
      this.loadArchive();
    },

    _bindExport() {
      const exportFile = (format, selector, label) => {
        const reportId = this._viewingId;
        if (!reportId) { Toast.warn('请先打开一份报告'); return; }
        const button = U.$(selector);
        if (!button) return;
        const original = button.innerHTML;
        button.disabled = true;
        button.textContent = '生成中…';
        API.report.exportReport({ reportId, format })
          .then(file => {
            saveDownloadedFile(file, `report_${reportId}.${format}`);
            Toast.ok(label + '已下载', '文件已保存到浏览器默认下载目录');
          })
          .catch(err => Toast.warn(label + '失败：' + (err && err.message || err)))
          .finally(() => { button.disabled = false; button.innerHTML = original; });
      };
      const pdf = U.$('#exPdf'), html = U.$('#exHtml');
      if (pdf && !pdf.dataset.bound) {
        pdf.dataset.bound = '1';
        pdf.addEventListener('click', () => exportFile('pdf', '#exPdf', 'PDF'));
      }
      if (html && !html.dataset.bound) {
        html.dataset.bound = '1';
        html.addEventListener('click', () => exportFile('html', '#exHtml', '网页'));
      }
    },

    _paintEmpty(msg, showBtn) {
      const box = U.$('#srPreview');
      if (!box) return;
      box.innerHTML = `<div class="sr-empty">
        ${icon('file')}
        <b>还没有学情分析报告</b>
        <p>${U.esc(msg || '生成后将按当前课程真实学情汇总整体掌握度、共性短板、个体预警与目标达成度，便于教研与上报。')}</p>
        ${showBtn !== false ? `<button class="btn btn--primary" type="button" id="srEmptyGen">${icon('sparkle')} 生成本次报告</button>` : ''}
      </div>`;
      const btn = U.$('#srEmptyGen');
      if (btn) btn.addEventListener('click', () => this.openGen());
      this._setExportVisible(false);
    },

    _setExportVisible(on) {
      ['#exPdf', '#exHtml'].forEach(sel => {
        const el = U.$(sel);
        if (el) el.hidden = !on;
      });
    },

    loadArchive() {
      const listEl = U.$('#repList');
      if (!listEl) return Promise.resolve();
      return API.report.list({}).then(r => {
        const list = Array.isArray(r && r.list) ? r.list : [];
        const badge = U.$('#srArcBadge');
        if (badge) badge.textContent = `${list.length} 份`;
        if (!list.length) {
          listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">暂无历史报告</div>`;
          if (!this._viewingId) this._paintEmpty('点击右上角「生成报告」，按课程、章节与时间段汇总一份可导出的学情分析报告。', true);
          return;
        }
        listEl.innerHTML = list.map(rp => `
          <div class="list__item list__item--clickable${rp.reportId === this._viewingId ? ' is-active' : ''}" data-rid="${rp.reportId}">
            <span class="list__lead" style="color:var(--brand-400)">${icon('file')}</span>
            <div class="list__main"><b>${U.esc(rp.title)}</b>
              <p>${U.esc(rp.scope || '全课程')} · ${U.esc(rp.period || '')} · 由 ${U.esc(rp.creator || '系统')} 生成 · ${rp.pages || 0} 页</p></div>
            <div class="list__trail"><span class="badge ${rp.status === 'ready' ? 'badge--ok' : 'badge--outline'}">${rp.status === 'ready' ? '可查看' : '归档'}</span></div>
          </div>`).join('');
        U.$$('[data-rid]', listEl).forEach(b => b.addEventListener('click', () => this.openDetail(b.dataset.rid)));
        if (!this._viewingId && list[0]) this.openDetail(list[0].reportId);
      }).catch(() => {
        listEl.innerHTML = `<div class="empty" style="padding:30px;text-align:center">历史报告加载失败</div>`;
      });
    },

    async openGen() {
      const reportView = this;
      const courseAtOpen = API.config.activeCourseId, login = JSON.stringify(Auth.getSession());
      const isCurrent = () => login === JSON.stringify(Auth.getSession()) && Router.current === 'report';
      const allCourses = await API.course.my().then(r => Array.isArray(r) ? r : []).catch(() => []);
      if (!isCurrent() || courseAtOpen !== API.config.activeCourseId) return;
      const currentCourseId = API.config.activeCourseId || '';
      const currentCourse = allCourses.find(c => c.courseId === currentCourseId) || null;
      const today = new Date();
      const maxDate = formatDateInput(today);
      const minDateObj = new Date(today);
      minDateObj.setFullYear(today.getFullYear() - 1);
      const minDate = formatDateInput(minDateObj);
      const defaultStartObj = new Date(today);
      defaultStartObj.setDate(today.getDate() - 30);
      const defaultStart = formatDateInput(defaultStartObj < minDateObj ? minDateObj : defaultStartObj);
      const presetTitle = defaultReportTitle(currentCourse && currentCourse.name, maxDate);
      Modal.open({
        title: '生成学情分析报告',
        closeOnBackdrop: false,
        body: `<div class="stack" style="gap:14px">
          <div><p class="fz-12 t-dim" style="margin-bottom:6px">报告标题</p>
            <input class="input" id="rgTitle" type="text" maxlength="256" value="${U.esc(presetTitle)}" placeholder="${U.esc(presetTitle || '学情分析报告')}">
            <p class="fz-12 t-dim" style="margin-top:6px">按当前课程生成，可改标题；章节与学情数据不会混入其他课。</p></div>
          <div>
            <div class="report-scope-head">
              <p class="fz-12 t-dim" style="margin:0">统计范围（可多选章节）</p>
              <label class="report-scope-all"><input type="checkbox" id="rgScopeAll" checked><span>全选</span></label>
            </div>
            <div class="report-scope-list" id="rgScope"></div>
            <div class="report-scope-foot"><span id="rgScopeCount">加载章节…</span></div>
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
          const titleInput = U.$('#rgTitle', ov);
          const startInput = U.$('#rgStart', ov);
          const endInput = U.$('#rgEnd', ov);
          let generating = false;
          let scopeSeq = 0;
          const scopeInputs = () => U.$$('#rgScope input[name="rgChapter"]', ov);
          const allBox = U.$('#rgScopeAll', ov);
          const updateScopeCount = () => {
            const all = scopeInputs();
            const count = all.filter(input => input.checked).length;
            const countEl = U.$('#rgScopeCount', ov);
            const generateButton = U.$('#rgGo', ov);
            if (countEl) countEl.textContent = `已选 ${count} 个章节`;
            if (generateButton) generateButton.disabled = generating || count === 0;
            if (allBox) {
              allBox.disabled = all.length === 0;
              allBox.checked = all.length > 0 && count === all.length;
              allBox.indeterminate = count > 0 && count < all.length;
            }
          };
          const paintChapters = (options, emptyHint) => {
            const box = U.$('#rgScope', ov);
            if (!box) return;
            if (!options.length) {
              const waiting = emptyHint && emptyHint.indexOf('正在加载') >= 0;
              box.innerHTML = `<div class="t-dim fz-12" style="padding:8px 0">${U.esc(emptyHint || '该课程还没有章节，将按全课程统计。')}</div>` +
                (waiting ? '' : `<label class="report-scope-option"><input type="checkbox" name="rgChapter" value="全课程" checked><span>全课程</span></label>`);
            } else {
              box.innerHTML = options.map(c => `<label class="report-scope-option" title="${U.esc(c.label)}">
                <input type="checkbox" name="rgChapter" value="${U.esc(c.value)}" checked>
                <span>${U.esc(c.label)}</span>
              </label>`).join('');
            }
            scopeInputs().forEach(input => input.addEventListener('change', updateScopeCount));
            updateScopeCount();
          };
          const loadChapters = (courseId) => {
            const seq = ++scopeSeq;
            paintChapters([], '正在加载该课程的章节…');
            if (!courseId) {
              paintChapters([], '请先选择课程');
              return;
            }
            chaptersOf(courseId).then(kps => {
              if (seq !== scopeSeq || !isCurrent()) return;
              paintChapters(chapterOptions(kps));
            });
          };
          const syncDateRange = () => {
            if (!startInput || !endInput) return;
            endInput.min = startInput.value || minDate;
            startInput.max = endInput.value || maxDate;
            if (startInput.value && endInput.value && startInput.value > endInput.value) {
              endInput.value = startInput.value;
            }
          };
          if (allBox) {
            allBox.addEventListener('change', () => {
              const on = allBox.checked;
              allBox.indeterminate = false;
              scopeInputs().forEach(input => { input.checked = on; });
              updateScopeCount();
            });
          }
          startInput && startInput.addEventListener('change', syncDateRange);
          endInput && endInput.addEventListener('change', syncDateRange);
          loadChapters(currentCourseId);
          syncDateRange();
          U.$('#rgGo', ov).addEventListener('click', () => {
            if (generating || reportView._generating || !isCurrent() || courseAtOpen !== API.config.activeCourseId) return;
            const selectedChapters = scopeInputs().filter(input => input.checked).map(input => input.value);
            const startDate = startInput && startInput.value;
            const endDate = endInput && endInput.value;
            const title = ((titleInput && titleInput.value) || '').trim();
            if (!title) return Toast.warn('请填写报告标题');
            if (!selectedChapters.length) return Toast.warn('请至少选择一个统计章节');
            if (!startDate || !endDate) return Toast.warn('请选择完整的日期范围');
            if (startDate > endDate) return Toast.warn('开始日期不能晚于结束日期');
            if (startDate < minDate || endDate > maxDate) return Toast.warn('请选择最近一年内的日期');
            const sections = U.$$('#rgSec .chip.is-active', ov).map(c => c.textContent);
            if (!sections.length) return Toast.warn('请至少选择一个报告部分');
            const courseId = currentCourseId;
            if (!courseId) return Toast.warn('请先选择或创建课程');
            generating = true;
            const button = U.$('#rgGo', ov), original = button.innerHTML;
            button.disabled = true; button.textContent = '生成中…';
            reportView._generating = API.report.generate({
              courseId, classIds: [courseId], title,
              chapter: selectedChapters.join('、'),
              startDate, endDate, sections
            }).then(async r => {
              const error = r && r.detail && r.detail.error;
              if (!r || r.status === 'error' || error || !r.reportId) {
                if (isCurrent() && courseId === API.config.activeCourseId) Toast.warn(error || '报告生成失败，请稍后重试');
                return false;
              }
              if (isCurrent() && courseId === API.config.activeCourseId) {
                Toast.ok('报告已生成');
                close();
                reportView._viewingId = r.reportId;
                await reportView.loadArchive();
                if (isCurrent() && courseId === API.config.activeCourseId) await reportView.openDetail(r.reportId);
              }
              return true;
            }).catch(err => { if (isCurrent() && courseId === API.config.activeCourseId) Toast.warn('报告生成失败：' + (err.message || err)); return false; })
              .finally(() => { generating = false; reportView._generating = null; button.innerHTML = original; updateScopeCount(); });
          });
        }
      });
    },

    openDetail(reportId) {
      const courseId = API.config.activeCourseId, login = JSON.stringify(Auth.getSession());
      return API.report.detail({ reportId }).then(raw => {
        if (courseId !== API.config.activeCourseId || login !== JSON.stringify(Auth.getSession()) || Router.current !== 'report') return;
        const painted = _trReportHtml(raw);
        if (painted.error) return Toast.warn(painted.error);
        this._viewingId = reportId;
        const preview = U.$('#srPreview');
        if (preview) {
          preview.innerHTML = painted.html;
          this._setExportVisible(true);
          this._bindExport();
          U.$$('#repList [data-rid]').forEach(item => {
            item.classList.toggle('is-active', item.dataset.rid === reportId);
          });
          return;
        }
        Modal.open({
          title: U.esc(painted.title), size: 'wide',
          body: painted.html,
          footer: `<button class="btn" data-close>关闭</button>
            <button class="btn btn--outline" id="exPdf">${icon('download')} 导出 PDF</button>
            <button class="btn btn--primary" id="exHtml">${icon('download')} 导出网页</button>`,
          onMount: (ov) => {
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
                .catch(err => Toast.warn(label + '失败：' + (err && err.message || err)))
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
