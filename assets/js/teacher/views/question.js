'use strict';

  /* ================================================================
     视图 4 · AI 出题与题库管理
     ================================================================ */
  const Question = {
    tab: 'gen',
    gen: { kpIds: [], difficulty: 3, count: 6 },
    bankFilter: 'all', bankKeyword: '', bankPage: 1, bankPageSize: 10,
    draftFilter: 'all',
    render() {
      const el = U.$('#view-question');
      el.innerHTML = `
      <div class="tabs" id="qTabs" style="margin-bottom:16px">
        <button class="is-active" data-t="gen">${icon('sparkle')} AI 智能出题</button>
        <button data-t="draft">${icon('pencil')} 草稿箱</button>
        <button data-t="bank">${icon('file')} 题库管理</button>
      </div>
      <div id="qBody"></div>`;
      U.$$('#qTabs button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#qTabs button', el).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.tab = b.dataset.t;
        if (this.tab === 'gen') this.renderGen();
        else if (this.tab === 'draft') this.renderDrafts();
        else this.renderBank();
      }));
      this.renderGen();
    },

    renderGen() {
      const box = U.$('#qBody');
      API.question.genConfig({ classId: state.classId }).then(cfg => {
        this._cfg = cfg;
        box.innerHTML = `
        <div class="gen-layout">
          <div class="stack" style="gap:14px">
            <div class="card">
              <div class="card__head"><h3>${icon('upload')} 素材库</h3></div>
              <div class="card__body">
                <div class="upload" id="genUpload">
                  <div style="color:var(--brand-400)">${icon('upload')}</div>
                  <b>上传教材 / 课件 / 视频</b><span>PDF · PPT · MP4，AI 自动解析并挂载知识点</span>
                </div>
                <div class="stack" style="gap:6px;margin-top:10px">
                  ${cfg.materials.map(m => `
                    <div class="file-item">${icon(m.type === 'video' ? 'video' : m.type === 'doc' ? 'file' : 'ppt')}
                      <b>${U.esc(m.name)}</b>
                      <span class="fz-11 t-dim nowrap">${m.size}</span>
                      ${m.status === 'parsing'
                        ? `<span class="badge badge--warn">解析中 ${m.progress}%</span>`
                        : `<span class="badge badge--ok">已解析 · ${m.kpCount} 知识点</span>`}</div>`).join('')}
                </div>
              </div>
            </div>
            <div class="card">
              <div class="card__head"><h3>${icon('settings')} 出题配置</h3></div>
              <div class="card__body stack gen-config-body" style="gap:12px">
                <div class="gen-config-section gen-config-section--kp">
                  <p class="fz-12 t-dim" style="margin-bottom:8px">指定知识点（可多选）</p>
                  <div class="gen-kp-scroll" id="genKp">${cfg.kpOptions.map(k =>
                    `<button class="chip" data-kp="${k.kpId}">${U.esc(k.name)}</button>`).join('')}</div></div>
                <div class="gen-config-section gen-config-section--settings">
                  <div class="gen-config-settings">
                    <div class="gen-config-field"><p class="fz-12 t-dim" style="margin-bottom:6px">难度 <span class="mono" id="genDiffLbl">${this.gen.difficulty} 星</span></p>
                    <input type="range" min="1" max="5" value="${this.gen.difficulty}" id="genDiff" style="width:100%"></div>
                    <div class="gen-config-field"><p class="fz-12 t-dim" style="margin-bottom:6px">题量 <span class="mono" id="genCountLbl">${this.gen.count} 题</span></p>
                    <input type="range" min="1" max="10" value="${this.gen.count}" id="genCountRange" style="width:100%"></div>
                  </div>
                </div>
                <button class="btn btn--primary btn--block" id="genBtn">${icon('sparkle')} 生成习题</button>
              </div>
            </div>
          </div>
          <div class="stack" style="gap:12px">
            <div class="callout callout--brand">${icon('info')}<div>AI 将依据课程标准自动标注每题的<b>知识点定位树</b>（前后置关系 + 重难点），并附<b>材料溯源</b>（fileId + 定位），确保可解释、可溯源。</div></div>
            <div id="genResult" class="gen-result-scroll"><div class="card"><div class="card__body card__body--flush" style="padding:18px">${R.empty('配置后点击「生成习题」', 'AI 将产出并预览题目与解析', 'sparkle')}</div></div></div>
          </div>
        </div>`;

        U.$('#genUpload').addEventListener('click', () => {
          Modal.open({
            title: '上传出题素材',
            body: `<div class="upload" style="cursor:default">${icon('upload')}<b>选择文件（演示）</b><span>真实环境此处触发分片上传与异步解析</span></div>
              <div class="kv" style="margin-top:14px"><div class="kv__row"><span>支持格式</span><span>PDF / PPT / PPTX / MP4</span></div>
              <div class="kv__row"><span>解析产物</span><span>知识点挂载 · 难度标注 · 溯源定位</span></div></div>`,
            footer: `<button class="btn" data-close>关闭</button><button class="btn btn--primary" id="upOk">模拟上传</button>`,
            onMount(ov, close) {
              U.$('#upOk', ov).addEventListener('click', () => { API.question.upload({ name: '新素材.pdf' }).then(() => { Toast.ok('素材已上传', '开始异步解析'); close(); }); });
            }
          });
        });

        U.$$('#genKp .chip', box).forEach(c => c.addEventListener('click', () => {
          c.classList.toggle('is-active');
          const id = c.dataset.kp;
          if (this.gen.kpIds.includes(id)) this.gen.kpIds = this.gen.kpIds.filter(x => x !== id);
          else this.gen.kpIds.push(id);
        }));
        U.$('#genDiff', box).addEventListener('input', e => { this.gen.difficulty = +e.target.value; U.$('#genDiffLbl', box).textContent = e.target.value + ' 星'; });
        U.$('#genCountRange', box).addEventListener('input', e => {
          this.gen.count = +e.target.value;
          U.$('#genCountLbl', box).textContent = this.gen.count + ' 题';
        });
        U.$('#genBtn', box).addEventListener('click', () => {
          if (!this.gen.kpIds.length) return Toast.warn('请至少选择一个知识点');
          if (this._genBusy) return;
          this._genBusy = true;
          this._drafts = [];
          this._genTargetCount = this.gen.count;
          U.$('#genResult').innerHTML = `
            <div class="callout callout--brand gen-progress-status" id="genProgressStatus" role="status" aria-live="polite" style="margin-bottom:12px">
              ${icon('sparkle')}<div id="genProgressText">正在生成第1道题目</div>
            </div>
            <div class="card"><div class="card__head" style="padding:14px 16px"><h3>${icon('sparkle')} AI 出题中…</h3>
              <span class="spacer"></span><span class="badge badge--brand" id="genProg">0 题</span></div>
              <div class="card__body"><div class="fz-12 t-dim" id="genProc">正在调用检索与出题工具…</div></div></div>`;
          const card = (d, i) => {
            const q = d.payload || {};
            const opts = ['A', 'B', 'C', 'D'].map(k => ({
              key: k, text: (q.options || {})[k] || '', right: q.answer === k,
            }));
            const figId = 'genFig' + i;
            const optFigId = 'genOptFig' + i;
            return `
            <div class="gen-q">
              <div class="gen-q__head">
                <span class="badge badge--brand">${i + 1}</span>
                <b>单选题</b>
                <span class="badge badge--outline">${U.esc(q.chapter || '')}</span>
                <span class="badge ${d.status === 'draft' ? 'badge--ok' : 'badge--danger'}">${d.status === 'draft' ? '校验通过 · 草稿' : '校验未通过'}</span>
                <span class="badge badge--outline">#${q.id || ''}</span>
              </div>
              <div class="gen-q__body">
                <div>${U.esc(q.question || '')}</div>
                <div id="${figId}" style="margin:8px 0"></div>
                <div class="gen-q__opts">${opts.map(o => {
                  const mini = d.payload && d.payload.options_graph && d.payload.options_graph[o.key] ? `<div id="${optFigId}${o.key}" style="margin:4px 0"></div>` : '';
                  return `<div class="gen-q__opt ${o.right ? 'is-answer' : ''}"><i>${o.key}</i> ${o.text ? U.esc(o.text) : ''}${o.right ? ' ✓ 正确答案' : ''}${mini}</div>`;
                }).join('')}</div>
                <div class="callout callout--brand" style="margin-top:10px;padding:9px 11px">${icon('bulb')}
                  <div><b>解析：</b>${U.esc(q.analysis || '暂无')}</div>
                  ${d.errors && d.errors.length ? `<div class="callout callout--danger" style="margin-top:6px;padding:7px 10px">${U.esc(d.errors.join('；'))}</div>` : ''}
                </div>
              </div>
            </div>`;
          };
          const mountFigs = (d, i) => {
            const q = d.payload || {};
            if (q.graph) { const el = U.$('#genFig' + i); if (el && window.DsFigure) DsFigure.mount(el, q.graph); }
            if (q.options_graph) {
              Object.keys(q.options_graph).forEach(k => {
                const el = U.$('#genOptFig' + i + k);
                if (el && window.DsFigure) DsFigure.mount(el, q.options_graph[k]);
              });
            }
          };
          const box = U.$('#genResult');
          API.question.genStream({
            kpIds: this.gen.kpIds, types: ['single'],
            difficulty: this.gen.difficulty, count: this.gen.count,
            requirement: this.gen.requirement || ''
          }, {
            onMeta: (d) => { const p = U.$('#genProc', box); if (p) p.textContent = `批次 ${d.batchId} · 共 ${d.count} 题`; },
            onLog: (d) => {
              const p = U.$('#genProc', box);
              if (p && d.type === 'tool_start') p.textContent = `正在调用 ${d.name} …`;
            },
            onDraft: (d) => {
              this._drafts.push(d);
              const i = this._drafts.length - 1;
              if (!U.$('#genList', box)) {
                box.innerHTML = `
                  <div class="card gen-result-card">
                    <div class="card__head" style="padding:14px 16px"><h3>${icon('sparkle')} 生成预览</h3>
                      <span class="spacer"></span><span class="badge badge--brand" id="genProg">0 题</span></div>
                    <div id="genList"></div>
                    <div class="callout callout--brand gen-progress-status" id="genProgressStatus" role="status" aria-live="polite" style="margin:12px 16px">
                      ${icon('sparkle')}<div id="genProgressText">正在生成第1道题目</div>
                    </div>
                    <div class="callout callout--warn" style="margin:0 16px 12px">${icon('alert')}
                      <div>草稿已存入<b>草稿箱</b>（未进入正式题库）；切换到「草稿箱」可查看、修改后一键发布。</div></div>
                  </div>`;
              }
              U.$('#genList', box).insertAdjacentHTML('beforeend', card(d, i));
              mountFigs(d, i);
              const prog = U.$('#genProg', box);
              if (prog) prog.textContent = this._drafts.length + ' 题';
              const progressText = U.$('#genProgressText', box);
              if (progressText) {
                const nextNumber = this._drafts.length + 1;
                progressText.textContent = nextNumber <= this._genTargetCount
                  ? `正在生成第${nextNumber}道题目`
                  : '正在完成生成…';
              }
              box.scrollTop = box.scrollHeight;
            },
            onError: (d) => Toast.err('生成出错', (d && d.message) || ''),
            onDone: (d) => {
              this._genBusy = false;
              const progressStatus = U.$('#genProgressStatus', box);
              if (progressStatus) progressStatus.remove();
              const prog = U.$('#genProg', box);
              if (prog) prog.textContent = (d.count || this._drafts.length) + ' 题 · 完成';
              Toast.ok('AI 出题完成', `${d.count || 0} 道草稿已存入草稿箱`);
            },
          }).catch((e) => {
            this._genBusy = false;
            const progressText = U.$('#genProgressText', box);
            if (progressText) progressText.textContent = '生成已中断，请重试';
            Toast.err('生成失败', e && e.message);
          });
        });
      });
    },

    renderGenerated(list) {
      const box = U.$('#genResult');
      box.innerHTML = `
      <div class="card__head" style="padding:14px 16px"><h3>${icon('sparkle')} 生成预览（${list.length} 题）</h3>
        <span class="spacer"></span>
        <button class="btn btn--sm btn--outline" id="gApprove">${icon('check')} 批量审核发布</button>
        <button class="btn btn--sm btn--primary" id="gPack">${icon('target')} 生成靶向补练包</button></div>
      ${list.map((q, i) => `
        <div class="gen-q">
          <div class="gen-q__head">
            <span class="badge badge--brand">${i + 1}</span>
            <b>${q.type === 'judge' ? '判断题' : '单选题'}</b>
            <span class="badge badge--outline">难度 ${U.stars(q.difficulty)}</span>
            <span class="badge badge--outline">${U.esc(q.kpPath.join(' › '))}</span>
            ${q.isKey ? '<span class="badge badge--warn">◆ 重难点</span>' : ''}
            <span class="spacer"></span>
            <span class="badge ${q.status === 'approved' ? 'badge--ok' : 'badge--warn'}">${q.status === 'approved' ? '已审核' : '待审核'}</span>
          </div>
          <div class="gen-q__body">
            <div>${q.stem}</div>
            <div class="gen-q__opts">${q.options.map(o => `<div class="gen-q__opt ${o.right ? 'is-answer' : ''}"><i>${o.key}</i> ${o.text}${o.right ? ' ✓ 正确答案' : ''}</div>`).join('')}</div>
            <div class="callout callout--brand" style="margin-top:10px;padding:9px 11px">${icon('bulb')}
              <div><b>解析：</b>${q.analysis}<br><span class="fz-11 t-dim">溯源：${U.esc(q.sourceRef.fileId)} · ${U.esc(q.sourceRef.locator)} · 预计正确率 ${q.classCorrectRate != null ? q.classCorrectRate : '—'}%</span></div></div>
          </div>
        </div>`).join('')}`;
      U.$('#gApprove', box).addEventListener('click', () => {
        API.question.review({ qIds: list.map(q => q.qId), action: 'publish' }).then(r =>
          Toast.ok('已审核发布', r.affected + ' 道习题进入题库'));
      });
      U.$('#gPack', box).addEventListener('click', () => {
        API.question.createPack({ kpIds: list.map(q => q.kpId), count: this.gen.count, difficulty: this.gen.difficulty }).then(r =>
          Toast.ok('靶向补练包已生成', '包号 ' + r.packId + ' · 已推送'));
      });
    },

    /* ================= 草稿箱 ================= */

    renderDrafts() {
      const box = U.$('#qBody');
      box.innerHTML = `
      <div class="card">
        <div class="card__head">
          <h3>${icon('pencil')} 出题草稿箱</h3>
          <span class="badge badge--outline">仅本人可见 · 发布后进入题库</span>
          <span class="spacer"></span>
          <div class="seg" id="draftSeg">
            <button data-s="all" class="is-active">全部</button><button data-s="draft">待处理</button>
            <button data-s="invalid">校验未过</button><button data-s="published">已发布</button>
          </div>
          <button class="btn btn--sm btn--outline" id="draftRefresh">${icon('refresh')} 刷新</button>
        </div>
        <div class="card__body" id="draftList" style="max-height:calc(100vh - var(--topbar-h) - 220px);overflow-y:auto"></div>
      </div>`;
      U.$$('#draftSeg button', box).forEach(b => b.addEventListener('click', () => {
        U.$$('#draftSeg button', box).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.draftFilter = b.dataset.s; this.loadDrafts();
      }));
      U.$('#draftRefresh', box).addEventListener('click', () => this.loadDrafts());
      this.loadDrafts();
    },

    loadDrafts() {
      const list = U.$('#draftList');
      list.innerHTML = `<div class="fz-12 t-dim" style="padding:14px">加载中…</div>`;
      API.question.drafts({ status: this.draftFilter }).then(r => {
        if (!r.list.length) {
          list.innerHTML = `<div class="fz-12 t-dim" style="padding:20px;text-align:center">
            ${icon('pencil')} 暂无草稿——去「AI 智能出题」生成，草稿会自动出现在这里</div>`;
          return;
        }
        list.innerHTML = r.list.map((d, i) => this.draftCard(d, i)).join('');
        // 图题渲染
        r.list.forEach((d, i) => {
          const p = d.payload || {};
          if (p.graph) { const el = U.$('#draftFig' + i); if (el && window.DsFigure) DsFigure.mount(el, p.graph); }
          if (p.options_graph) {
            Object.keys(p.options_graph).forEach(k => {
              const el = U.$(`#draftOptFig${i}${k}`);
              if (el && window.DsFigure) DsFigure.mount(el, p.options_graph[k]);
            });
          }
        });
        // 编辑 / 发布 / 删除
        U.$('[data-dedit]', list)?.addEventListener || null;
        U.$$('#draftList [data-dedit]').forEach(b => b.addEventListener('click', () => {
          const d = r.list.find(x => x.draftId === b.dataset.dedit);
          this.openDraftEdit(d);
        }));
        U.$$('#draftList [data-dpub]').forEach(b => b.addEventListener('click', () => {
          const draftId = b.dataset.dpub;
          b.disabled = true; b.textContent = '发布中…';
          API.question.draftPublish({ draftId }).then(res => {
            Toast.ok('已发布进题库', '新题号 ' + res.qId + '，可在「题库管理」中查看');
            this.loadDrafts();
          }).catch(err => { b.disabled = false; b.textContent = '发布'; Toast.err('发布失败', err && err.message); });
        }));
        U.$$('#draftList [data-ddel]').forEach(b => b.addEventListener('click', () => {
          if (!b.dataset.armed) {
            b.dataset.armed = '1'; b.classList.add('is-arm'); b.textContent = '确认删除';
            setTimeout(() => { b.dataset.armed = ''; b.classList.remove('is-arm'); b.textContent = '删除'; }, 3000);
            return;
          }
          API.question.draftDelete({ draftId: b.dataset.ddel }).then(() => {
            Toast.ok('草稿已删除'); this.loadDrafts();
          }).catch(err => Toast.err('删除失败', err && err.message));
        }));
      }).catch(err => {
        list.innerHTML = `<div class="fz-12 t-dim" style="padding:14px">加载失败：${U.esc(err.message || '')}</div>`;
      });
    },

    draftCard(d, i) {
      const p = d.payload || {};
      const statusBadge = {
        draft: '<span class="badge badge--ok">校验通过</span>',
        invalid: '<span class="badge badge--danger">校验未过</span>',
        published: `<span class="badge badge--brand">已发布 ${U.esc(d.publishedQId || '')}</span>`,
      }[d.status] || `<span class="badge badge--outline">${U.esc(d.status)}</span>`;
      const opts = ['A', 'B', 'C', 'D'].map(k => ({
        key: k, text: (p.options || {})[k] || '', right: p.answer === k,
      }));
      const errs = (d.errors || []).map(e => `<div>${U.esc(e)}</div>`).join('');
      const canPub = d.status === 'draft';
      return `
      <div class="gen-q" style="margin:0 16px 12px">
        <div class="gen-q__head">
          <span class="badge badge--brand">${i + 1}</span>
          <b>单选题</b>
          <span class="badge badge--outline">${U.esc(d.chapter || '')}</span>
          ${statusBadge}
          <span class="badge badge--outline mono">#${p.id || ''}</span>
          <span class="spacer"></span>
          <span class="fz-11 t-dim">${U.esc(d.createdAt || '')}</span>
        </div>
        <div class="gen-q__body">
          <div>${U.esc(p.question || '')}</div>
          <div id="draftFig${i}" style="margin:8px 0"></div>
          <div class="gen-q__opts">${opts.map(o => {
            const mini = p.options_graph && p.options_graph[o.key] ? `<div id="draftOptFig${i}${o.key}" style="margin:4px 0"></div>` : '';
            return `<div class="gen-q__opt ${o.right ? 'is-answer' : ''}"><i>${o.key}</i> ${o.text ? U.esc(o.text) : ''}${o.right ? ' ✓ 正确答案' : ''}${mini}</div>`;
          }).join('')}</div>
          <div class="callout callout--brand" style="margin-top:10px;padding:9px 11px">${icon('bulb')}
            <div><b>解析：</b>${U.esc(p.analysis || '暂无')}</div></div>
          ${d.status === 'invalid' && errs ? `<div class="callout callout--danger" style="margin-top:8px;padding:7px 10px">${icon('alert')}<div>${errs}</div></div>` : ''}
        </div>
        <div class="row" style="padding:0 16px 12px;gap:8px">
          ${d.status !== 'published' ? `<button class="btn btn--sm btn--outline" data-dedit="${d.draftId}">${icon('edit')} 编辑</button>` : ''}
          ${canPub ? `<button class="btn btn--sm btn--primary" data-dpub="${d.draftId}">${icon('check')} 发布进题库</button>` : ''}
          ${d.status !== 'published' ? `<button class="btn btn--sm btn--ghost" data-ddel="${d.draftId}" style="color:var(--danger)">删除</button>` : ''}
          <span class="spacer"></span>
          ${d.publishedQId ? `<span class="fz-11 t-dim">已入库题号 <b class="mono">${U.esc(d.publishedQId)}</b></span>` : ''}
        </div>
      </div>`;
    },

    openDraftEdit(d) {
      const p = d.payload || {};
      const opts = ['A', 'B', 'C', 'D'].map(k => ({ key: k, text: (p.options || {})[k] || '', right: p.answer === k }));
      Modal.open({
        title: icon('pencil') + ' 编辑草稿 · ' + U.esc(d.draftId), size: 'wide',
        body: `
        <div class="question-edit">
          <div class="question-edit__summary">
            <div class="question-edit__summary-main">
              <span class="badge badge--brand">草稿</span>
              <div><b>修改后保存会重新校验</b><span>校验未通过仍可保存，但发布前必须通过</span></div>
            </div>
            <span class="question-edit__summary-id">原始题号 <b class="mono">#${U.esc(p.id || '')}</b></span>
          </div>
          <section class="question-edit__section">
            <div class="edit-grid">
              <div class="edit-field"><label>章节（王道小节）</label>
                <input class="input" id="dqChapter" value="${U.esc(p.chapter || '')}" placeholder="如 6.4 图的应用"></div>
              <div class="edit-field"><label>答案</label>
                <input class="input" id="dqAns" value="${U.esc(p.answer || '')}" placeholder="如 B"></div>
            </div>
          </section>
          <section class="question-edit__section">
            <div class="question-edit__section-head"><div><b>题干</b><span>${p.graph ? '本题含图，图结构暂不支持在线编辑' : ''}</span></div></div>
            <div class="question-edit__section-body">
              <textarea class="textarea question-edit__stem" id="dqStem">${U.esc(p.question || '')}</textarea>
              ${p.graph ? '<div id="draftEditFig" style="margin:8px 0"></div>' : ''}
            </div>
          </section>
          <section class="question-edit__section">
            <div class="question-edit__section-head"><div><b>选项</b><span>勾选正确答案；含小图的选项会随内容保留</span></div></div>
            <div class="question-edit__options" id="dqOpts">
              ${opts.map(o => `
                <div class="eq-opt">
                  <span class="select eq-opt-key" style="border:none;background:transparent">${o.key}</span>
                  <input class="input eq-opt-text" data-k="${o.key}" value="${U.esc(o.text)}" placeholder="选项 ${o.key}">
                  <label class="question-edit__correct"><input type="checkbox" class="dq-opt-right" data-k="${o.key}" ${o.right ? 'checked' : ''}> <span>正确答案</span></label>
                </div>`).join('')}
            </div>
          </section>
          <section class="question-edit__section">
            <div class="question-edit__section-head"><div><b>解析</b></div></div>
            <div class="question-edit__section-body">
              <textarea class="textarea question-edit__analysis" id="dqAnalysis">${U.esc(p.analysis || '')}</textarea>
            </div>
          </section>
        </div>`,
        footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="dqSave">保存草稿</button>`,
        onMount(ov, close) {
          if (p.graph && window.DsFigure) { const el = U.$('#draftEditFig', ov); if (el) DsFigure.mount(el, p.graph); }
          // 正确答案单选语义：勾一个自动取消其它
          U.$$('#dqOpts .dq-opt-right', ov).forEach(cb => cb.addEventListener('change', () => {
            if (cb.checked) U.$$('#dqOpts .dq-opt-right', ov).forEach(x => { if (x !== cb) x.checked = false; });
          }));
          U.$('#dqSave', ov).addEventListener('click', () => {
            const answer = U.$('#dqAns', ov).value.trim()
              || (U.$$('#dqOpts .dq-opt-right', ov).find(x => x.checked) || {}).dataset?.k || '';
            const newOpts = {};
            U.$$('#dqOpts .eq-opt-text', ov).forEach(inp => { newOpts[inp.dataset.k] = inp.value; });
            const payload = Object.assign({}, p, {
              question: U.$('#dqStem', ov).value,
              options: newOpts,
              answer: answer || p.answer,
              analysis: U.$('#dqAnalysis', ov).value,
              chapter: U.$('#dqChapter', ov).value.trim() || p.chapter,
            });
            API.question.draftUpdate({ draftId: d.draftId, payload }).then(res => {
              Toast.ok('草稿已保存', res.status === 'draft' ? '校验通过' : '校验未通过：' + (res.errors || []).join('；'));
              close(); Question.loadDrafts();
            }).catch(err => Toast.err('保存失败', err && err.message));
          });
        }
      });
    },

    renderBank() {
      const box = U.$('#qBody');
      box.innerHTML = `
      <div class="card">
        <div class="card__head">
          <h3>${icon('file')} 题库（${U.esc(state.classId)}）</h3>
          <span class="spacer"></span>
          <div class="search" style="width:180px">${icon('search2')}<input class="input" id="bankSearch" placeholder="题号 / 题干 / 知识点"></div>
          <div class="seg" id="bankSeg">
            <button data-s="all" class="is-active">全部</button><button data-s="pending">待审核</button>
            <button data-s="approved">已审</button><button data-s="published">已发布</button><button data-s="archived">归档</button></div>
          <button class="btn btn--sm btn--primary" id="bankImport">${icon('upload')} 批量导入</button>
        </div>
        <div class="card__body card__body--flush">
          <div class="tbl-wrap bank-table-scroll"><table class="tbl" id="bankTbl"></table></div>
          <div class="bank-pagination" id="bankPagination"></div>
        </div>
      </div>`;

      U.$$('#bankSeg button', box).forEach(b => b.addEventListener('click', () => {
        U.$$('#bankSeg button', box).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.bankFilter = b.dataset.s; this.bankPage = 1; this.loadBank();
      }));
      U.$('#bankSearch', box).addEventListener('input', e => { this.bankKeyword = e.target.value.trim(); this.bankPage = 1; this.loadBank(); });
      U.$('#bankImport', box).addEventListener('click', () => {
        Modal.open({
          title: '批量导入题目', size: 'wide',
          body: `
          <div class="import-tabs">
            <div class="import-tab is-active" data-tab="file">${icon('upload')} 文件上传</div>
            <div class="import-tab" data-tab="json">${icon('code')} JSON 粘贴</div>
          </div>

          <div class="import-panel" data-panel="file">
            <div class="callout callout--brand" style="margin-bottom:14px">${icon('info')}<div>
              <b>支持格式</b>：Word (.docx)、PDF (.pdf)、文本 (.txt)、图片 (.png/.jpg/.jpeg)<br/>
              <b>识别格式</b>：每题以数字开头（如 <code>1.</code> / <code>1)</code> / <code>第1题</code>），含题干、选项（A./B./C./D.）、答案（答案: B）
            </div></div>
            <input type="file" id="importFile" accept=".docx,.doc,.pdf,.txt,.png,.jpg,.jpeg,.bmp" style="display:none">
            <div class="import-dropzone" id="importDrop">
              <div style="font-size:48px">${icon('upload')}</div>
              <div style="margin-top:8px"><b>点击选择文件</b> 或将文件拖拽到此处</div>
              <div class="fz-12 t-dim" style="margin-top:4px">支持 .docx / .pdf / .txt / .png / .jpg / .jpeg</div>
            </div>
            <div id="importFileInfo" style="display:none;margin-top:12px"></div>
          </div>

          <div class="import-panel" data-panel="json" style="display:none">
            <div class="callout callout--brand" style="margin-bottom:14px">${icon('info')}<div>
              <b>粘贴 JSON 数组</b> — 适合已准备好结构化数据的场景
            </div></div>
            <p class="fz-12 t-dim" style="margin-bottom:6px">格式示例：<code>[{"stem":"题干...","type":"single","difficulty":3,"kp_id":"KP1","options":[{"key":"A","text":"选项A"},{"key":"B","text":"选项B","right":true}],"answer":"B"}]</code></p>
            <textarea class="code-edit" id="importJson" style="min-height:280px;font-family:monospace;font-size:12px" placeholder='在此粘贴 JSON 数组...'></textarea>
          </div>
          `,
          footer: `<button class="btn" data-close>取消</button>
            <button class="btn btn--primary" id="importSubmit">${icon('check')} 开始导入</button>`,
          onMount(ov, close) {
            let importMode = 'file';  // 'file' 或 'json'
            let selectedFile = null;
            let parsedQuestions = null;

            // Tab 切换
            U.$$('.import-tab', ov).forEach(t => t.addEventListener('click', () => {
              U.$$('.import-tab', ov).forEach(x => x.classList.remove('is-active'));
              t.classList.add('is-active');
              importMode = t.dataset.tab;
              U.$$('.import-panel', ov).forEach(p => p.style.display = p.dataset.panel === importMode ? '' : 'none');
            }));

            // ===== 文件上传模式 =====
            const dropzone = U.$('#importDrop', ov);
            const fileInput = U.$('#importFile', ov);
            const fileInfo = U.$('#importFileInfo', ov);

            dropzone.addEventListener('click', () => fileInput.click());
            ['dragenter', 'dragover'].forEach(ev => dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.add('is-hover'); }));
            ['dragleave', 'drop'].forEach(ev => dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.remove('is-hover'); }));
            dropzone.addEventListener('drop', e => {
              if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
            });
            fileInput.addEventListener('change', e => {
              if (e.target.files.length) handleFile(e.target.files[0]);
            });

            function handleFile(f) {
              selectedFile = f;
              const ext = f.name.split('.').pop().toLowerCase();
              const sizeKB = Math.round(f.size / 1024);
              fileInfo.style.display = '';
              fileInfo.innerHTML = `<div class="row fz-13" style="align-items:center">
                ${icon('file')} <b>${f.name}</b> <span class="fz-12 t-dim">· ${sizeKB}KB · .${ext}</span>
                <span class="spacer"></span><button class="btn btn--sm btn--outline" id="removeFile">移除</button>
              </div>`;
              U.$('#removeFile', fileInfo).addEventListener('click', () => {
                selectedFile = null; fileInfo.style.display = 'none'; fileInput.value = '';
              });
            }

            // ===== JSON 粘贴模式 =====
            U.$('#importJson', ov).addEventListener('input', () => { parsedQuestions = null; });

            // ===== 提交 =====
            U.$('#importSubmit', ov).addEventListener('click', async () => {
              U.$('#importSubmit', ov).disabled = true;
              try {
                if (importMode === 'file') {
                  if (!selectedFile) return Toast.warn('请先选择文件');
                  Toast.loading('正在解析 ' + selectedFile.name + ' ...');
                  const fd = new FormData();
                  fd.append('file', selectedFile);
                  const resp = await fetch('/api/v1/question/import/file', {
                    method: 'POST', headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || '') },
                    body: fd
                  });
                  const r = await resp.json();
                  const d = r.data || {};
                  Toast.ok('导入完成', d.success + ' 成功 / ' + d.failed + ' 失败 · 共 ' + d.total + ' 题');
                  if (d.errors && d.errors.length) {
                    Modal.open({ title: '导入错误详情', body: `<pre style="white-space:pre-wrap;font-size:12px">${d.errors.join('\\n')}</pre>`, footer: `<button class="btn btn--primary" data-close>知道了</button>` });
                  }
                  if (d.warnings && d.warnings.length) {
                    Toast.warn(d.warnings.join('; '));
                  }
                  close(); Question.loadBank();
                } else {
                  let qList = parsedQuestions;
                  if (!qList) {
                    const txt = U.$('#importJson', ov).value.trim();
                    if (!txt) return Toast.warn('请先粘贴 JSON');
                    try { qList = JSON.parse(txt); } catch (err) { return Toast.warn('JSON 格式错误：' + err.message); }
                  }
                  if (!Array.isArray(qList)) return Toast.warn('JSON 必须是数组格式');
                  if (qList.length === 0) return Toast.warn('没有有效的题目');
                  const body = qList[0].stem !== undefined ? { questions: qList } : qList;
                  Toast.loading('正在导入 ' + body.questions.length + ' 道题目...');
                  const r = await API.question.importBatch(body);
                  Toast.ok('导入完成', r.success + ' 成功 / ' + r.failed + ' 失败 · 共 ' + r.total + ' 题');
                  if (r.errors && r.errors.length) {
                    Modal.open({ title: '导入错误详情', body: `<pre style="white-space:pre-wrap;font-size:12px">${r.errors.join('\\n')}</pre>`, footer: `<button class="btn btn--primary" data-close>知道了</button>` });
                  }
                  close(); Question.loadBank();
                }
              } catch (err) {
                Toast.warn('导入失败：' + (err.message || String(err)));
              } finally {
                U.$('#importSubmit', ov).disabled = false;
              }
            });
          }
        });
      });
      this.loadBank();
    },

    loadBank() {
      API.question.bank({
        status: this.bankFilter, keyword: this.bankKeyword,
        page: this.bankPage, size: this.bankPageSize
      }).then(r => {
        const t = U.$('#bankTbl'); if (!t) return;
        const totalPages = Math.max(1, Math.ceil((r.total || 0) / this.bankPageSize));
        if (this.bankPage > totalPages) { this.bankPage = totalPages; return this.loadBank(); }
        const stMap = { pending: ['待审核', 'badge--warn'], approved: ['已审', 'badge--ok'], published: ['已发布', 'badge--brand'], archived: ['归档', 'badge--outline'] };
        t.innerHTML = `
          <thead><tr><th>题号</th><th>题干</th><th>题型</th><th>知识点</th><th>难度</th><th class="t-right">正确率</th><th>状态</th><th></th></tr></thead>
          <tbody>${r.list.map(q => {
            const [lbl, bd] = stMap[q.status] || ['—', 'badge--outline'];
            return `<tr>
              <td class="mono fz-12">${q.qId}</td>
              <td><div class="bank-stem-scroll">${U.esc(q.stem)}</div></td>
              <td>${q.type}</td><td>${U.esc(q.kp)}</td>
              <td>${U.stars(q.difficulty)}</td>
              <td class="t-right num ${q.correctRate === null ? 't-dim' : (q.correctRate < 60 ? 't-danger' : '')}">${q.correctRate === null ? '—' : q.correctRate + '%'}</td>
              <td><span class="badge ${bd}">${lbl}</span>${q.isKey ? ' <span class="badge badge--warn">◆</span>' : ''}</td>
              <td class="t-right"><button class="btn btn--xs btn--ghost" data-edit="${q.qId}">编辑</button>
                <button class="btn btn--xs btn--ghost" data-del="${q.qId}">删除</button></td>
            </tr>`;
          }).join('')}</tbody>`;
        U.$$('[data-edit]', t).forEach(b => b.addEventListener('click', () => this.editQ(b.dataset.edit, r.list)));
        U.$$('[data-del]', t).forEach(b => b.addEventListener('click', () => {
          API.question.remove({ qId: b.dataset.del }).then(() => { Toast.ok('已删除习题'); this.loadBank(); });
        }));

        const pager = U.$('#bankPagination');
        if (!pager) return;
        pager.innerHTML = `
          <button class="bank-page-btn" data-page-action="first" aria-label="第一页" ${this.bankPage === 1 ? 'disabled' : ''}>«</button>
          <button class="bank-page-btn" data-page-action="prev" aria-label="上一页" ${this.bankPage === 1 ? 'disabled' : ''}>‹</button>
          ${Array.from({ length: totalPages }, (_, i) => i + 1).map(p =>
            `<button class="bank-page-btn ${p === this.bankPage ? 'is-active' : ''}" data-page="${p}">${p}</button>`
          ).join('')}
          <button class="bank-page-btn" data-page-action="next" aria-label="下一页" ${this.bankPage === totalPages ? 'disabled' : ''}>›</button>
          <button class="bank-page-btn" data-page-action="last" aria-label="最后一页" ${this.bankPage === totalPages ? 'disabled' : ''}>»</button>`;
        const go = page => {
          if (page < 1 || page > totalPages || page === this.bankPage) return;
          this.bankPage = page; this.loadBank();
        };
        U.$$('[data-page]', pager).forEach(b => b.addEventListener('click', () => go(+b.dataset.page)));
        U.$('[data-page-action="first"]', pager).addEventListener('click', () => go(1));
        U.$('[data-page-action="prev"]', pager).addEventListener('click', () => go(this.bankPage - 1));
        U.$('[data-page-action="next"]', pager).addEventListener('click', () => go(this.bankPage + 1));
        U.$('[data-page-action="last"]', pager).addEventListener('click', () => go(totalPages));
      });
    },

    editQ(qId, list) {
      const q = list.find(x => x.qId === qId);
      // 先拉取完整数据（bank 返回的字段可能不全）
      API.question.bank({ status: 'all' }).then(r => {
        const full = r.list.find(x => x.qId === qId) || q;
        _openEditModal(qId, full);
      });
    }
  };

  function _openEditModal(qId, q) {
    Modal.open({
      title: icon('file') + ' 编辑习题 · ' + U.esc(qId), size: 'wide',
      body: `
      <div class="question-edit">
        <div class="question-edit__summary">
          <div class="question-edit__summary-main">
            <span class="badge badge--brand">编辑中</span>
            <div><b>题目内容与属性</b><span>修改后保存即可更新题库记录</span></div>
          </div>
          <span class="question-edit__summary-id">题号 <b class="mono">#${U.esc(qId)}</b></span>
        </div>

        <section class="question-edit__section">
          <div class="question-edit__section-head">
            <div><b>基础信息</b><span>设置题目的归属、题型和审核属性</span></div>
          </div>
          <div class="edit-grid">
            <div class="edit-field">
              <label>知识点</label>
              <input class="input" id="eqKp" list="eqKpList" value="${U.esc(q.kp || '')}" placeholder="输入知识点名称">
              <datalist id="eqKpList"></datalist>
            </div>
            <div class="edit-field">
              <label>难度</label>
              <select id="eqDiff" class="select">
                ${[1,2,3,4,5].map(i => `<option value="${i}" ${i === (q.difficulty || 3) ? 'selected' : ''}>${'★'.repeat(i)}${'☆'.repeat(5-i)} ${['入门','简单','中等','较难','困难'][i-1]}</option>`).join('')}
              </select>
            </div>
            <div class="edit-field">
              <label>来源</label>
              <input class="input" id="eqSource" value="${U.esc(q.source || q.sourceRef?.fileId || q.sourceRef?.locator || '')}" placeholder="如 讲义第3章、题库导入">
            </div>
            <div class="edit-field">
              <label>题型</label>
              <select id="eqType" class="select">
                ${[['single','单选题'],['multiple','多选题'],['blank','填空题'],['judge','判断题'],['essay','简答题']].map(([v,l]) => `<option value="${v}" ${v === (q.type || 'single') ? 'selected' : ''}>${l}</option>`).join('')}
              </select>
            </div>
            <div class="edit-field">
              <label>分值</label>
              <input class="input" id="eqScore" type="number" min="1" max="100" value="${q.score || 5}">
            </div>
            <div class="edit-field">
              <label>标记</label>
              <label class="question-edit__check">
                <input type="checkbox" id="eqKey" ${q.isKey ? 'checked' : ''}>
                <span>重点题 <em>高频考点</em></span>
              </label>
            </div>
          </div>
        </section>

        <section class="question-edit__section">
          <div class="question-edit__section-head">
            <div><b>题干</b><span>清晰描述题目要求，支持多行内容</span></div>
          </div>
          <div class="question-edit__section-body">
            <textarea class="textarea question-edit__stem" id="eqStem" placeholder="请输入题干内容">${U.esc(q.stem || '')}</textarea>
          </div>
        </section>

        <section class="question-edit__section">
          <div class="question-edit__section-head">
            <div><b>选项设置</b><span>勾选正确答案，可按需添加或删除选项</span></div>
            <button class="btn btn--xs btn--outline" id="eqAddOpt" type="button">+ 添加选项</button>
          </div>
          <div class="question-edit__options" id="eqOpts">
            ${(q.options || [{key:'A',text:'',right:false},{key:'B',text:'',right:false},{key:'C',text:'',right:false},{key:'D',text:'',right:false}]).map((o,i) => `
              <div class="eq-opt" data-i="${i}">
                <select class="select eq-opt-key" aria-label="选项字母">${'ABCDEFG'.slice(0,8).split('').map(k => `<option ${k === (o.key || 'ABCD'[i]) ? 'selected' : ''}>${k}</option>`).join('')}</select>
                <input class="input eq-opt-text" value="${U.esc(o.text || '')}" placeholder="选项 ${o.key || 'ABCD'[i]} 内容">
                <label class="question-edit__correct">
                  <input type="checkbox" class="eq-opt-right" ${o.right ? 'checked' : ''}> <span>正确答案</span>
                </label>
                <button class="btn btn--xs btn--ghost eq-opt-del" type="button">删除</button>
              </div>`).join('')}
          </div>
        </section>

        <section class="question-edit__section">
          <div class="edit-grid edit-grid--2">
            <div class="edit-field">
              <label>答案</label>
              <input class="input" id="eqAns" value="${U.esc(q.answer || '')}" placeholder="如 B 或 AB">
            </div>
            <div class="edit-field">
              <label>状态</label>
              <select id="eqStatus" class="select">
                ${[['pending','待审核'],['published','已发布'],['archived','归档']].map(([v,l]) => `<option value="${v}" ${v === (q.status || 'pending') ? 'selected' : ''}>${l}</option>`).join('')}
              </select>
            </div>
          </div>
        </section>

        <section class="question-edit__section">
          <div class="question-edit__section-head">
            <div><b>解析</b><span>补充答案依据或解题思路，帮助学生理解</span></div>
          </div>
          <div class="question-edit__section-body">
            <textarea class="textarea question-edit__analysis" id="eqAnalysis" placeholder="请输入题目解析">${U.esc(q.analysis || '')}</textarea>
          </div>
        </section>
      </div>
      `,
      footer: `<button class="btn" data-close>取消</button><button class="btn btn--primary" id="eqSave">保存修订</button>`,
      onMount(ov, close) {
        // 填充知识点 datalist
        API.question.genConfig().then(cfg => {
          const dl = U.$('#eqKpList', ov);
          if (dl && cfg.kpOptions) {
            dl.innerHTML = cfg.kpOptions.map(k => `<option value="${U.esc(k.name || k.kpName || '')}" data-id="${U.esc(k.kpId || k.kp_id || '')}"></option>`).join('');
          }
        });

        // 添加选项
        U.$('#eqAddOpt', ov)?.addEventListener('click', () => {
          const container = U.$('#eqOpts', ov);
          const idx = container.children.length;
          const letter = 'ABCDEFG'[idx] || 'A';
          const row = document.createElement('div');
          row.className = 'eq-opt';
          row.dataset.i = idx;
          row.innerHTML = `
            <select class="select eq-opt-key" aria-label="选项字母">${'ABCDEFG'.slice(0,8).split('').map(k => `<option ${k===letter?'selected':''}>${k}</option>`).join('')}</select>
            <input class="input eq-opt-text" placeholder="选项 ${letter} 内容">
            <label class="question-edit__correct"><input type="checkbox" class="eq-opt-right"> <span>正确答案</span></label>
            <button class="btn btn--xs btn--ghost eq-opt-del" type="button">删除</button>`;
          container.appendChild(row);
        });
        // 删除选项委托
        U.$('#eqOpts', ov)?.addEventListener('click', e => {
          if (e.target.classList.contains('eq-opt-del')) {
            e.target.closest('.eq-opt').remove();
            // 更新 data-i
            [...U.$('#eqOpts', ov).children].forEach((el, idx) => el.dataset.i = idx);
          }
        });

        U.$('#eqSave', ov).addEventListener('click', () => {
          // 收集选项
          const opts = [...U.$('#eqOpts', ov).children].map(row => ({
            key: row.querySelector('.eq-opt-key').value,
            text: row.querySelector('.eq-opt-text').value,
            right: row.querySelector('.eq-opt-right').checked,
          })).filter(o => o.text.trim());

          // 收集知识点 kp_id
          const kpInput = U.$('#eqKp', ov);
          const kpText = kpInput.value.trim();
          let kpId = q.kpId || '';
          const match = U.$('#eqKpList', ov)?.querySelector(`option[value="${kpText}"]`);
          if (match && match.dataset.id) kpId = match.dataset.id;

          // 收集答案（从选项 right 自动推导，如果没手动填）
          let answer = U.$('#eqAns', ov).value.trim();
          if (!answer) {
            answer = opts.filter(o => o.right).map(o => o.key).join('');
          }

          const body = {
            stem: U.$('#eqStem', ov).value,
            options: opts,
            answer,
            analysis: U.$('#eqAnalysis', ov).value,
            difficulty: parseInt(U.$('#eqDiff', ov).value),
            kp_id: kpId,
            kp_path: [kpText],
            type: U.$('#eqType', ov).value,
            score: parseInt(U.$('#eqScore', ov).value) || 5,
            is_key: U.$('#eqKey', ov).checked ? 1 : 0,
            status: U.$('#eqStatus', ov).value,
          };
          Toast.loading('保存中...');
          API.question.update({ qId, ...body }).then(() => {
            Toast.done(); Toast.ok('已保存修订'); close(); Question.loadBank();
          }).catch(err => { Toast.done(); Toast.warn('保存失败：' + (err.message || err)); });
        });
      }
    });
  }

Router.register('question', { title: 'AI 出题与题库管理', mount: () => Question.render() });
