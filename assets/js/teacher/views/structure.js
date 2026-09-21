/* ==========================================================================
   教师端 · 课程目录与资源
   目录 = 章；标签 = KP（来自资源标签并集）。上传挂到章下。
   ========================================================================== */
'use strict';

const TeacherStructure = {
  data: null,
  selectedChapterId: null,

  render() {
    const el = U.$('#view-structure');
    el.innerHTML = `<div class="card"><div class="card__body" style="padding:30px;text-align:center">${icon('refresh')} 加载中…</div></div>`;
    API.teacher.structure().then(d => {
      this.data = d;
      this._paint();
    }).catch(err => {
      el.innerHTML = `<div class="empty">${icon('alert')}<b>加载失败</b><p>${U.esc(err.message || '')}</p></div>`;
    });
  },

  _paint() {
    const el = U.$('#view-structure');
    const d = this.data;
    const chapters = (d.chapters || []).filter(c => {
      if (!c.virtual) return true;
      // 保留有资源的「未分章」；丢弃旧版空的「未分类」虚拟壳
      return (c.resources || []).length > 0;
    });
    const tree = chapters.map(ch => this._chapterHtml(ch)).join('')
      || R.empty('还没有章节目录', '点击上方「新建章节」开始搭建', 'layers');

    el.innerHTML = `
      <div class="card" style="height:calc(100vh - var(--topbar-h) - 44px);display:flex;flex-direction:column;min-height:0">
        <div class="card__head" style="flex-shrink:0">
          <h3>${icon('folder')} 课程目录与资源</h3>
          <span class="spacer"></span>
          <button class="btn btn--primary btn--sm" id="stNewCh" type="button">${icon('plus')} 新建章节</button>
          <button class="btn btn--outline btn--sm" id="stUpload" type="button">${icon('upload')} 上传到目录</button>
        </div>
        <div class="card__body" id="stTree" style="overflow:auto;min-height:0;flex:1">${tree}</div>
      </div>
      <style>
        #view-structure .st-link{cursor:pointer;border-bottom:1px dashed transparent}
        #view-structure .st-link:hover{color:var(--brand);border-bottom-color:var(--brand)}
        #view-structure .chip{cursor:pointer}
        #view-structure .chip:hover{border-color:var(--brand);color:var(--brand)}
      </style>`;

    U.$('#stNewCh').addEventListener('click', () => this._chapterModal(null));
    U.$('#stUpload').addEventListener('click', () => this.openUploadModal(this.selectedChapterId));

    U.$$('#stTree [data-act]').forEach(b => b.addEventListener('click', e => {
      e.stopPropagation();
      const act = b.dataset.act;
      const id = b.dataset.id;
      // 清单 5-1/5-2：章节与知识点都进详情页，按钮集中到详情页里
      if (act === 'chdetail') this._chapterDetailModal(id);
      if (act === 'kpdetail') this._kpDetailModal(id);
      if (act === 'editch') this._chapterModal(id);
      if (act === 'delch') this._deleteChapter(id);
      if (act === 'upload') this.openUploadModal(id);
      if (act === 'newkp') this._kpModal(id);
      if (act === 'delkp') this._deleteKp(id, b.dataset.name);
      if (act === 'editres') {
        const rid = id;
        const ch = (this.data.chapters || []).find(c =>
          c.id === (b.dataset.ch || '') || (c.resources || []).some(r => r.resId === rid));
        const r = ch && (ch.resources || []).find(x => x.resId === rid);
        if (r) this.openEditResourceModal(r);
      }
      if (act === 'delres') this._deleteResource(id);
    }));

    U.$$('#stTree [data-ch]').forEach(row => row.addEventListener('click', () => {
      this.selectedChapterId = row.dataset.ch || null;
      U.$$('#stTree [data-ch]').forEach(x => x.classList.toggle('is-active', x === row));
    }));
  },

  /** 章下「本章知识点（标签）」= 该章全部资源标签的并集 */
  _chapterTagUnion(ch) {
    const map = new Map();
    for (const r of (ch.resources || [])) {
      for (const t of (r.tags || r.kps || [])) {
        const id = t.kpId || t.tagId || t.id || t.name;
        if (!id) continue;
        if (!map.has(id)) map.set(id, t.name || id);
      }
      // 兼容仅 kpIds 无 tags 对象
      for (const kid of (r.kpIds || [])) {
        if (!map.has(kid)) {
          const found = ((this.data && this.data.kpOptions) || []).find(k => k.id === kid);
          map.set(kid, found ? found.name : kid);
        }
      }
    }
    return [...map.entries()].map(([id, name]) => ({ id, name }));
  },

  _chapterHtml(ch) {
    const tags = this._chapterTagUnion(ch);
    const tagChips = tags.length
      ? tags.map(t => `<span class="badge badge--outline">${U.esc(t.name)}</span>`).join('')
      : '<span class="fz-11 t-dim">本章资源尚未打标签</span>';
    const kps = ch.kps || [];
    // 清单 5-1：知识点标签可点开详情页（编辑/删除都在详情页里）
    const kpChips = kps.length
      ? kps.map(k => `<button type="button" class="chip" data-act="kpdetail" data-id="${U.esc(k.id)}"
          title="点击查看详情、编辑或删除">${U.esc(k.name)}${k.isKey ? ' ★' : ''}</button>`).join('')
      : tagChips;

    const res = (ch.resources || []).map(r => {
      const rtags = (r.tags || r.kps || []).map(t =>
        `<span class="badge badge--outline">${U.esc(t.name)}</span>`).join('');
      return `
      <div class="list__item" data-res="${r.resId}" style="padding-left:20px">
        <div class="list__main">
          <b class="clamp-2">${U.esc(r.title)}</b>
          <div class="row fz-11 t-dim" style="gap:6px;flex-wrap:wrap;margin-top:2px">
            <span class="badge badge--outline">${U.esc(r.type)}</span>
            ${rtags}
          </div>
        </div>
        <div class="row" style="gap:4px">
          <button class="btn btn--xs btn--ghost" data-act="editres" data-id="${r.resId}" data-ch="${U.esc(ch.id || '')}">编辑</button>
          <button class="btn btn--xs btn--ghost" data-act="delres" data-id="${r.resId}">删</button>
        </div>
      </div>`;
    }).join('') || `<p class="fz-11 t-dim" style="padding:6px 0 8px 20px">目录下暂无资源 · 点「上传」加入</p>`;

    return `
      <div class="list__section" data-ch="${U.esc(ch.id || '')}"
           style="border:1px solid var(--border);border-radius:10px;padding:10px 12px;margin-bottom:12px">
        <div class="list__item" style="padding-left:0">
          <div class="list__main">
            <b class="st-link" data-act="chdetail" data-id="${U.esc(ch.id || '')}"
               title="点击查看详情与编辑">${U.esc(ch.name)}</b>${ch.virtual ? ' <span class="badge badge--outline">未分章</span>' : ''}
            <p class="fz-11 t-dim">资源 ${(ch.resources || []).length} · 知识点 ${kps.length}</p>
          </div>
          <div class="row" style="gap:4px;flex-shrink:0">
            ${ch.virtual ? '' : `
              <button class="btn btn--xs btn--outline" data-act="chdetail" data-id="${U.esc(ch.id)}">详情 / 管理</button>`}
          </div>
        </div>
        ${res}
        <div style="padding:8px 0 0 20px;border-top:1px dashed var(--border);margin-top:6px">
          <div class="fz-11 t-dim" style="margin-bottom:6px;font-weight:600">本章知识点（标签）</div>
          <div class="chips" style="align-items:center">${kpChips}</div>
          ${kps.length && tags.length
            ? `<p class="fz-11 t-dim" style="margin-top:6px">资源侧标签并集：${tags.map(t => U.esc(t.name)).join('、')}</p>`
            : ''}
        </div>
      </div>`;
  },

  /* ---------- 上传到章节目录 ---------- */
  openUploadModal(chapterId) {
    const chapters = ((this.data && this.data.chapterOptions) || [])
      .filter(c => c.id); // 去掉虚拟章
    if (!chapters.length) {
      Toast.warn('请先新建章节');
      return;
    }
    const kps = (this.data && this.data.kpOptions) || [];
    const chOpts = chapters.map(c =>
      `<option value="${U.esc(c.id)}" ${c.id === chapterId ? 'selected' : ''}>${U.esc(c.name)}</option>`).join('');

    const body = `
      <form id="trUploadForm" class="stack" style="gap:12px">
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">目录（章）</span>
          <select class="select" id="trChapter" required>${chOpts}</select></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">选择文件</span>
          <input class="input" type="file" id="trFile" accept=".mp4,.pdf,.ppt,.pptx,.doc,.docx" required></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">资源标题</span>
          <input class="input" type="text" id="trTitle" placeholder="默认使用文件名"></label>
        <div class="stack" style="gap:6px">
          <span class="fz-12 t-dim">KP 标签（可多选；标签=知识点）</span>
          <div id="trKpTags" class="chips" style="max-height:140px;overflow:auto">
            ${kps.map(k => `<button type="button" class="chip" data-kp="${U.esc(k.id)}" data-ch="${U.esc(k.chapter || '')}">${U.esc(k.name)}</button>`).join('')
              || '<span class="fz-11 t-dim">暂无知识点，可在下方输入新建</span>'}
          </div>
          <div class="row" style="gap:6px">
            <input class="input" id="trNewKp" placeholder="新建 KP 标签名，回车加入" style="flex:1">
            <button type="button" class="btn btn--sm btn--outline" id="trAddKp">新建</button>
          </div>
        </div>
        <p class="fz-12 t-dim">PDF / PPT / TXT / JSON 上传后自动 RAG 切片。</p>
      </form>`;

    Modal.open({
      title: '上传资源到章节目录',
      body,
      footer: `<button class="btn btn--primary" id="trSubmit" type="button">${icon('upload')} 开始上传</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        const selected = new Set();
        const tagBox = U.$('#trKpTags', ov);

        const paint = () => {
          tagBox.querySelectorAll('[data-kp]').forEach(b => {
            b.classList.toggle('is-on', selected.has(b.dataset.kp));
            // 兼容主题：is-active 也可
            b.classList.toggle('is-active', selected.has(b.dataset.kp));
          });
        };

        const selectChapterKps = (chId) => {
          selected.clear();
          const ch = chapters.find(c => c.id === chId);
          if (!ch) { paint(); return; }
          kps.filter(k => k.chapter === ch.name).forEach(k => selected.add(k.id));
          paint();
        };

        tagBox.addEventListener('click', e => {
          const b = e.target.closest('[data-kp]');
          if (!b) return;
          const id = b.dataset.kp;
          if (selected.has(id)) selected.delete(id); else selected.add(id);
          paint();
        });

        U.$('#trChapter', ov).addEventListener('change', () => selectChapterKps(U.$('#trChapter', ov).value));
        selectChapterKps(U.$('#trChapter', ov).value);

        async function addNewKp() {
          const name = (U.$('#trNewKp', ov).value || '').trim();
          if (!name) { Toast.warn('请输入标签名'); return; }
          try {
            const r = await API.teacher.createKp({
              name,
              chapterId: U.$('#trChapter', ov).value,
              hours: 0,
              isKey: false,
            });
            const id = (r && (r.id || r.kpId)) || '';
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'chip';
            chip.dataset.kp = id;
            chip.textContent = name;
            tagBox.appendChild(chip);
            selected.add(id);
            paint();
            U.$('#trNewKp', ov).value = '';
            // 刷新缓存
            if (TeacherStructure.data) {
              TeacherStructure.data.kpOptions = TeacherStructure.data.kpOptions || [];
              TeacherStructure.data.kpOptions.push({ id, name, chapter: '' });
            }
            Toast.ok('已新建 KP 标签', name);
          } catch (err) {
            Toast.error('新建失败', (err && err.message) || '');
          }
        }
        U.$('#trAddKp', ov).addEventListener('click', addNewKp);
        U.$('#trNewKp', ov).addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); addNewKp(); }
        });

        U.$('#trFile', ov).addEventListener('change', e => {
          const f = e.target.files[0];
          const titleIn = U.$('#trTitle', ov);
          if (f && !titleIn.value.trim()) {
            titleIn.value = f.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ');
          }
        });

        U.$('#trSubmit', ov).addEventListener('click', () => {
          const f = U.$('#trFile', ov).files[0];
          if (!f) { Toast.error('请先选择文件'); return; }
          const chId = U.$('#trChapter', ov).value;
          if (!chId) { Toast.error('请选择章节目录'); return; }
          const ch = chapters.find(c => c.id === chId);
          const kpIds = [...selected];
          const fd = new FormData();
          fd.append('file', f);
          fd.append('title', U.$('#trTitle', ov).value.trim());
          fd.append('chapterId', chId);
          fd.append('chapter', ch ? ch.name : '');
          fd.append('kpIds', JSON.stringify(kpIds));
          fd.append('kp_id', kpIds[0] || '');
          const kpObj = kpIds[0] ? kps.find(k => k.id === kpIds[0]) : null;
          fd.append('kp', kpObj ? kpObj.name : '');
          fd.append('category', kpIds.length ? 'knowledge' : 'other');
          const btn = U.$('#trSubmit', ov);
          btn.disabled = true; btn.textContent = '上传中…';
          API.teacher.uploadResource(fd).then(r => {
            Toast.ok('已上传到目录', ch ? ch.name : '');
            close();
            TeacherStructure.render();
          }).catch(err => {
            btn.disabled = false; btn.innerHTML = `${icon('upload')} 开始上传`;
            Toast.error('上传失败', err && err.message || '');
          });
        });
      }
    });
  },

  openEditResourceModal(r) {
    const chapters = ((this.data && this.data.chapterOptions) || []).filter(c => c.id);
    const kps = (this.data && this.data.kpOptions) || [];
    const body = `
      <form class="stack" style="gap:12px">
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">标题</span>
          <input class="input" id="erTitle" value="${U.esc(r.title || '')}"></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">目录（章）</span>
          <select class="select" id="erChapter">
            <option value="">未分章</option>
            ${chapters.map(c => `<option value="${U.esc(c.id)}" ${c.id === r.chapterId ? 'selected' : ''}>${U.esc(c.name)}</option>`).join('')}
          </select></label>
        <div class="stack" style="gap:6px">
          <span class="fz-12 t-dim">KP 标签（点击选中 / 取消）</span>
          <div id="erKpTags" class="chips" style="max-height:140px;overflow:auto">
            ${kps.map(k => `<button type="button" class="chip" data-kp="${U.esc(k.id)}">${U.esc(k.name)}</button>`).join('')
              || '<span class="fz-11 t-dim">当前课程暂无知识点</span>'}
          </div>
          <div class="fz-11 t-dim" style="margin-top:4px">已选标签（点击 ✕ 移除）：</div>
          <div id="erKpSelected" class="chips" style="min-height:28px"></div>
        </div>
      </form>`;
    Modal.open({
      title: '编辑资源',
      body,
      footer: `<button class="btn btn--primary" id="erSave" type="button">保存</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        const selected = new Set(r.kpIds || (r.kps || []).map(t => t.kpId));
        const nameOf = (id) => {
          const k = kps.find(x => x.id === id);
          return k ? k.name : id;
        };
        const paint = () => {
          U.$('#erKpTags', ov).querySelectorAll('[data-kp]').forEach(b => {
            b.classList.toggle('is-on', selected.has(b.dataset.kp));
            b.classList.toggle('is-active', selected.has(b.dataset.kp));
          });
          U.$('#erKpSelected', ov).innerHTML = [...selected].map(id =>
            `<span class="chip is-on" style="display:inline-flex;align-items:center;gap:4px">
              ${U.esc(nameOf(id))}
              <button type="button" class="btn btn--xs btn--ghost" data-off="${U.esc(id)}" style="height:18px;padding:0 4px;min-width:18px">✕</button>
            </span>`).join('') || '<span class="fz-11 t-dim">（无）</span>';
          U.$('#erKpSelected', ov).querySelectorAll('[data-off]').forEach(btn => {
            btn.addEventListener('click', () => {
              selected.delete(btn.dataset.off);
              paint();
            });
          });
        };
        U.$('#erKpTags', ov).addEventListener('click', e => {
          const b = e.target.closest('[data-kp]');
          if (!b) return;
          if (selected.has(b.dataset.kp)) selected.delete(b.dataset.kp); else selected.add(b.dataset.kp);
          paint();
        });
        paint();
        U.$('#erSave', ov).addEventListener('click', () => {
          API.teacher.updateResource(r.resId, {
            title: U.$('#erTitle', ov).value.trim(),
            chapterId: U.$('#erChapter', ov).value,
            kpIds: [...selected],
          }).then(() => {
            Toast.ok('资源已更新');
            close();
            TeacherStructure.render();
          }).catch(err => Toast.error('保存失败', (err && err.message) || ''));
        });
      }
    });
  },

  _deleteResource(resId) {
    if (!confirm('确定删除该资源？学生端不可见，并清理 RAG 切片。')) return;
    API.teacher.deleteResource(resId).then(() => {
      Toast.ok('已删除');
      this.render();
    }).catch(err => Toast.error('删除失败', (err && err.message) || ''));
  },

  _chapterModal(id) {
    const ch = id ? (this.data.chapters || []).find(c => c.id === id) : null;
    Modal.open({
      title: ch ? '修改章节' : '新建章节',
      body: `
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">章节名称</span>
          <input class="input" id="chName" value="${U.esc(ch ? ch.name : '')}" placeholder="如：第1章 绪论"></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学时</span>
          <input class="input" id="chHours" type="number" min="0" value="${ch ? ch.hours || 0 : 0}"></label>
        <p class="fz-12 t-dim">创建后即可在目录中向该章上传资源，并为资源打 KP 标签。</p>`,
      footer: `<button class="btn btn--primary" id="chSave">保存</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#chSave', ov).addEventListener('click', () => {
          const name = U.$('#chName', ov).value.trim();
          const hours = parseInt(U.$('#chHours', ov).value, 10) || 0;
          if (!name) { Toast.warn('请输入章节名'); return; }
          const p = ch
            ? API.teacher.updateChapter(ch.id, { name, hours })
            : API.teacher.createChapter({ name, hours });
          p.then(() => {
            close();
            TeacherStructure.render();
            Toast.ok(ch ? '章节已更新' : '章节已创建', '可点击该章「上传」加入资源');
          }).catch(err => Toast.error('失败', (err && err.message) || ''));
        });
      }
    });
  },

  _deleteChapter(id) {
    if (!confirm('确定删除该章节？章下若仍有知识点将被拒绝。')) return;
    API.teacher.deleteChapter(id).then(() => {
      Toast.ok('已删除');
      this.render();
    }).catch(err => Toast.error('删除失败', (err && err.message) || ''));
  },

  /* ---------- 章节详情页（上传 / +KP / 改名 / 删除 集中在此） ---------- */
  _chapterDetailModal(id) {
    const ch = (this.data.chapters || []).find(c => c.id === id);
    if (!ch) return;
    const kps = ch.kps || [];
    Modal.open({
      title: '章节详情',
      body: `
        <div class="stack" style="gap:12px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">章节名称</span>
            <input class="input" id="cdName" value="${U.esc(ch.name || '')}" placeholder="如：第1章 绪论"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学时</span>
            <input class="input" id="cdHours" type="number" min="0" value="${ch.hours || 0}"></label>
          <div class="row" style="gap:8px;flex-wrap:wrap">
            <span class="badge badge--outline">资源 ${(ch.resources || []).length}</span>
            <span class="badge badge--outline">知识点 ${kps.length}</span>
          </div>
          <div class="stack" style="gap:6px">
            <span class="fz-12 t-dim">本章知识点（点击查看 / 编辑详情）</span>
            <div class="chips">
              ${kps.map(k => `<button type="button" class="chip" data-kp="${U.esc(k.id)}">${U.esc(k.name)}${k.isKey ? ' ★' : ''}</button>`).join('')
                || '<span class="fz-11 t-dim">本章暂无知识点</span>'}
            </div>
          </div>
          <p class="fz-12 t-dim">上传资源、新增知识点、改名与删除都在本页完成；目录列表只做展示。</p>
        </div>`,
      footer: `
        <button class="btn btn--primary" id="cdSave" type="button">保存修改</button>
        <button class="btn" id="cdUpload" type="button">${icon('upload')} 上传资源</button>
        <button class="btn" id="cdNewKp" type="button">${icon('plus')} 新增知识点</button>
        <button class="btn btn--danger" id="cdDel" type="button">删除章节</button>
        <button class="btn" data-close>关闭</button>`,
      onMount(ov, close) {
        U.$$('[data-kp]', ov).forEach(b => b.addEventListener('click', () => {
          close();
          TeacherStructure._kpDetailModal(b.dataset.kp);
        }));
        U.$('#cdUpload', ov).addEventListener('click', () => {
          close();
          TeacherStructure.openUploadModal(id);
        });
        U.$('#cdNewKp', ov).addEventListener('click', () => {
          close();
          TeacherStructure._kpModal(id);
        });
        U.$('#cdSave', ov).addEventListener('click', () => {
          const name = U.$('#cdName', ov).value.trim();
          const hours = parseInt(U.$('#cdHours', ov).value, 10) || 0;
          if (!name) { Toast.warn('请输入章节名'); return; }
          API.teacher.updateChapter(id, { name, hours }).then(() => {
            Toast.ok('章节已更新');
            close();
            TeacherStructure.render();
          }).catch(err => Toast.error('保存失败', (err && err.message) || ''));
        });
        U.$('#cdDel', ov).addEventListener('click', () => {
          close();
          TeacherStructure._deleteChapter(id);
        });
      }
    });
  },

  /* ---------- 知识点详情页（改名 / 换章 / 学时 / 重点 / 简介 / 删除） ---------- */
  _kpDetailModal(kpId) {
    const chapters = ((this.data && this.data.chapterOptions) || []).filter(c => c.id);
    let kp = null;
    let chapterId = '';
    for (const c of (this.data.chapters || [])) {
      const f = (c.kps || []).find(k => k.id === kpId);
      if (f) { kp = f; chapterId = c.id || ''; break; }
    }
    if (!kp) {
      const o = ((this.data && this.data.kpOptions) || []).find(k => k.id === kpId);
      if (o) kp = { id: o.id, name: o.name, hours: 0, isKey: false, chapter: o.chapter || '' };
    }
    if (!kp) { Toast.warn('未找到该知识点'); return; }
    if (!chapterId) {
      const m = chapters.find(c => c.name === kp.chapter);
      chapterId = m ? m.id : '';
    }

    Modal.open({
      title: '知识点详情',
      body: `
        <div class="stack" style="gap:12px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点名称</span>
            <input class="input" id="kdName" value="${U.esc(kp.name || '')}" placeholder="如：二分查找"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">所属章节</span>
            <select class="select" id="kdChapter">
              <option value="">（不修改）</option>
              ${chapters.map(c => `<option value="${U.esc(c.id)}" ${c.id === chapterId ? 'selected' : ''}>${U.esc(c.name)}</option>`).join('')}
            </select></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学时</span>
            <input class="input" id="kdHours" type="number" min="0" value="${kp.hours || 0}"></label>
          <label class="row" style="gap:6px">
            <input type="checkbox" id="kdKey" ${kp.isKey ? 'checked' : ''}> <span>标记为重点</span></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点介绍</span>
            <textarea class="input" id="kdSummary" rows="4" placeholder="加载中…"></textarea></label>
          <div class="row" style="gap:8px;flex-wrap:wrap" id="kdStats"></div>
        </div>`,
      footer: `
        <button class="btn btn--primary" id="kdSave" type="button">保存修改</button>
        <button class="btn btn--danger" id="kdDel" type="button">删除知识点</button>
        <button class="btn" data-close>关闭</button>`,
      onMount(ov, close) {
        // 简介与真实统计来自后端（kp_details + 关系 + 资源/题目计数）
        API.teacher.kpDetail({ kpId }).then(d => {
          const ta = U.$('#kdSummary', ov);
          if (ta) { ta.value = (d && d.summary) || ''; ta.placeholder = '一句话讲清这个知识点讲什么'; }
          const st = U.$('#kdStats', ov);
          if (st && d) {
            st.innerHTML = [
              `资源 ${d.resourceCount || 0}`,
              `题目 ${d.questionCount || 0}`,
              `前置 ${(d.pre || []).length}`,
              `后继 ${(d.post || []).length}`,
            ].map(t => `<span class="badge badge--outline">${t}</span>`).join('');
          }
        }).catch(() => {
          const ta = U.$('#kdSummary', ov);
          if (ta) { ta.value = ''; ta.placeholder = '（简介加载失败，可直接填写后保存）'; }
        });

        U.$('#kdSave', ov).addEventListener('click', () => {
          const name = U.$('#kdName', ov).value.trim();
          if (!name) { Toast.warn('请输入知识点名称'); return; }
          const payload = {
            name,
            hours: parseInt(U.$('#kdHours', ov).value, 10) || 0,
            isKey: U.$('#kdKey', ov).checked,
            summary: (U.$('#kdSummary', ov).value || '').trim(),
          };
          const cid = U.$('#kdChapter', ov).value;
          if (cid) payload.chapterId = cid;
          API.teacher.updateKp(kpId, payload).then(() => {
            Toast.ok('知识点已更新', name);
            close();
            TeacherStructure.render();
          }).catch(err => Toast.error('保存失败', (err && err.message) || ''));
        });

        U.$('#kdDel', ov).addEventListener('click', () => {
          close();
          TeacherStructure._deleteKp(kpId, kp.name);
        });
      }
    });
  },

  /** 新建本章知识点（标签） */
  _kpModal(chapterId) {
    const ch = (this.data.chapters || []).find(c => c.id === chapterId);
    Modal.open({
      title: '添加知识点标签',
      body: `
        <div class="stack" style="gap:12px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">所属章节</span>
            <input class="input" value="${U.esc(ch ? ch.name : '')}" disabled></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点名称</span>
            <input class="input" id="kpNewName" placeholder="如：二分查找"></label>
          <label class="row" style="gap:6px"><input type="checkbox" id="kpNewKey"> <span>标记为重点</span></label>
        </div>`,
      footer: `<button class="btn btn--primary" id="kpNewSave">添加</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#kpNewSave', ov).addEventListener('click', () => {
          const name = U.$('#kpNewName', ov).value.trim();
          if (!name) { Toast.warn('请输入知识点名称'); return; }
          API.teacher.createKp({
            name,
            chapterId,
            hours: 0,
            isKey: U.$('#kpNewKey', ov).checked,
          }).then(() => {
            close();
            TeacherStructure.render();
            Toast.ok('已添加知识点', name);
          }).catch(err => Toast.error('添加失败', (err && err.message) || ''));
        });
      }
    });
  },

  /** 删除知识点标签（API；有资源/题时后端 400） */
  _deleteKp(kpId, name) {
    const label = name || kpId;
    if (!confirm(`确定删除知识点「${label}」？\n若仍挂有资源或题目，将无法删除。`)) return;
    API.teacher.deleteKp(kpId).then(() => {
      Toast.ok('已删除知识点', label);
      this.render();
    }).catch(err => Toast.error('删除失败', (err && err.message) || ''));
  },
};

window.TeacherStructure = TeacherStructure;
Router.register('structure', { title: '课程目录与资源', mount: () => TeacherStructure.render() });
Router.register('resource', { title: '课程目录与资源', mount: () => TeacherStructure.render() });
