'use strict';

const TeacherShares = {
  render() {
    const el = U.$('#view-shares');
    if (!API.config.activeCourseId) {
      el.innerHTML = `<div class="card"><div class="card__body">
        <div class="empty" style="padding:48px 20px;text-align:center">
          <b>尚未创建或选择课程</b>
          <p class="fz-12 t-dim" style="margin-top:8px">请先在顶栏选择课程。</p>
        </div>
      </div>`;
      return;
    }
    el.innerHTML = U.skeleton(280);
    API.teacher.shares().then(d => this.paint(el, d)).catch(e => {
      el.innerHTML = `<div class="card"><div class="card__body"><p class="t-danger">${U.esc(e.message || '加载失败')}</p></div></div>`;
    });
  },

  paint(el, d) {
    const list = Array.isArray(d.list) ? d.list : [];
    el.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="card__head">
          <h3>${icon('link')} 更多资源分享</h3>
          <span class="spacer"></span>
          <button class="btn btn--primary btn--sm" id="shareCreateBtn" type="button">${icon('plus')} 发布资源</button>
        </div>
        <div class="card__body">
          ${list.length ? `<div class="share-list">${list.map(item => this.card(item)).join('')}</div>`
            : `<div class="empty" style="padding:36px 16px;text-align:center">${icon('link')}<b>还没有分享</b>
              <p class="t-dim">可以添加文章、站点或公众号内容。</p></div>`}
        </div>
      </div>`;
    U.$('#shareCreateBtn').addEventListener('click', () => this.edit());
    U.$$('[data-share-edit]', el).forEach(btn => btn.addEventListener('click', () => {
      const item = list.find(x => x.shareId === btn.dataset.shareEdit);
      if (item) this.edit(item);
    }));
    U.$$('[data-share-del]', el).forEach(btn => btn.addEventListener('click', () => this.remove(btn.dataset.shareDel, btn.dataset.title)));
    U.$$('[data-share-readers]', el).forEach(btn => btn.addEventListener('click', () => this.readers(btn.dataset.shareReaders)));
  },

  card(item) {
    const read = Number(item.readCount) || 0;
    const total = Number(item.studentCount) || 0;
    return `<article class="share-item">
      <div class="share-item__main">
        <b>${U.esc(item.title)}</b>
        <p class="fz-12 t-dim">${U.esc(item.source || '教师推荐')} · ${U.esc(item.publishedOn || '')}</p>
        <a class="fz-12 t-brand" href="${U.esc(item.url)}" target="_blank" rel="noopener noreferrer">${U.esc(item.url)}</a>
      </div>
      <div class="share-item__meta">
        <span class="badge badge--outline">已读 ${read}/${total}</span>
        <button class="btn btn--sm" type="button" data-share-readers="${U.esc(item.shareId)}">阅读记录</button>
        <button class="btn btn--sm btn--ghost" type="button" data-share-edit="${U.esc(item.shareId)}">编辑</button>
        <button class="btn btn--sm btn--ghost" type="button" data-share-del="${U.esc(item.shareId)}" data-title="${U.esc(item.title)}">删除</button>
      </div>
    </article>`;
  },

  edit(item) {
    const isNew = !item;
    Modal.open({
      title: isNew ? '发布资源' : '编辑资源',
      body: `<div class="stack" style="gap:10px">
        <label><span class="fz-12 t-dim">标题</span><input class="input" id="shareTitle" maxlength="80" value="${U.esc(item && item.title || '')}" placeholder="例如：哈希表在工业界的新用法"></label>
        <label><span class="fz-12 t-dim">来源（网站 / 公众号）</span><input class="input" id="shareSource" maxlength="40" value="${U.esc(item && item.source || '')}" placeholder="例如：InfoQ / 某课程公众号"></label>
        <label><span class="fz-12 t-dim">链接</span><input class="input" id="shareUrl" value="${U.esc(item && item.url || '')}" placeholder="https://"></label>
      </div>`,
      footer: `<button class="btn btn--primary" id="shareSave">${isNew ? '发布' : '保存'}</button>`,
      onMount: (root, close) => {
        U.$('#shareSave', root).addEventListener('click', () => {
          const payload = {
            title: U.$('#shareTitle', root).value,
            source: U.$('#shareSource', root).value,
            url: U.$('#shareUrl', root).value,
          };
          const req = isNew ? API.teacher.createShare(payload) : API.teacher.updateShare(item.shareId, payload);
          req.then(() => { Toast.ok(isNew ? '已发布' : '已保存'); close(); this.render(); })
            .catch(e => Toast.err(e.message || '保存失败'));
        });
      }
    });
  },

  remove(id, title) {
    Modal.open({
      title: '删除资源',
      body: `<p>确认删除「${U.esc(title || '')}」？</p>`,
      footer: `<button class="btn btn--danger" id="shareDelOk">确认删除</button>`,
      onMount: (root, close) => {
        U.$('#shareDelOk', root).addEventListener('click', () => {
          API.teacher.deleteShare(id).then(() => { Toast.ok('已删除'); close(); this.render(); })
            .catch(e => Toast.err(e.message || '删除失败'));
        });
      }
    });
  },

  readers(id) {
    API.teacher.shareReaders(id).then(d => {
      const read = d.read || [];
      const unread = d.unread || [];
      const share = d.share || {};
      Modal.open({
        title: `阅读记录 · ${share.title || ''}`,
        size: 'wide',
        body: `<div class="share-readers">
          <p class="fz-12 t-dim share-readers__summary">已读 ${read.length} / ${(read.length + unread.length)} 人</p>
          <div class="share-readers__cols">
            <section class="share-readers__col">
              <b class="fz-13">已读</b>
              <div class="share-readers__list">${read.length ? read.map(s => `
                <div class="share-readers__person"><b>${U.esc(s.name)}</b>
                <p>${U.esc(s.studentNo)} · ${U.esc(s.readAt || '')}</p></div>`).join('')
                : '<p class="share-readers__empty">还没有学生打开。</p>'}</div>
            </section>
            <section class="share-readers__col">
              <b class="fz-13">未读</b>
              <div class="share-readers__list">${unread.length ? unread.map(s => `
                <div class="share-readers__person"><b>${U.esc(s.name)}</b>
                <p>${U.esc(s.studentNo || '')}</p></div>`).join('')
                : '<p class="share-readers__empty">全部学生已读。</p>'}</div>
            </section>
          </div>
        </div>`
      });
    }).catch(e => Toast.err(e.message || '无法加载阅读记录'));
  }
};

Router.register('shares', { title: '更多资源分享', mount: () => TeacherShares.render() });
