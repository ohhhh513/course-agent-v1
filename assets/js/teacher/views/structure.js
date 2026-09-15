/* ==========================================================================
   教师端 · 课程结构（章节/知识点 CRUD + 前置关系编辑）
   多课程重构配套功能：教师在此搭建课程的知识图谱，学生端三大图谱实时同步。
   ========================================================================== */
'use strict';

const TeacherStructure = {
  data: null,      // /teacher/structure 响应
  selected: null,  // 当前选中的 kpId

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

  /* ---------------- 主视图 ---------------- */
  _paint() {
    const el = U.$('#view-structure');
    const d = this.data;
    const tree = d.chapters.map(ch => this._chapterHtml(ch)).join('')
      || R.empty('还没有章节', '点击右上角「新建章节」开始搭建课程结构', 'layers');

    el.innerHTML = `
      <div style="display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px;align-items:start">
        <div class="card">
          <div class="card__head">
            <h3>${icon('layers')} 章节与知识点</h3><span class="spacer"></span>
            <button class="btn btn--primary btn--sm" id="stNewCh">${icon('plus')} 新建章节</button>
          </div>
          <div class="card__body card__body--tight" id="stTree">${tree}</div>
        </div>
        <div class="card" id="stEditor">
          <div class="card__head"><h3>${icon('book')} 知识点编辑</h3></div>
          <div class="card__body">
            <p class="fz-12 t-dim" style="line-height:1.8">在左侧选择知识点进行编辑。<br>
            结构变更会自动同步全体学生的学习路径与学生端图谱。<br>
            删除知识点前，需先将其资源与题目的知识点标签替换或清除。</p>
          </div>
        </div>
      </div>`;

    // 顶部新建章节
    U.$('#stNewCh').addEventListener('click', () => this._chapterModal(null));

    // 章节级按钮
    U.$$('#stTree [data-act]').forEach(b => b.addEventListener('click', e => {
      e.stopPropagation();
      const act = b.dataset.act, id = b.dataset.id;
      if (act === 'newkp') this._kpModal(id);
      if (act === 'editch') this._chapterModal(id);
      if (act === 'delch') this._deleteChapter(id);
      if (act === 'adopt') this._adoptVirtual(b.dataset.name);
    }));
    // KP 行点击
    U.$$('#stTree [data-kp]').forEach(row => row.addEventListener('click', () => {
      this.selected = row.dataset.kp;
      this._paintEditor();
      U.$$('#stTree [data-kp]').forEach(x => x.classList.toggle('is-active', x === row));
    }));
    // 恢复选中
    if (this.selected) {
      const row = U.$(`#stTree [data-kp="${this.selected}"]`);
      if (row) { row.classList.add('is-active'); this._paintEditor(); }
    }
  },

  _chapterHtml(ch) {
    const kps = ch.kps.map(k => `
      <div class="list__item list__item--clickable" data-kp="${k.id}" style="padding-left:26px">
        <div class="list__main">
          <b>${U.esc(k.name)}</b>${k.isKey ? ' <span class="badge badge--brand">重点</span>' : ''}
          <p class="fz-11 t-dim">资源 ${k.resCount} · 题目 ${k.qCount} · 前置 ${k.preCount}</p>
        </div>
        <span class="list__trail fz-11 t-dim">${k.id}</span>
      </div>`).join('');
    const chOps = ch.virtual
      ? `<button class="btn btn--xs btn--ghost" data-act="adopt" data-name="${U.esc(ch.name)}">节点化此章</button>`
      : `<button class="btn btn--xs btn--ghost" data-act="newkp" data-id="${ch.id}">${icon('plus')} 知识点</button>
         <button class="btn btn--xs btn--ghost" data-act="editch" data-id="${ch.id}">改名</button>
         <button class="btn btn--xs btn--ghost" data-act="delch" data-id="${ch.id}">删除</button>`;
    return `
      <div style="padding:12px 14px 4px">
        <b class="fz-13">${U.esc(ch.name)}</b>
        <span class="fz-11 t-dim">（${ch.kps.length} 个知识点${ch.virtual ? ' · 历史章节' : ''}）</span>
        <span style="float:right">${chOps}</span>
      </div>
      <div class="list" style="padding:0 8px 8px">${kps || '<p class="fz-12 t-dim" style="padding:4px 20px 8px">暂无知识点</p>'}</div>`;
  },

  /* ---------------- 右侧编辑器 ---------------- */
  _paintEditor() {
    const kp = this._findKp(this.selected);
    const box = U.$('#stEditor');
    if (!kp) { this.selected = null; return; }
    const chOptions = this.data.chapters
      .filter(c => !c.virtual)
      .map(c => `<option value="${c.id}" ${this._chapterIdOf(kp) === c.id ? 'selected' : ''}>${U.esc(c.name)}</option>`)
      .join('');
    box.innerHTML = `
      <div class="card__head"><h3>${icon('book')} 编辑知识点</h3><span class="spacer"></span>
        <span class="fz-11 t-dim">${U.esc(kp.id)}</span></div>
      <div class="card__body stack" style="gap:12px">
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">名称</span>
          <input class="input" id="seName" value="${U.esc(kp.name)}"></label>
        <div style="display:grid;grid-template-columns:1fr 110px;gap:10px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">所属章节</span>
            <select class="select" id="seChapter">${chOptions}</select></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学时（可选）</span>
            <input class="input" id="seHours" type="number" min="0" value="${kp.hours || 0}"></label>
        </div>
        <label class="row" style="gap:6px"><input type="checkbox" id="seKey" ${kp.isKey ? 'checked' : ''}>
          <span class="fz-12">标记为重点知识点</span></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">前置知识点（按住 Ctrl 多选；保存时自动环检测）</span>
          <select class="select" id="sePre" multiple size="6"></select></label>
        <div class="row" style="gap:8px">
          <button class="btn btn--primary btn--sm" id="seSave">${icon('check')} 保存全部</button>
          <span class="spacer"></span>
          <button class="btn btn--danger btn--sm" id="seDel" ${kp.resCount + kp.qCount > 0 ? 'disabled title="请先将该知识点的资源与题目标签替换或清除"' : ''}>${icon('x')} 删除</button>
        </div>
        <p class="fz-11 t-dim" id="seDelHint">${kp.resCount + kp.qCount > 0 ? `该知识点下有 ${kp.resCount} 个资源、${kp.qCount} 道题目：请先将对应资源的知识点标签替换或清除，并处理相关题目后，才可删除。` : ''}</p>
      </div>`;

    // 前置多选候选
    API.teacher.kpRelations(kp.id).then(r => {
      const sel = U.$('#sePre');
      if (!sel) return;
      sel.innerHTML = (r.candidates || []).map(c =>
        `<option value="${c.id}" ${r.preKpIds.includes(c.id) ? 'selected' : ''}>${U.esc(c.name)}（${U.esc(c.chapter)}）</option>`).join('');
    }).catch(() => {});

    U.$('#seSave').addEventListener('click', () => this._saveKp(kp));
    U.$('#seDel').addEventListener('click', () => this._deleteKp(kp));
  },

  _findKp(id) {
    for (const ch of this.data.chapters) {
      const k = ch.kps.find(x => x.id === id);
      if (k) return { ...k, _chName: ch.name };
    }
    return null;
  },

  _chapterIdOf(kp) {
    const ch = this.data.chapters.find(c => c.name === kp._chName || c.name === kp.name);
    return (ch && !ch.virtual) ? ch.id : '';
  },

  _saveKp(kp) {
    const name = U.$('#seName').value.trim();
    if (!name) { Toast.warn('请输入名称'); return; }
    const chapterId = U.$('#seChapter').value;
    if (!chapterId) { Toast.warn('请先在左侧将该章「节点化」后再编辑归属'); return; }
    const preKpIds = [...U.$('#sePre').selectedOptions].map(o => o.value);
    const btn = U.$('#seSave');
    btn.disabled = true;
    API.teacher.updateKp(kp.id, {
      name, chapterId, hours: parseInt(U.$('#seHours').value, 10) || 0, isKey: U.$('#seKey').checked,
    }).then(() => API.teacher.saveKpRelations(kp.id, { preKpIds }))
      .then(() => {
        Toast.ok('已保存', '学习路径与学生端图谱已同步');
        this.selected = kp.id;
        this.render();
      })
      .catch(err => { btn.disabled = false; Toast.error('保存失败', err && err.message || ''); });
  },

  _deleteKp(kp) {
    if (!confirm(`确定删除知识点「${kp.name}」吗？\n删除后其学习路径、前置关系将一并移除，且不可恢复。`)) return;
    API.teacher.deleteKp(kp.id).then(() => {
      Toast.ok('已删除');
      this.selected = null;
      this.render();
    }).catch(err => Toast.error('删除失败', err && err.message || ''));
  },

  /* ---------------- 弹窗：新建/改名章节 ---------------- */
  _chapterModal(chId) {
    const editing = chId ? this.data.chapters.find(c => c.id === chId) : null;
    Modal.open({
      title: editing ? '修改章节' : '新建章节',
      body: `
        <div class="stack" style="gap:14px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">章节名称</span>
            <input class="input" id="chName" value="${editing ? U.esc(editing.name) : ''}" placeholder="如：第1章 绪论"></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">建议学时（可选）</span>
            <input class="input" id="chHours" type="number" min="0" value="${editing ? editing.hours || 0 : 0}"></label>
          ${editing ? '' : '<p class="fz-12 t-dim">章节按创建顺序排列；创建后即可在其下新建知识点。</p>'}
        </div>`,
      footer: `<button class="btn btn--primary" id="chGo" type="button">${editing ? '保存' : '创建'}</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#chGo', ov).addEventListener('click', () => {
          const body = { name: U.$('#chName', ov).value.trim(), hours: parseInt(U.$('#chHours', ov).value, 10) || 0 };
          if (!body.name) { Toast.warn('请输入章节名称'); return; }
          const call = editing ? API.teacher.updateChapter(editing.id, body) : API.teacher.createChapter(body);
          call.then(() => { close(); Toast.ok(editing ? '已保存' : '章节已创建'); TeacherStructure.render(); })
            .catch(err => Toast.error('操作失败', err && err.message || ''));
        });
      }
    });
  },

  /* ---------------- 弹窗：新建知识点 ---------------- */
  _kpModal(chapterId) {
    const ch = this.data.chapters.find(c => c.id === chapterId);
    Modal.open({
      title: '新建知识点',
      body: `
        <div class="stack" style="gap:14px">
          <div class="fz-12">所属章节：<b>${U.esc(ch ? ch.name : '')}</b></div>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">知识点名称</span>
            <input class="input" id="kpName" placeholder="如：时间复杂度分析"></label>
          <div style="display:grid;grid-template-columns:110px 1fr;gap:10px;align-items:end">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">学时（可选）</span>
              <input class="input" id="kpHours" type="number" min="0" value="0"></label>
            <label class="row" style="gap:6px;padding-bottom:8px"><input type="checkbox" id="kpKey">
              <span class="fz-12">标记为重点知识点</span></label>
          </div>
          <p class="fz-12 t-dim">创建后可在右侧编辑其前置知识点；全体学生的学习路径将自动同步。</p>
        </div>`,
      footer: `<button class="btn btn--primary" id="kpGo" type="button">创建</button><button class="btn" data-close>取消</button>`,
      onMount(ov, close) {
        U.$('#kpGo', ov).addEventListener('click', () => {
          const name = U.$('#kpName', ov).value.trim();
          if (!name) { Toast.warn('请输入知识点名称'); return; }
          API.teacher.createKp({
            name, chapterId,
            hours: parseInt(U.$('#kpHours', ov).value, 10) || 0,
            isKey: U.$('#kpKey', ov).checked,
          }).then(r => { close(); Toast.ok('知识点已创建', r.id); TeacherStructure.render(); })
            .catch(err => Toast.error('创建失败', err && err.message || ''));
        });
      }
    });
  },

  /* ---------------- 历史字符串章一键节点化 ---------------- */
  _adoptVirtual(name) {
    API.teacher.createChapter({ name }).then(() => {
      Toast.ok('章节已节点化', name);
      this.render();
    }).catch(err => Toast.error('操作失败', err && err.message || ''));
  },
};

Router.register('structure', { title: '课程结构', sub: '章节 · 知识点 · 前置关系', mount: () => TeacherStructure.render() });
