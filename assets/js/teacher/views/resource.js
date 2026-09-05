'use strict';

  /* ================================================================
     教师视图 · 资源管理
     - 列出所有学习资源（含封面、时长/页数、观看次数）
     - 支持上传新资源（MP4/PDF/PPT/DOC）并挂载知识点
     - 支持删除资源
     ================================================================ */
  const TeacherResource = {
    keyword: '',
    _kps: [],

    render() {
      const el = U.$('#view-resource');
      el.innerHTML = `
      <div class="card">
        <div class="card__head">
          <h3>${icon('folder')} 资源管理</h3>
          <span class="spacer"></span>
          <div class="search" style="width:220px;margin-right:10px">
            ${icon('search2')}<input class="input" id="trSearch" placeholder="搜索资源标题 / 知识点">
          </div>
          <button class="btn btn--primary" id="trUpload" type="button">${icon('upload')} 上传资源</button>
        </div>
        <div class="card__body">
          <div class="res-grid" id="trGrid">${U.skeleton(200)}</div>
        </div>
      </div>`;

      let tm;
      U.$('#trSearch').addEventListener('input', e => {
        clearTimeout(tm);
        tm = setTimeout(() => { this.keyword = e.target.value.trim(); this.load(); }, 260);
      });
      U.$('#trUpload').addEventListener('click', () => this.openUploadModal());

      this.load();
      this._fetchKps();
    },

    _fetchKps() {
      API.teacher.resourceKps().then(d => {
        this._kps = d.chapters || [];
      }).catch(() => {});
    },

    load() {
      API.teacher.resources({ keyword: this.keyword }).then(r => {
        const box = U.$('#trGrid');
        if (!box) return;
        const list = r.list || [];
        if (!list.length) {
          box.innerHTML = R.empty('暂无资源', this.keyword ? '没有匹配到搜索条件' : '点击右上角上传第一个资源', 'folder');
          return;
        }
        box.innerHTML = list.map(x => this._card(x)).join('');
        U.$$('.tr-del', box).forEach(b => b.addEventListener('click', e => {
          e.stopPropagation();
          const rid = b.dataset.res;
          if (confirm(`确定删除资源「${b.dataset.title}」吗？\n删除后学生端将不可见。`)) {
            API.teacher.deleteResource(rid).then(() => {
              Toast.ok('已删除');
              this.load();
            }).catch(err => Toast.error('删除失败', err && err.message || ''));
          }
        }));
      }).catch(err => {
        const box = U.$('#trGrid');
        if (box) box.innerHTML = `<div class="empty">${icon('alert')}<b>加载失败</b><p>${U.esc(err && err.message || '')}</p></div>`;
      });
    },

    _card(r) {
      const label = { video: '教学视频', ppt: '课堂PPT', doc: '教材文献', quiz: '题库' };
      const meta = r.duration ? r.duration : (r.pages ? `${r.pages} 页` : '—');
      return `
      <div class="res tr-res" data-res="${r.resId}">
        <button class="btn btn--ghost btn--icon btn--sm tr-del" data-res="${r.resId}" data-title="${U.esc(r.title)}" title="删除">${icon('x')}</button>
        <div class="res__thumb res__thumb--${r.type}">
          <img class="res__cover" src="${r.cover}" alt="" loading="lazy" onerror="this.remove()">
          <span class="res__type-label">${label[r.type]}</span>
          ${r.duration ? `<span class="res__dur">${r.duration}</span>` : ''}
          ${r.pages ? `<span class="res__dur">${r.pages} 页</span>` : ''}
        </div>
        <div class="res__body">
          <b class="clamp-2">${U.esc(r.title)}</b>
          <div class="row"><span class="badge badge--outline">${label[r.type]}</span><span class="spacer"></span><span>${r.views || 0} 次</span></div>
          <div class="row fz-11 t-dim" style="margin-top:6px"><span>${U.esc(r.kp || '—')}</span><span class="spacer"></span><span>${U.esc(r.source || '')}</span></div>
        </div>
      </div>`;
    },

    openUploadModal() {
      const body = `
      <form id="trUploadForm" class="stack" style="gap:14px">
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">选择文件</span><input class="input" type="file" id="trFile" accept=".mp4,.pdf,.ppt,.pptx,.doc,.docx" required></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">资源标题</span><input class="input" type="text" id="trTitle" placeholder="默认使用文件名"></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">挂载知识点</span><select class="select" id="trKp"><option value="">自动识别章节</option></select></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">资源分类</span><select class="select" id="trCat"><option value="other">课外/教材</option><option value="knowledge">知识点挂载</option></select></label>
        <p class="fz-12 t-dim">支持 MP4、PDF、PPT、DOC；上传后会自动解析视频时长或文档页数。</p>
      </form>`;

      const footer = `<button class="btn btn--primary" id="trSubmit" type="button">${icon('upload')} 开始上传</button><button class="btn" data-close>取消</button>`;

      Modal.open({
        title: '上传学习资源',
        body,
        footer,
        onMount(ov, close) {
          const self = TeacherResource;
          const fileIn = U.$('#trFile', ov);
          const titleIn = U.$('#trTitle', ov);
          const kpSel = U.$('#trKp', ov);

          // 填充知识点下拉（value 用名称，data-kp-id 用于挂载图谱）
          const _buildKpOpts = (chapters) => {
            return '<option value="">自动识别章节</option>' +
              chapters.map(ch => `<optgroup label="${U.esc(ch.chapter)}">` +
                `<option value="${U.esc(ch.chapter)}" data-kp-id="">${U.esc(ch.chapter)}（章节级）</option>` +
                ch.items.map(it => `<option value="${U.esc(it.name)}" data-kp-id="${U.esc(it.kpId)}">${U.esc(it.name)}</option>`).join('') +
                '</optgroup>').join('');
          };
          if (self._kps.length) {
            kpSel.innerHTML = _buildKpOpts(self._kps);
          } else {
            API.teacher.resourceKps().then(d => {
              self._kps = d.chapters || [];
              kpSel.innerHTML = _buildKpOpts(self._kps);
            }).catch(() => {});
          }

          fileIn.addEventListener('change', () => {
            const f = fileIn.files[0];
            if (f && !titleIn.value.trim()) {
              titleIn.value = f.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ');
            }
          });

          U.$('#trSubmit', ov).addEventListener('click', () => {
            const f = fileIn.files[0];
            if (!f) { Toast.error('请先选择文件'); return; }
            const fd = new FormData();
            const selected = kpSel.options[kpSel.selectedIndex];
            const kpId = selected ? (selected.dataset.kpId || '') : '';
            fd.append('file', f);
            fd.append('title', titleIn.value.trim());
            fd.append('kp', kpSel.value);
            fd.append('kp_id', kpId);
            fd.append('category', U.$('#trCat', ov).value);
            const btn = U.$('#trSubmit', ov);
            btn.disabled = true; btn.textContent = '上传中…';
            API.teacher.uploadResource(fd).then(() => {
              Toast.ok('上传成功'); close(); self.load();
            }).catch(err => {
              btn.disabled = false; btn.innerHTML = `${icon('upload')} 开始上传`;
              Toast.error('上传失败', err && err.message || '');
            });
          });
        }
      });
    }
  };

Router.register('resource', { title: '资源管理', mount: () => TeacherResource.render() });
