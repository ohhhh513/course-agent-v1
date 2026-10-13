'use strict';

  /* ================================================================
     视图 4 · AI 出题与题库管理
     ================================================================ */
  const Question = {
    tab: 'gen',
    gen: { kpIds: [], difficulty: 3, count: 6 },
    bankFilter: 'all', bankKeyword: '', bankPage: 1, bankPageSize: 10,
    bankSort: 'default',                       // 2026-09-24：题库管理排序键 default | kp | correctRate | difficulty
    bankDir: 'asc',                            // 2026-09-24：排序方向 asc | desc（按知识点排序按字母 a→z）
    draftFilter: 'draft',                       // 2026-09-24：草稿箱默认「待处理」，选项仅 draft / published
    _renderToken: 0,
    _renderCourseId: '',
    render() {
      const previousCourseId = this._renderCourseId;
      this._renderCourseId = API.config.activeCourseId;
      this._renderToken += 1;
      if (previousCourseId !== this._renderCourseId) {
        // 切换课程后不能沿用上一门课程的知识点选择、草稿生成状态。
        this.gen.kpIds = [];
        this._drafts = [];
        this._genBusy = false;
        this.bankPage = 1;
        this.bankSort = 'default';     // 2026-09-24：切换课程后题库排序回到默认
        this.bankDir = 'asc';          // 2026-09-24：排序方向重置为升序
        this.draftFilter = 'draft';       // 2026-09-24：切换课程后草稿箱回到「待处理」
      }
      const el = U.$('#view-question');
      if (!API.config.activeCourseId) {
        el.innerHTML = `<div class="card"><div class="card__body"><div class="empty" style="padding:48px;text-align:center"><b>尚未创建或选择课程</b><p class="fz-12 t-dim">请先建课后再进入题库与 AI 出题。</p></div></div></div>`;
        return;
      }
      el.innerHTML = `
      <div class="tabs" id="qTabs" style="margin-bottom:16px">
        <button class="is-active" data-t="gen">${icon('sparkle')} AI 智能出题</button>
        <button data-t="draft">${icon('pencil')} 草稿箱</button>
        <button data-t="bank">${icon('file')} 题库管理</button>
        <button data-t="recycle">${icon('trash')} 回收站</button>
      </div>
      <div id="qBody"></div>`;
      U.$$('#qTabs button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#qTabs button', el).forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active'); this.tab = b.dataset.t;
        if (this.tab === 'gen') this.renderGen();
        else if (this.tab === 'draft') this.renderDrafts();
        else if (this.tab === 'recycle') this.renderRecycle();
        else this.renderBank();
      }));
      this.renderGen();
    },

    renderGen() {
      const renderToken = this._renderToken;
      const renderCourseId = this._renderCourseId;
      const isCurrent = () => renderToken === this._renderToken
        && renderCourseId === API.config.activeCourseId;
      const box = U.$('#qBody');
      API.question.genConfig({}).then(cfg => {
        if (!isCurrent()) return;
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
            onMeta: (d) => {
              if (!isCurrent()) return;
              const p = U.$('#genProc', box); if (p) p.textContent = `批次 ${d.batchId} · 共 ${d.count} 题`;
            },
            onLog: (d) => {
              if (!isCurrent()) return;
              const p = U.$('#genProc', box);
              if (p && d.type === 'tool_start') p.textContent = `正在调用 ${d.name} …`;
            },
            onDraft: (d) => {
              if (!isCurrent()) return;
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
            onError: (d) => { if (isCurrent()) Toast.err('生成出错', (d && d.message) || ''); },
            onAction: (d) => {
              // 写操作待批准（P2c）：草稿此刻**还没有**落库，需用户在卡片上点确认
              if (!isCurrent()) return;
              const confirms = ((d && d.actions) || []).filter(a => a && a.kind === 'confirm');
              if (!confirms.length) return;
              let holder = U.$('#genConfirms', box);
              if (!holder) {
                holder = document.createElement('div');
                holder.id = 'genConfirms';
                holder.className = 'gen-confirms';
                box.appendChild(holder);
              }
              holder.insertAdjacentHTML('beforeend',
                confirms.map(a => AgentChatView.confirmCardHtml(a)).join(''));
              AgentChatView.bindConfirms(holder);
              box.scrollTop = box.scrollHeight;
            },
            onDone: (d) => {
              if (!isCurrent()) return;
              this._genBusy = false;
              const progressStatus = U.$('#genProgressStatus', box);
              if (progressStatus) progressStatus.remove();
              const prog = U.$('#genProg', box);
              const made = d.count || this._drafts.length;
              const pending = U.$$('#genConfirms .confirm-card.is-pending', box).length;
              if (prog) prog.textContent = made + ' 题 · 完成';
              if (made) {
                Toast.ok('AI 出题完成', `${made} 道草稿已存入草稿箱`);
              } else if (pending) {
                // P2c：写操作要用户确认后才落库，这里不能说「已存入草稿箱」
                Toast.info('已生成待批准动作', '在上方卡片点「确认执行」后才会写入草稿箱');
              } else {
                Toast.warn('本次没有产出草稿', '可查看右侧生成过程');
              }
            },
          }).catch((e) => {
            if (!isCurrent()) return;
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
            <button data-s="draft" class="is-active">待处理</button>
            <button data-s="published">已发布</button>
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
      const renderToken = this._renderToken;
      const renderCourseId = this._renderCourseId;
      const isCurrent = () => renderToken === this._renderToken
        && renderCourseId === API.config.activeCourseId;
      if (!list) return;
      list.innerHTML = `<div class="fz-12 t-dim" style="padding:14px">加载中…</div>`;
      API.question.drafts({ status: this.draftFilter }).then(r => {
        if (!isCurrent()) return;
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
        if (!isCurrent()) return;
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
          <span class="badge badge--outline">${U.esc(d.kpName || d.kpId || '')}</span>
          ${statusBadge}
          <span class="badge badge--outline mono">#${U.esc(d.qId || p.q_id || '')}</span>
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
            <span class="question-edit__summary-id">题号 <b class="mono">#${U.esc(p.q_id || '')}</b></span>
          </div>
          <section class="question-edit__section">
            <div class="edit-grid">
              <div class="edit-field"><label>章节</label>
                <input class="input" value="${U.esc(p.chapter_id || '')}" disabled placeholder="由出题时定位"></div>
              <div class="edit-field"><label>知识点</label>
                <input class="input" value="${U.esc(p.kp_id || '')}" disabled placeholder="由出题时定位"></div>
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
          <h3>${icon('file')} 题库${API.config.activeCourseId ? '（' + U.esc(API.config.activeCourseId) + '）' : ''}</h3>
          <span class="spacer"></span>
          <div class="search" style="width:180px">${icon('search2')}<input class="input" id="bankSearch" placeholder="题干 / 知识点"></div>
          <div class="seg" id="bankSeg" title="题库排序">
            <button data-s="default" class="is-active">默认</button>
            <button data-s="kp">知识点</button>
            <button data-s="correctRate">正确率</button>
            <button data-s="difficulty">难度</button>
            <button data-s="dir" id="bankDirBtn" class="seg__dir" title="反转当前排序">
              <span class="seg__dir-arrow"></span>
              <span class="seg__dir-label">升序</span>
            </button>
          </div>
          <button class="btn btn--sm" id="bankNew">${icon('pencil')} 新建题目</button>
          <button class="btn btn--sm" id="bankImport">导入题目</button>
        </div>
        <div class="card__body card__body--flush">
          <div class="tbl-wrap bank-table-scroll"><table class="tbl" id="bankTbl"></table></div>
          <div class="bank-pagination" id="bankPagination"></div>
        </div>
      </div>`;

      const sortBtns = U.$$('#bankSeg button[data-s]:not([data-s="dir"])', box);
      sortBtns.forEach(b => b.addEventListener('click', () => {
        sortBtns.forEach(x => x.classList.remove('is-active'));
        b.classList.add('is-active');
        this.bankSort = b.dataset.s;
        this.bankPage = 1;
        this.loadBank();
      }));
      // 排序反转按钮：仅切换升降序方向，不改变当前排序键；按钮文案/箭头同步。
      const dirBtn = U.$('#bankDirBtn', box);
      if (dirBtn) {
        dirBtn.addEventListener('click', () => {
          this.bankDir = this.bankDir === 'asc' ? 'desc' : 'asc';
          this.bankPage = 1;
          // 立即刷新按钮箭头与文案，再异步刷新表格（按钮本身不在表格内，loadBank 不会动它）
          this._renderBankDirBtn(box);
          this.loadBank();
        });
      }
      this._renderBankDirBtn(box);
      U.$('#bankSearch', box).addEventListener('input', e => { this.bankKeyword = e.target.value.trim(); this.bankPage = 1; this.loadBank(); });
      U.$('#bankNew', box).addEventListener('click', () => openNewQuestionModal(() => this.loadBank()));
      U.$('#bankImport', box).addEventListener('click', () => AgentUI.openImport());
      this.loadBank();
    },

    bankHighlight(text) {
      const value = String(text == null ? '' : text);
      const keyword = (this.bankKeyword || '').trim();
      if (!keyword) return U.esc(value);
      const escapedKeyword = U.esc(keyword).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return U.esc(value).replace(new RegExp(escapedKeyword, 'gi'), hit =>
        `<mark class="bank-hit">${hit}</mark>`);
    },

    /** 渲染题库排序方向的开关按钮文案/图标：升序 ↘ 降序 ↗。 */
    _renderBankDirBtn(box) {
      // box 可能已被卸载，直接查 document 兜底，保证点击反转后一定能拿到当前 DOM。
      const btn = (box && U.$('#bankDirBtn', box)) || document.getElementById('bankDirBtn');
      if (!btn) return;
      const isAsc = this.bankDir !== 'desc';
      const arrow = btn.querySelector('.seg__dir-arrow');
      const label = btn.querySelector('.seg__dir-label');
      if (arrow) arrow.textContent = isAsc ? '↘' : '↗';
      if (label) label.textContent = isAsc ? '升序' : '降序';
      btn.classList.toggle('is-desc', !isAsc);
      btn.setAttribute('aria-pressed', String(!isAsc));
    },

    loadBank() {
      const renderToken = this._renderToken;
      const renderCourseId = this._renderCourseId;
      const isCurrent = () => renderToken === this._renderToken
        && renderCourseId === API.config.activeCourseId;
      API.question.bank({
        sort: this.bankSort, dir: this.bankDir, keyword: this.bankKeyword,
        page: this.bankPage, size: this.bankPageSize
      }).then(r => {
        if (!isCurrent()) return;
        const t = U.$('#bankTbl'); if (!t) return;
        const totalPages = Math.max(1, Math.ceil((r.total || 0) / this.bankPageSize));
        if (this.bankPage > totalPages) { this.bankPage = totalPages; return this.loadBank(); }
        const stMap = { pending: ['待审核', 'badge--warn'], approved: ['已审', 'badge--ok'], published: ['已发布', 'badge--brand'], archived: ['归档', 'badge--outline'] };
        const TYPE_LABEL = { single: '单选题', multi: '多选题', multiple: '多选题', blank: '填空题', judge: '判断题', essay: '简答题' };
        t.innerHTML = `
          <thead><tr>
            <th>题号</th><th>题干</th><th>题型</th><th>知识点</th><th>难度</th>
            <th class="t-center">重难点</th>
            <th class="t-center">正确率</th><th class="t-center">状态</th><th class="t-center">操作</th>
          </tr></thead>
        <tbody>${r.list.map(q => {
            const [lbl, bd] = stMap[q.status] || ['—', 'badge--outline'];
            const typeLabel = TYPE_LABEL[q.type] || q.type || '—';
            const kpText = (q.tags && q.tags.length
              ? q.tags.map(t => t.name || t.kpName || '').filter(Boolean).join('、')
              : (q.kp || ''));
            return `<tr>
              <td class="mono fz-12">${this.bankHighlight(q.qId)}</td>
              <td><div class="bank-stem-scroll">${this.bankHighlight(q.stem)}</div></td>
              <td>${typeLabel}</td><td>${this.bankHighlight(kpText)}</td>
              <td>${U.stars(q.difficulty)}</td>
              <td class="t-center">${q.isKey ? '<span class="badge badge--warn">◆ 重点</span>' : '<span class="t-dim">' + '—' + '</span>'}</td>
              <td class="t-center num ${q.correctRate === null ? 't-dim' : (q.correctRate < 60 ? 't-danger' : '')}">${q.correctRate === null ? '—' : q.correctRate + '%'}</td>
              <td class="t-center"><span class="badge ${bd}">${lbl}</span></td>
              <td class="t-center"><button class="btn btn--xs btn--ghost" data-edit="${q.qId}">编辑</button>
                <button class="btn btn--xs btn--ghost" type="button" data-del="${U.esc(q.qId)}">删除</button></td>
            </tr>`;
          }).join('')}</tbody>`;
        U.$$('[data-edit]', t).forEach(b => b.addEventListener('click', () => this.editQ(b.dataset.edit, r.list)));
        U.$$('[data-del]', t).forEach(b => b.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          const qId = b.getAttribute('data-del');
          if (!qId) return;
          b.disabled = true;
          API.question.remove({ qId }).then(() => {
            Toast.ok('已移入回收站', '7 天内可在「回收站」恢复');
            this.loadBank();
          }).catch(err => {
            b.disabled = false;
            Toast.error('删除失败', (err && err.message) || '请稍后重试');
          });
        }));

        const pager = U.$('#bankPagination');
        if (!pager) return;
        /* wallpaper 风格紧凑页码：首尾页恒显，当前页前后共 ~7 页，间隔处渲染可点击的「…」 */
        const WIN = 7; /* 页码窗口宽度 */
        const pages = [];
        if (totalPages <= WIN + 2) {
          for (let p = 1; p <= totalPages; p++) pages.push(p);
        } else {
          let lo = Math.max(2, this.bankPage - Math.floor((WIN - 1) / 2));
          let hi = Math.min(totalPages - 1, lo + WIN - 2);
          lo = Math.max(2, hi - WIN + 2);
          pages.push(1);
          if (lo > 2) pages.push('...');
          for (let p = lo; p <= hi; p++) pages.push(p);
          if (hi < totalPages - 1) pages.push('...');
          pages.push(totalPages);
        }
        pager.innerHTML = `
          <button class="bank-page-btn" data-page-action="prev" aria-label="上一页" ${this.bankPage === 1 ? 'disabled' : ''}>«</button>
          ${pages.map(p => p === '...'
            ? `<button class="bank-page-btn bank-page-ellipsis" data-page-action="jump" title="输入页码跳转">...</button>`
            : `<button class="bank-page-btn ${p === this.bankPage ? 'is-active' : ''}" data-page="${p}">${p}</button>`
          ).join('')}
          <button class="bank-page-btn" data-page-action="next" aria-label="下一页" ${this.bankPage === totalPages ? 'disabled' : ''}>»</button>`;
        const go = page => {
          if (page < 1 || page > totalPages || page === this.bankPage) return;
          this.bankPage = page; this.loadBank();
        };
        const openJumpModal = () => {
          Modal.open({
            title: '输入页码',
            body: `<input class="input" id="bankJumpInput" type="number" min="1" max="${totalPages}" placeholder="1 - ${totalPages}" style="width:100%">
              <p class="modal__hint" id="bankJumpHint"></p>`,
            footer: `<button class="btn btn--ghost" data-close>取消</button>
              <button class="btn btn--primary" id="bankJumpOk">确认</button>`,
            onMount(ov, close) {
              const inp = U.$('#bankJumpInput', ov);
              const ok = U.$('#bankJumpOk', ov);
              const hint = U.$('#bankJumpHint', ov);
              const doJump = () => {
                const raw = inp.value.trim();
                const v = parseInt(raw, 10);
                if (raw === '' || isNaN(v)) {
                  hint.textContent = '请输入页码数字';
                  Toast.warn('请输入页码数字');
                  return;
                }
                if (v < 1 || v > totalPages) {
                  hint.textContent = `页码超出范围，请输入 1 - ${totalPages}`;
                  Toast.warn(`请输入 1 - ${totalPages} 之间的页码`);
                  return;
                }
                hint.textContent = '';
                close(); go(v);
              };
              ok.addEventListener('click', doJump);
              inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); doJump(); } });
              setTimeout(() => { inp.focus(); inp.select(); }, 30);
            }
          });
        };
        U.$$('[data-page]', pager).forEach(b => b.addEventListener('click', () => go(+b.dataset.page)));
        U.$('[data-page-action="prev"]', pager).addEventListener('click', () => go(this.bankPage - 1));
        U.$('[data-page-action="next"]', pager).addEventListener('click', () => go(this.bankPage + 1));
        U.$$('[data-page-action="jump"]', pager).forEach(b => b.addEventListener('click', openJumpModal));
      });
    },

    renderRecycle() {
      const box = U.$('#qBody');
      if (!box) return;
      box.innerHTML = `<div class="card"><div class="card__body">${U.skeleton(160)}</div></div>`;
      const typeName = { single: '单选题', multi: '多选题', multiple: '多选题', blank: '填空题', judge: '判断题', essay: '简答题' };
      API.question.recycle().then(data => {
        const list = (data && data.list) || [];
        box.innerHTML = `
        <div class="card">
          <div class="card__head">
            <h3>${icon('trash')} 习题回收站</h3>
            <span class="badge badge--outline">${list.length} 题</span>
            <span class="spacer"></span>
            <span class="fz-12 t-dim">下架后保留 7 天，到期自动永久删除</span>
          </div>
          <div class="card__body card__body--flush">
            ${list.length ? `<div class="tbl-wrap"><table class="tbl" style="width:100%;table-layout:fixed">
              <colgroup>
                <col style="width:132px">
                <col>
                <col style="width:88px">
                <col style="width:156px">
                <col style="width:72px">
                <col style="width:148px">
              </colgroup>
              <thead><tr>
                <th>题号</th><th>题干</th><th>题型</th><th>下架时间</th><th>剩余</th><th class="t-center">操作</th>
              </tr></thead>
              <tbody>
              ${list.map((item, index) => `<tr data-recycle-detail="${index}" style="cursor:pointer">
                <td class="mono fz-12">${U.esc(item.qId)}</td>
                <td><div class="bank-stem-scroll">${U.esc(item.stem || '')}</div></td>
                <td>${U.esc(typeName[item.type] || item.type || '—')}</td>
                <td class="fz-12" style="white-space:nowrap">${U.esc(item.deletedAt || '')}</td>
                <td class="fz-12" style="white-space:nowrap">${item.daysLeft} 天</td>
                <td class="t-center" style="white-space:nowrap">
                  <button class="btn btn--xs btn--ghost" type="button" data-view="${index}">查看</button>
                  <button class="btn btn--xs btn--outline" type="button" data-restore="${U.esc(item.qId)}">恢复</button>
                </td>
              </tr>`).join('')}
              </tbody></table></div>` : '<div class="t-dim fz-13" style="padding:28px">回收站是空的。从题库删除的题目会先放在这里。</div>'}
          </div>
        </div>`;
        const openDetail = (index) => this.openRecycleDetail(list[index], () => this.renderRecycle());
        U.$$('[data-recycle-detail]', box).forEach(row => row.addEventListener('click', event => {
          if (event.target.closest('button')) return;
          openDetail(Number(row.dataset.recycleDetail));
        }));
        U.$$('[data-view]', box).forEach(button => button.addEventListener('click', () => openDetail(Number(button.dataset.view))));
        U.$$('[data-restore]', box).forEach(button => button.addEventListener('click', () => {
          API.question.restore({ qId: button.dataset.restore }).then(() => {
            Toast.ok('已恢复到题库');
            this.renderRecycle();
          }).catch(err => Toast.warn(err.message || '恢复失败'));
        }));
      }).catch(err => {
        box.innerHTML = `<div class="card"><div class="card__body t-dim">${U.esc(err.message || '回收站加载失败')}</div></div>`;
      });
    },

    openRecycleDetail(item, onRestore) {
      if (!item) return;
      const typeName = { single: '单选题', multi: '多选题', multiple: '多选题', blank: '填空题', judge: '判断题', essay: '简答题' };
      const blank = item.type === 'blank';
      const options = Array.isArray(item.options) ? item.options : [];
      const optionHtml = blank
        ? `<div class="callout">参考答案：${U.esc(item.answer || '未填写')}</div>`
        : `<div class="opts opts--readonly">${options.map(option => `
            <div class="opt${option.right ? ' is-right' : ''}">
              <span class="opt__key">${U.esc(option.key || '')}</span>
              <span style="flex:1">${U.esc(option.text || '')}</span>
              ${option.right ? '<span class="opt__flag badge badge--ok">正确答案</span>' : ''}
            </div>`).join('') || '<div class="t-dim fz-13">没有选项</div>'}</div>`;
      Modal.open({
        title: '题目详情 · ' + (item.qId || ''),
        size: 'wide',
        body: `
          <div class="stack" style="gap:12px">
            <div class="row row--wrap fz-12 t-dim">
              <span class="badge badge--outline mono">${U.esc(item.qId || '')}</span>
              <span class="badge badge--brand">${U.esc(typeName[item.type] || item.type || '—')}</span>
              <span class="badge badge--outline">${U.esc(item.chapter || '未分章')}</span>
              <span class="badge badge--outline">难度 ${U.stars(item.difficulty)}</span>
              <span class="badge badge--outline">${item.score || 0} 分</span>
              <span class="spacer"></span>
              <span>剩余 ${item.daysLeft} 天</span>
            </div>
            <div>
              <div class="fz-12 t-dim" style="margin-bottom:6px">考查知识点</div>
              <div class="row row--wrap">${(item.kpNames || []).map(name => `<span class="badge badge--outline">${U.esc(name)}</span>`).join('') || '<span class="t-dim">未标注</span>'}</div>
            </div>
            <div>
              <div class="fz-12 t-dim" style="margin-bottom:6px">题干</div>
              <div class="callout" style="white-space:pre-wrap">${U.esc(item.stem || '')}</div>
            </div>
            <div id="recycleFig"></div>
            <div>
              <div class="fz-12 t-dim" style="margin-bottom:6px">${blank ? '填空答案' : '选项'}</div>
              ${optionHtml}
            </div>
            <div>
              <div class="fz-12 t-dim" style="margin-bottom:6px">解析</div>
              <div class="callout" style="white-space:pre-wrap">${U.esc(item.analysis || '暂无解析')}</div>
            </div>
            <div class="fz-12 t-dim">下架时间 ${U.esc(item.deletedAt || '')}，将于 ${U.esc(item.purgeAt || '')} 永久删除</div>
          </div>`,
        footer: `<button class="btn" data-close>关闭</button><button class="btn btn--primary" type="button" id="recycleRestore">${icon('refresh')} 恢复到题库</button>`,
        onMount(ov, close) {
          const figure = item.figureJson;
          const figEl = U.$('#recycleFig', ov);
          if (figEl && figure) {
            if (figure.imageUrl || figure.image_url) U.mountQuestionImage(figEl, figure.imageUrl || figure.image_url);
            else if (figure.graph && window.DsFigure) DsFigure.mount(figEl, figure.graph);
          }
          U.$('#recycleRestore', ov).addEventListener('click', () => {
            API.question.restore({ qId: item.qId }).then(() => {
              Toast.ok('已恢复到题库');
              close();
              if (onRestore) onRestore();
            }).catch(err => Toast.warn(err.message || '恢复失败'));
          });
        },
      });
    },

    editQ(qId, list) {
      const q = list.find(x => x.qId === qId);
      // 先拉取完整数据（bank 返回的字段可能不全）；保留当前排序键/方向，避免列表顺序错乱
      API.question.bank({ sort: this.bankSort, dir: this.bankDir }).then(r => {
        const full = r.list.find(x => x.qId === qId) || q;
        _openEditModal(qId, full);
      });
    }
  };

  const BLANK_MARK_SRC = '_{2,}|＿{2,}|（\\s*）|\\(\\s*\\)';

  function blankCountOf(stem) {
    return (String(stem || '').match(new RegExp(BLANK_MARK_SRC, 'g')) || []).length;
  }

  function blankSeeds(q) {
    const options = Array.isArray(q && q.options) ? q.options : [];
    if (options.some(item => Array.isArray(item && item.accept))) {
      return options.map(item => (item.accept || []).join('|'));
    }
    const answer = String((q && q.answer) || '').trim();
    return answer ? answer.split(/[;；]/) : [''];
  }

  function blankEditorHtml(values, count) {
    const n = count > 0 ? count : 1;
    return Array.from({ length: n }, (_, index) => `
      <label class="stack" style="gap:4px">
        <span class="fz-12 t-dim">第 ${index + 1} 空（多种正确写法用 | 分隔）</span>
        <input class="input eq-blank-accept" value="${U.esc(values[index] || '')}" placeholder="例如：先进先出|FIFO">
      </label>`).join('');
  }

  function collectBlankOptions(root, selector = '.eq-blank-accept') {
    const rows = [...root.querySelectorAll(selector)].map(input => input.value.trim());
    if (!rows.length || rows.some(text => !text)) return null;
    const options = rows.map((text, index) => ({
      blank: index + 1,
      accept: text.split(/[|｜]/).map(item => item.trim()).filter(Boolean),
    }));
    if (options.some(item => !item.accept.length)) return null;
    return options;
  }

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
              <label>题型</label>
              <select id="eqType" class="select">
                ${[['single','单选题'],['multi','多选题'],['blank','填空题'],['judge','判断题'],['essay','简答题']].map(([v,l]) => `<option value="${v}" ${v === ((q.type === 'multiple' ? 'multi' : q.type) || 'single') ? 'selected' : ''}>${l}</option>`).join('')}
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
            <div class="edit-field">
              <label>归属章节目录</label>
              <select class="select" id="eqChapter"><option value="">（不选章）</option></select>
            </div>
            <div class="edit-field" style="grid-column:1/-1">
              <label>考查知识点标签（可多选）</label>
              <div id="eqKpTags" class="chips" style="max-height:88px;overflow:auto"></div>
            </div>
          </div>
        </section>

        <section class="question-edit__section" id="eqFigSection" style="display:${q.hasImage || q.figureJson ? '' : 'none'}">
          <div class="question-edit__section-head">
            <div><b>图像结构</b><span>与学生端练习同款 SVG 渲染；可编辑节点/边并实时预览</span></div>
            <label class="question-edit__check"><input type="checkbox" id="eqHasFig" ${q.hasImage || q.figureJson ? 'checked' : ''}> 含图像</label>
          </div>
          <div id="eqFigBox" style="display:${q.hasImage || q.figureJson ? '' : 'none'}" class="stack" style="gap:10px">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">配图方式</span>
              <select class="select" id="eqFigSource">
                <option value="file">上传图片</option>
                <option value="link">图片链接</option>
                <option value="structure">绘制结构图</option>
              </select></label>
            <div id="eqFigFile" class="stack" style="gap:6px">
              <label class="stack" style="gap:4px"><span class="fz-12 t-dim">选择图片</span>
                <input class="input" id="eqFigFileInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"></label>
              <p class="fz-12 t-dim">从本机选择 PNG、JPG、GIF 或 WEBP，不超过 8MB。不需要公网地址。不重新选择则保留已有配图。</p>
            </div>
            <div id="eqFigLink" class="stack" style="gap:6px;display:none">
              <label class="stack" style="gap:4px"><span class="fz-12 t-dim">图片链接</span>
                <input class="input" id="eqFigUrl" placeholder="粘贴 https:// 开头的图片地址"></label>
              <p class="fz-12 t-dim">直接使用该链接显示图片，请填写可公开访问的地址。</p>
            </div>
            <div id="eqFigStructure" class="stack" style="gap:10px">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
              <label class="stack" style="gap:4px"><span class="fz-12 t-dim">图型</span>
                <select class="select" id="eqFigType">
                  <option value="tree">二叉树</option>
                  <option value="adjacency_matrix">邻接矩阵</option>
                  <option value="graph">一般图</option>
                </select></label>
              <label class="stack" style="gap:4px" id="eqFigTreeRoot"><span class="fz-12 t-dim">根节点</span>
                <input class="input" id="eqFigRoot" value="A"></label>
            </div>
            <label class="stack" style="gap:4px" id="eqFigNodes"><span class="fz-12 t-dim">节点（逗号分隔）</span>
              <input class="input" id="eqFigNodesInput" value="A,B,C"></label>
            <label class="stack" style="gap:4px" id="eqFigEdgesTree"><span class="fz-12 t-dim">边（每行：父,子,left|right）</span>
              <textarea class="input" id="eqFigEdgesTreeInput" style="min-height:56px;font-family:monospace"></textarea></label>
            <label class="stack" style="gap:4px" id="eqFigEdgesGraph"><span class="fz-12 t-dim">边（每行：起点,终点,权重）</span>
              <textarea class="input" id="eqFigEdgesGraphInput" style="min-height:56px;font-family:monospace"></textarea></label>
            <div id="eqFigMatrix" style="overflow:auto;display:none"></div>
            </div>
            <div class="stack" style="gap:6px">
              <span class="fz-12 t-dim">预览</span>
              <div style="border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--bg-1)"><div id="eqFigPrev" style="min-height:120px"></div></div>
            </div>
          </div>
        </section>

        <section class="question-edit__section">
          <div class="question-edit__section-head">
            <div><b>题干</b><span>清晰描述题目要求，支持多行内容</span></div>
          </div>
          <div class="question-edit__section-body">
            <textarea class="textarea question-edit__stem" id="eqStem" placeholder="${(q.type || '') === 'blank' ? '用 ____ 标出每个空' : '输入题干…'}">${U.esc(q.stem || '')}</textarea>
            <p class="fz-12 t-dim" id="eqBlankHint" style="display:${(q.type || '') === 'blank' ? '' : 'none'};margin:8px 0 0">每个空写四个下划线 ____，或写一对空括号（）。空的数量要和下面的答案一致。</p>
          </div>
        </section>

        <section class="question-edit__section" id="eqBlankSection" style="display:${(q.type || '') === 'blank' ? '' : 'none'}">
          <div class="question-edit__section-head">
            <div><b>填空答案</b><span>按空位顺序填写，同一空的多种写法用 | 分隔</span></div>
          </div>
          <div class="stack" style="gap:8px" id="eqBlanks">${blankEditorHtml(blankSeeds(q), blankCountOf(q.stem))}</div>
        </section>

        <section class="question-edit__section" id="eqChoiceSection" style="display:${(q.type || '') === 'blank' ? 'none' : ''}">
          <div class="question-edit__section-head">
            <div><b>选项设置</b><span>勾选正确答案，可按需添加或删除选项</span></div>
            <button class="btn btn--xs btn--outline" id="eqAddOpt" type="button">+ 添加选项</button>
          </div>
          <div class="question-edit__options" id="eqOpts">
            ${((q.type === 'blank' ? null : q.options) || [{key:'A',text:'',right:false},{key:'B',text:'',right:false},{key:'C',text:'',right:false},{key:'D',text:'',right:false}]).map((o,i) => {
              const key = String(o.key || 'ABCD'[i] || 'A').toUpperCase();
              const marked = !!(o.right || String(q.answer || '').toUpperCase().includes(key));
              return `
              <div class="eq-opt" data-i="${i}">
                <select class="select eq-opt-key" aria-label="选项字母">${'ABCDEFGH'.split('').map(k => `<option ${k === key ? 'selected' : ''}>${k}</option>`).join('')}</select>
                <input class="input eq-opt-text" value="${U.esc(o.text || '')}" placeholder="选项 ${key} 内容">
                <label class="question-edit__correct">
                  <input type="checkbox" class="eq-opt-right" ${marked ? 'checked' : ''}> <span>正确答案</span>
                </label>
                <button class="btn btn--xs btn--ghost eq-opt-del" type="button">删除</button>
              </div>`;
            }).join('')}
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
        const selectedKps = new Set(q.kpIds || (q.kpId ? [q.kpId] : []));
        let structureData = null;
        API.teacher.structure().then(d => {
          structureData = d;
          const chSel = U.$('#eqChapter', ov);
          if (chSel) {
            chSel.innerHTML = '<option value="">（不选章）</option>' +
              (d.chapterOptions || []).map(c =>
                `<option value="${U.esc(c.id)}" ${c.id === (q.chapterId || '') ? 'selected' : ''}>${U.esc(c.name)}</option>`).join('');
            if (q.chapterId) chSel.value = q.chapterId;
          }
          const box = U.$('#eqKpTags', ov);
          if (box) {
            box.innerHTML = (d.kpOptions || []).map(k =>
              `<button type="button" class="chip" data-kp="${U.esc(k.id)}">${U.esc(k.name)}</button>`).join('')
              || '<span class="fz-11 t-dim">暂无知识点</span>';
            box.querySelectorAll('[data-kp]').forEach(b => {
              if (selectedKps.has(b.dataset.kp)) {
                b.classList.add('is-on');
                b.classList.add('is-active');
              }
            });
            box.addEventListener('click', e => {
              const b = e.target.closest('[data-kp]');
              if (!b) return;
              if (selectedKps.has(b.dataset.kp)) selectedKps.delete(b.dataset.kp);
              else selectedKps.add(b.dataset.kp);
              b.classList.toggle('is-on', selectedKps.has(b.dataset.kp));
              b.classList.toggle('is-active', selectedKps.has(b.dataset.kp));
            });
          }
        }).catch(() => {});

        // 图结构编辑（从已有 figure_json 预填）
        const fig = q.figureJson || q.figure_json || null;
        const linkedUrl = fig && (fig.imageUrl || fig.image_url);
        const graph = linkedUrl ? null : ((fig && (fig.graph || fig)) || null);
        if (linkedUrl) {
          const source = U.$('#eqFigSource', ov);
          const urlInput = U.$('#eqFigUrl', ov);
          const local = String(linkedUrl).startsWith('/resources/question-figures/');
          if (source) source.value = local ? 'file' : 'link';
          if (urlInput && !local) urlInput.value = linkedUrl;
        } else if (graph && graph.type) {
          const source = U.$('#eqFigSource', ov);
          if (source) source.value = 'structure';
          const t = graph.type || 'tree';
          const typeSel = U.$('#eqFigType', ov);
          if (typeSel) typeSel.value = (t === 'tree' || t === 'adjacency_matrix' || t === 'graph') ? t : 'tree';
          const nodes = (graph.nodes || []).join(',');
          if (U.$('#eqFigNodesInput', ov)) U.$('#eqFigNodesInput', ov).value = nodes;
          if (graph.type === 'tree' && U.$('#eqFigRoot', ov)) U.$('#eqFigRoot', ov).value = graph.root || '';
          if (graph.type === 'tree' && U.$('#eqFigEdgesTreeInput', ov)) {
            U.$('#eqFigEdgesTreeInput', ov).value = (graph.edges || []).map(e => `${e.from},${e.to},${e.position || 'left'}`).join('\n');
          }
          if (graph.type === 'graph' && U.$('#eqFigEdgesGraphInput', ov)) {
            U.$('#eqFigEdgesGraphInput', ov).value = (graph.edges || []).map(e => `${e.from},${e.to},${e.w ?? ''}`).join('\n');
          }
        }
        const figBox = U.$('#eqFigBox', ov);
        const hasFig = U.$('#eqHasFig', ov);
        const syncFigUI = () => {
          const t = (U.$('#eqFigType', ov) || {}).value;
          const source = (U.$('#eqFigSource', ov) || {}).value;
          const show = !!(hasFig && hasFig.checked);
          if (figBox) figBox.style.display = show ? '' : 'none';
          const fileBox = U.$('#eqFigFile', ov);
          const linkBox = U.$('#eqFigLink', ov);
          const structure = U.$('#eqFigStructure', ov);
          if (fileBox) fileBox.style.display = source === 'file' ? '' : 'none';
          if (linkBox) linkBox.style.display = source === 'link' ? '' : 'none';
          if (structure) structure.style.display = source === 'structure' ? '' : 'none';
          if (U.$('#eqFigTreeRoot', ov)) U.$('#eqFigTreeRoot', ov).style.display = source === 'structure' && t === 'tree' ? '' : 'none';
          if (U.$('#eqFigEdgesTree', ov)) U.$('#eqFigEdgesTree', ov).style.display = source === 'structure' && t === 'tree' ? '' : 'none';
          if (U.$('#eqFigEdgesGraph', ov)) U.$('#eqFigEdgesGraph', ov).style.display = source === 'structure' && t === 'graph' ? '' : 'none';
          if (!show) return;
          const prev = U.$('#eqFigPrev', ov);
          if (!prev) return;
          if (source === 'file') {
            const picked = (U.$('#eqFigFileInput', ov) || {}).files;
            if (picked && picked[0]) {
              const img = document.createElement('img');
              img.className = 'q-linked-image';
              img.alt = '题目配图';
              img.src = URL.createObjectURL(picked[0]);
              prev.replaceChildren(img);
            } else if (!U.mountQuestionImage(prev, (U.$('#eqFigUrl', ov) || {}).value) && !U.mountQuestionImage(prev, linkedUrl || '')) {
              prev.innerHTML = '<span class="fz-12 t-dim">选择图片后在这里预览</span>';
            }
            return;
          }
          if (source === 'link') {
            const url = U.httpImageUrl((U.$('#eqFigUrl', ov) || {}).value);
            if (!url) prev.innerHTML = '<span class="fz-12 t-dim">粘贴图片链接后在这里预览</span>';
            else U.mountQuestionImage(prev, url);
            return;
          }
          if (!window.DsFigure) return;
          let spec = null;
          if (t === 'tree') {
            const root = (U.$('#eqFigRoot', ov).value || '').trim();
            const nodes = (U.$('#eqFigNodesInput', ov).value || '').split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
            const edges = (U.$('#eqFigEdgesTreeInput', ov).value || '').split('\n').map(s => s.trim()).filter(Boolean).map(line => {
              const [from, to, position] = line.split(/[,，]/).map(x => x.trim());
              return { from, to, position: position === 'right' ? 'right' : 'left' };
            }).filter(e => e.from && e.to);
            if (nodes.length) spec = { type: 'tree', root: root || nodes[0], nodes, edges };
          } else if (t === 'graph') {
            const nodes = (U.$('#eqFigNodesInput', ov).value || '').split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
            const edges = (U.$('#eqFigEdgesGraphInput', ov).value || '').split('\n').map(s => s.trim()).filter(Boolean).map(line => {
              const [from, to, w] = line.split(/[,，]/).map(x => x.trim());
              return { from, to, w: w || '' };
            }).filter(e => e.from && e.to);
            if (nodes.length) spec = { type: 'graph', nodes, edges, directed: true };
          } else {
            // 矩阵：直接沿用原图预览（在线改矩阵格可后续增强）
            spec = graph;
          }
          if (spec) DsFigure.mount(prev, spec); else if (prev) prev.innerHTML = '';
        };
        if (hasFig) hasFig.addEventListener('change', syncFigUI);
        ['#eqFigType', '#eqFigRoot', '#eqFigNodesInput', '#eqFigEdgesTreeInput', '#eqFigEdgesGraphInput', '#eqFigUrl'].forEach(sel => {
          const el = U.$(sel, ov);
          if (el) el.addEventListener('input', syncFigUI);
        });
        U.$('#eqFigSource', ov)?.addEventListener('change', syncFigUI);
        U.$('#eqFigFileInput', ov)?.addEventListener('change', syncFigUI);
        syncFigUI();

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

        const syncBlankMode = () => {
          const blank = (U.$('#eqType', ov) || {}).value === 'blank';
          const choice = U.$('#eqChoiceSection', ov);
          const blanks = U.$('#eqBlankSection', ov);
          const hint = U.$('#eqBlankHint', ov);
          const stem = U.$('#eqStem', ov);
          if (stem) stem.placeholder = blank ? '用 ____ 标出每个空' : '输入题干…';
          if (choice) choice.style.display = blank ? 'none' : '';
          if (blanks) blanks.style.display = blank ? '' : 'none';
          if (hint) hint.style.display = blank ? '' : 'none';
          if (blank) {
            const box = U.$('#eqBlanks', ov);
            const stem = (U.$('#eqStem', ov) || {}).value || '';
            const count = blankCountOf(stem);
            const current = [...ov.querySelectorAll('.eq-blank-accept')].map(input => input.value);
            const target = count > 0 ? count : 1;
            if (box && target !== current.length) box.innerHTML = blankEditorHtml(current, count);
          }
        };
        U.$('#eqType', ov)?.addEventListener('change', syncBlankMode);
        U.$('#eqStem', ov)?.addEventListener('input', () => {
          if ((U.$('#eqType', ov) || {}).value === 'blank') syncBlankMode();
        });

        U.$('#eqSave', ov).addEventListener('click', async () => {
          const qType = (U.$('#eqType', ov) || {}).value || 'single';
          let blankOptions = null;
          if (qType === 'blank') {
            blankOptions = collectBlankOptions(ov);
            const marked = blankCountOf((U.$('#eqStem', ov) || {}).value || '');
            if (!blankOptions || (marked && blankOptions.length !== marked)) {
              Toast.warn('请为每个空填写答案', '题干里的 ____ 数量要和答案行数一致');
              return;
            }
          }
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

          const picked = opts.filter(o => o.right).map(o => o.key).sort();
          if (!blankOptions && (qType === 'single' || qType === 'judge') && picked.length !== 1) {
            Toast.warn('请只勾选一个正确答案');
            return;
          }
          if (!blankOptions && qType === 'multi' && picked.length < 2) {
            Toast.warn('多选题请至少勾选两个正确答案');
            return;
          }
          const answer = blankOptions
            ? blankOptions.map(item => item.accept[0]).join('；')
            : picked.join('');

          const body = {
            stem: U.$('#eqStem', ov).value,
            options: blankOptions || opts,
            answer,
            analysis: U.$('#eqAnalysis', ov).value,
            difficulty: parseInt(U.$('#eqDiff', ov).value),
            kp_id: kpId,
            kp_path: [kpText],
            type: U.$('#eqType', ov).value,
            score: parseInt(U.$('#eqScore', ov).value) || 5,
            is_key: U.$('#eqKey', ov).checked ? 1 : 0,
            chapterId: U.$('#eqChapter', ov) ? U.$('#eqChapter', ov).value : (q.chapterId || ''),
            kp_ids: [...selectedKps],
            kp_id: ([...selectedKps][0] || q.kpId || ''),
          };
          const hasFigEl = U.$('#eqHasFig', ov);
          if (hasFigEl && hasFigEl.checked) {
            const source = (U.$('#eqFigSource', ov) || {}).value;
            if (source === 'file') {
              const picked = (U.$('#eqFigFileInput', ov) || {}).files;
              let url = String(linkedUrl || '').startsWith('/resources/question-figures/') ? linkedUrl : '';
              if (picked && picked[0]) {
                const fd = new FormData();
                fd.append('file', picked[0]);
                let uploaded;
                try { uploaded = await API.teacher.uploadQuestionFigure(fd); }
                catch (err) { Toast.warn(err.message || '图片上传失败'); return; }
                url = uploaded && uploaded.url;
              }
              if (!U.httpImageUrl(url)) { Toast.warn('请选择 PNG、JPG、GIF 或 WEBP 图片'); return; }
              body.figure_json = { imageUrl: url, has_image: true };
              body.has_image = true;
            } else if (source === 'link') {
              const url = U.httpImageUrl((U.$('#eqFigUrl', ov) || {}).value);
              if (!url) { Toast.warn('请填写以 http:// 或 https:// 开头的图片链接'); return; }
              body.figure_json = { imageUrl: url, has_image: true };
              body.has_image = true;
            } else {
            const t = U.$('#eqFigType', ov).value;
            if (t === 'tree') {
              const root = (U.$('#eqFigRoot', ov).value || '').trim();
              const nodes = (U.$('#eqFigNodesInput', ov).value || '').split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
              const edges = (U.$('#eqFigEdgesTreeInput', ov).value || '').split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                const [from, to, position] = line.split(/[,，]/).map(x => x.trim());
                return { from, to, position: position === 'right' ? 'right' : 'left' };
              }).filter(e => e.from && e.to);
              body.figure_json = { graph: { type: 'tree', root: root || nodes[0], nodes, edges }, has_image: true };
              body.has_image = true;
            } else if (t === 'graph') {
              const nodes = (U.$('#eqFigNodesInput', ov).value || '').split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
              const edges = (U.$('#eqFigEdgesGraphInput', ov).value || '').split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                const [from, to, w] = line.split(/[,，]/).map(x => x.trim());
                return { from, to, w: w || '' };
              }).filter(e => e.from && e.to);
              body.figure_json = { graph: { type: 'graph', nodes, edges, directed: true }, has_image: true };
              body.has_image = true;
            } else if (fig) {
              // 矩阵暂沿用原 figure
              body.figure_json = fig;
              body.has_image = true;
            }
            }
          } else {
            body.figure_json = null;
            body.has_image = false;
          }
          Toast.loading('保存中...');
          API.question.update({ qId, ...body }).then(() => {
            Toast.done(); Toast.ok('已保存修订'); close(); Question.loadBank();
          }).catch(err => { Toast.done(); Toast.warn('保存失败：' + (err.message || err)); });
        });
      }
    });
  }

/* ================= 手动单题表单（含图结构编辑器 + 同款渲染预览） ================= */
function openNewQuestionModal(onDone) {
  const PRESETS = [
    { v: "single", t: "单选题" },
  ];

  function chOptions(list) {
    return list.map(c => `<option value="${U.esc(c.id || "")}">${U.esc(c.name)}</option>`).join("");
  }
  function kpOptions(list) {
    return list.map(k => `<option value="${U.esc(k.id)}">${U.esc(k.name)}（${U.esc(k.chapter)}）</option>`).join("");
  }

  Modal.open({
    title: "新建题目", size: "wide",
    body: `
      <div class="stack" style="gap:12px">
        <div style="display:grid;grid-template-columns:1fr 1fr 110px 110px;gap:10px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">归属章节目录</span>
            <select class="select" id="nqChapter"><option value="">加载中…</option></select></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">难度（1~5）</span>
            <select class="select" id="nqDiff">${[1,2,3,4,5].map(i => `<option ${i===3?"selected":""}>${i}</option>`).join("")}</select></label>
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">分值</span>
            <input class="input" id="nqScore" type="number" min="1" value="5"></label>
        </div>
        <div class="stack" style="gap:4px">
          <span class="fz-12 t-dim">考查知识点标签（可多选；标签=KP）</span>
          <div id="nqKpTags" class="chips" style="max-height:100px;overflow:auto"></div>
        </div>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">题型</span>
          <select class="select" id="nqType">
            <option value="single">单选题</option>
            <option value="multi">多选题</option>
            <option value="judge">判断题</option>
            <option value="blank">填空题</option>
          </select></label>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">题干</span>
          <textarea class="input" id="nqStem" style="min-height:64px" placeholder="输入题干…"></textarea>
          <span class="fz-12 t-dim" id="nqBlankHint" style="display:none">每个空写 ____ 。下面按空位填写答案，同一空多种写法用 | 分隔。</span></label>
        <div class="stack" id="nqBlanks" style="display:none;gap:8px"></div>
        <div class="stack" style="gap:6px" id="nqChoice">
          <span class="fz-12 t-dim" id="nqChoiceLabel">选项（单选；勾选圆点为正确答案）</span>
          <div class="stack" style="gap:6px" id="nqOpts">
            ${["A","B","C","D"].map((k, i) => `
              <div class="row" style="gap:8px">
                <input type="radio" name="nqAns" value="${k}" ${i===0?"checked":""} title="设为正确答案">
                <span class="fz-12 fw-6" style="width:18px">${k}</span>
                <input class="input" data-opt="${k}" placeholder="选项 ${k} 内容" style="flex:1">
                <button class="btn btn--xs btn--ghost" data-delopt="${k}" ${i<2?"disabled":""}>删除</button>
              </div>`).join("")}
          </div>
          <button class="btn btn--xs btn--ghost" id="nqAddOpt" style="align-self:flex-start">+ 添加选项</button>
        </div>
        <label class="stack" style="gap:4px"><span class="fz-12 t-dim">解析</span>
          <textarea class="input" id="nqAnalysis" style="min-height:48px" placeholder="答案解析…"></textarea></label>
        <label class="row" style="gap:6px"><input type="checkbox" id="nqHasFig">
          <span class="fz-12">本题含图像</span></label>
        <div id="nqFigBox" style="display:none" class="stack" style="gap:10px">
          <label class="stack" style="gap:4px"><span class="fz-12 t-dim">配图方式</span>
            <select class="select" id="nqFigSource">
              <option value="file">上传图片</option>
              <option value="link">图片链接</option>
              <option value="structure">绘制结构图</option>
            </select></label>
          <div id="nqFigFile" class="stack" style="gap:6px">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">选择图片</span>
              <input class="input" id="nqFigFileInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"></label>
            <p class="fz-12 t-dim">从本机选择 PNG、JPG、GIF 或 WEBP，不超过 8MB。不需要公网地址。</p>
          </div>
          <div id="nqFigLink" class="stack" style="gap:6px;display:none">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">图片链接</span>
              <input class="input" id="nqFigUrl" placeholder="粘贴 https:// 开头的图片地址"></label>
            <p class="fz-12 t-dim">直接使用该链接显示图片，请填写可公开访问的地址。</p>
          </div>
          <div id="nqFigStructure" style="display:none" class="stack" style="gap:10px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <label class="stack" style="gap:4px"><span class="fz-12 t-dim">图型</span>
              <select class="select" id="nqFigType">
                <option value="tree">二叉树</option>
                <option value="adjacency_matrix">邻接矩阵</option>
                <option value="graph">一般图</option>
              </select></label>
            <label class="stack" style="gap:4px" id="nqFigTreeRoot"><span class="fz-12 t-dim">根节点</span>
              <input class="input" id="nqFigRoot" value="A"></label>
          </div>
          <label class="stack" style="gap:4px" id="nqFigNodes"><span class="fz-12 t-dim">节点（逗号分隔）</span>
            <input class="input" id="nqFigNodesInput" value="A,B,C,D"></label>
          <label class="stack" style="gap:4px" id="nqFigEdgesTree"><span class="fz-12 t-dim">边（每行：父,子,left|right）</span>
            <textarea class="input" id="nqFigEdgesTreeInput" style="min-height:56px;font-family:monospace" placeholder="A,B,left&#10;A,C,right">A,B,left
A,C,right</textarea></label>
          <label class="stack" style="gap:4px" id="nqFigEdgesGraph" style="display:none"><span class="fz-12 t-dim">边（每行：起点,终点,权重）</span>
            <textarea class="input" id="nqFigEdgesGraphInput" style="min-height:56px;font-family:monospace" placeholder="A,B,4&#10;B,C,2"></textarea></label>
          <div id="nqFigMatrix" style="overflow:auto"></div>
          </div>
          <div class="stack" style="gap:6px">
            <span class="fz-12 t-dim">预览</span>
            <div style="border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--bg-1)"><div id="nqFigPrev" style="min-height:120px"></div></div>
          </div>
        </div>
      </div>`,
    footer: `<button class="btn" data-close>取消</button>
      <button class="btn btn--primary" id="nqSubmit">${icon("check")} 保存进题库</button>`,
    onMount(ov, close) {
      const $ = (sel) => ov.querySelector(sel);
      const selectedKps = new Set();
      let structureData = null;

      API.teacher.structure().then(d => {
        structureData = d;
        const chSel = $("#nqChapter");
        if (chSel) {
          chSel.innerHTML = '<option value="">（不选章）</option>' +
            (d.chapterOptions || (d.chapters || []).filter(c => !c.virtual).map(c => ({ id: c.id, name: c.name })))
              .map(c => `<option value="${U.esc(c.id)}">${U.esc(c.name)}</option>`).join("");
        }
        const tagBox = $("#nqKpTags");
        if (tagBox) {
          tagBox.innerHTML = (d.kpOptions || (d.chapters || []).flatMap(c => (c.kps || []).map(k => ({ id: k.id, name: k.name, chapter: c.name }))))
            .map(k => `<button type="button" class="chip" data-kp="${U.esc(k.id)}" data-ch="${U.esc(k.chapter || '')}">${U.esc(k.name)}</button>`).join("")
            || '<span class="fz-11 t-dim">暂无知识点，请先在目录页创建</span>';
        }
      }).catch(() => {});

      const paintKps = () => {
        ov.querySelectorAll("#nqKpTags [data-kp]").forEach(b => {
          const on = selectedKps.has(b.dataset.kp);
          b.classList.toggle("is-on", on);
          b.classList.toggle("is-active", on);
        });
      };
      ov.querySelector("#nqKpTags")?.addEventListener("click", e => {
        const b = e.target.closest("[data-kp]");
        if (!b) return;
        if (selectedKps.has(b.dataset.kp)) selectedKps.delete(b.dataset.kp); else selectedKps.add(b.dataset.kp);
        paintKps();
      });
      ov.querySelector("#nqChapter")?.addEventListener("change", () => {
        const chId = ov.querySelector("#nqChapter").value;
        const ch = (structureData && structureData.chapterOptions || []).find(c => c.id === chId);
        if (!ch) return;
        // 选章时自动勾选该章 KP（可再手动取消）
        ov.querySelectorAll("#nqKpTags [data-kp]").forEach(b => {
          if (b.dataset.ch === ch.name) selectedKps.add(b.dataset.kp);
        });
        paintKps();
      });

      let savedChoice = null;
      const readChoice = () => [...$("#nqOpts").querySelectorAll("[data-opt]")].map(input => ({
        key: input.dataset.opt,
        text: input.value,
        checked: !!input.parentElement.querySelector("input[name=nqAns]")?.checked,
      }));
      const writeChoice = (rows, mode) => {
        const multi = mode === "multi";
        const locked = mode === "judge";
        $("#nqChoiceLabel").textContent = multi
          ? "选项（多选；勾选所有正确答案，至少两个）"
          : locked
            ? "选项（判断；选择「正确」或「错误」）"
            : "选项（单选；勾选圆点为正确答案）";
        $("#nqAddOpt").style.display = locked ? "none" : "";
        $("#nqOpts").innerHTML = rows.map((row, index) => `
          <div class="row" style="gap:8px">
            <input type="${multi ? "checkbox" : "radio"}" name="nqAns" value="${row.key}" ${row.checked ? "checked" : ""} title="设为正确答案">
            <span class="fz-12 fw-6" style="width:18px">${row.key}</span>
            <input class="input" data-opt="${row.key}" value="${U.esc(row.text || "")}" placeholder="选项 ${row.key} 内容" style="flex:1" ${locked ? "readonly" : ""}>
            <button class="btn btn--xs btn--ghost" data-delopt="${row.key}" ${(locked || index < 2) ? "disabled" : ""}>删除</button>
          </div>`).join("");
      };
      const stemPlaceholder = {
        single: "输入题干…",
        multi: "输入题干…",
        judge: "输入需要判断对错的陈述…",
        blank: "用 ____ 标出每个空，例如：队列遵循____原则。",
      };
      const syncNewType = () => {
        const type = $("#nqType").value;
        const blank = type === "blank";
        $("#nqStem").placeholder = stemPlaceholder[type] || "输入题干…";
        $("#nqChoice").style.display = blank ? "none" : "";
        $("#nqBlankHint").style.display = blank ? "" : "none";
        $("#nqBlanks").style.display = blank ? "flex" : "none";
        if (blank) {
          const count = blankCountOf($("#nqStem").value);
          const target = count > 0 ? count : 1;
          const current = [...ov.querySelectorAll(".nq-blank-accept")].map(input => input.value);
          if (current.length !== target) {
            $("#nqBlanks").innerHTML = blankEditorHtml(current, count).replaceAll("eq-blank-accept", "nq-blank-accept");
          }
          return;
        }
        const current = readChoice();
        const isJudgePair = current.length === 2 && current[0].text === "正确" && current[1].text === "错误";
        if (type === "judge") {
          if (!isJudgePair) savedChoice = current;
          const picked = (current.find(row => row.checked) || {}).key === "B" ? "B" : "A";
          writeChoice([
            { key: "A", text: "正确", checked: picked !== "B" },
            { key: "B", text: "错误", checked: picked === "B" },
          ], "judge");
          return;
        }
        let rows = isJudgePair && savedChoice ? savedChoice : current;
        savedChoice = null;
        if (!rows.length) {
          rows = ["A", "B", "C", "D"].map((key, index) => ({ key, text: "", checked: index === 0 }));
        }
        if (type === "single") {
          const first = rows.findIndex(row => row.checked);
          rows.forEach((row, index) => { row.checked = index === (first < 0 ? 0 : first); });
        }
        writeChoice(rows, type);
      };
      $("#nqType").addEventListener("change", syncNewType);
      $("#nqStem").addEventListener("input", () => { if ($("#nqType").value === "blank") syncNewType(); });
      syncNewType();

      // 选项增删
      ov.querySelector("#nqAddOpt").addEventListener("click", () => {
        const rows = readChoice();
        const used = rows.map(row => row.key);
        const next = "ABCDEFGH".split("").find(key => !used.includes(key));
        if (!next) { Toast.warn("最多 8 个选项"); return; }
        rows.push({ key: next, text: "", checked: false });
        writeChoice(rows, $("#nqType").value);
      });
      ov.addEventListener("click", e => {
        const d = e.target.closest("[data-delopt]");
        if (d && !d.disabled) d.closest(".row").remove();
      });

      // 图编辑器
      const figBox = $("#nqFigBox");
      $("#nqHasFig").addEventListener("change", e => {
        figBox.style.display = e.target.checked ? "" : "none";
        renderPreview();
      });
      const figType = () => $("#nqFigType").value;
      const figSource = () => $("#nqFigSource").value;
      const nodesList = () => ($("#nqFigNodesInput").value || "").split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
      function syncFigUI() {
        const link = figSource() === "link";
        const file = figSource() === "file";
        const t = figType();
        $("#nqFigFile").style.display = file ? "" : "none";
        $("#nqFigLink").style.display = link ? "" : "none";
        $("#nqFigStructure").style.display = (file || link) ? "none" : "";
        $("#nqFigTreeRoot").style.display = !file && !link && t === "tree" ? "" : "none";
        $("#nqFigEdgesTree").style.display = !file && !link && t === "tree" ? "" : "none";
        $("#nqFigEdgesGraph").style.display = !file && !link && t === "graph" ? "" : "none";
        const mWrap = $("#nqFigMatrix");
        if (!file && !link && t === "adjacency_matrix") {
          const nodes = nodesList();
          mWrap.innerHTML = `<table class="ds-matrix"><thead><tr><th></th>${nodes.map(n => `<th>${U.esc(n)}</th>`).join("")}</tr></thead><tbody>${
            nodes.map((rn, i) => `<tr><th>${U.esc(rn)}</th>${nodes.map((cn, j) =>
              `<td><input class="input" data-mr="${i}" data-mc="${j}" style="width:52px;padding:2px 4px" value="0"></td>`).join("")}</tr>`).join("")}</tbody></table>`;
          mWrap.style.display = "";
        } else {
          mWrap.style.display = "none";
        }
        renderPreview();
      }
      function buildSpec() {
        const t = figType();
        const nodes = nodesList();
        if (!nodes.length) return null;
        if (t === "tree") {
          const root = ($("#nqFigRoot").value || nodes[0]).trim();
          const edges = ($("#nqFigEdgesTreeInput").value || "").split("\n").map(s => s.trim()).filter(Boolean).map(line => {
            const [from, to, position] = line.split(/[,，]/).map(x => x.trim());
            return { from, to, position: position === "right" ? "right" : "left" };
          }).filter(e => e.from && e.to);
          const all = [...new Set([root, ...nodes, ...edges.flatMap(e => [e.from, e.to])])];
          return { type: "tree", root, nodes: all, edges };
        }
        if (t === "adjacency_matrix") {
          const m = nodes.map((_, i) => nodes.map((__, j) => {
            const inp = ov.querySelector(`[data-mr="${i}"][data-mc="${j}"]`);
            return inp ? (parseFloat(inp.value) || 0) : 0;
          }));
          return { type: "adjacency_matrix", nodes, matrix: m };
        }
        const edges = ($("#nqFigEdgesGraphInput").value || "").split("\n").map(s => s.trim()).filter(Boolean).map(line => {
          const [from, to, w] = line.split(/[,，]/).map(x => x.trim());
          return { from, to, w: w || "" };
        }).filter(e => e.from && e.to);
        return { type: "graph", nodes, edges, directed: true };
      }
      function renderPreview() {
        const prev = $("#nqFigPrev");
        if (!prev || figBox.style.display === "none") return;
        if (figSource() === "file") {
          const picked = ($("#nqFigFileInput") || {}).files;
          if (picked && picked[0]) {
            const img = document.createElement("img");
            img.className = "q-linked-image";
            img.alt = "题目配图";
            img.src = URL.createObjectURL(picked[0]);
            prev.replaceChildren(img);
          } else prev.innerHTML = '<span class="fz-12 t-dim">选择图片后在这里预览</span>';
          return;
        }
        if (figSource() === "link") {
          const url = U.httpImageUrl($("#nqFigUrl").value);
          if (!url) prev.innerHTML = '<span class="fz-12 t-dim">粘贴图片链接后在这里预览</span>';
          else U.mountQuestionImage(prev, url);
          return;
        }
        if (!window.DsFigure) return;
        const spec = buildSpec();
        if (spec) DsFigure.mount(prev, spec); else prev.innerHTML = "";
      }
      ["#nqFigType", "#nqFigNodesInput", "#nqFigEdgesTreeInput", "#nqFigEdgesGraphInput", "#nqFigUrl"].forEach(sel =>
        ov.addEventListener("input", e => { if (e.target.matches(sel)) syncFigUI(); }));
      $("#nqFigSource").addEventListener("change", syncFigUI);
      $("#nqFigFileInput").addEventListener("change", syncFigUI);
      syncFigUI();

      // 提交
      ov.querySelector("#nqSubmit").addEventListener("click", async () => {
        const stem = $("#nqStem").value.trim();
        if (!stem) { Toast.warn("请输入题干"); return; }
        const qType = $("#nqType").value;
        const blank = qType === "blank";
        let opts = [];
        let answer = "";
        if (blank) {
          opts = collectBlankOptions(ov, ".nq-blank-accept");
          const marked = blankCountOf(stem);
          if (!opts || (marked && opts.length !== marked)) {
            Toast.warn("请为每个空填写答案", "题干里的 ____ 数量要和答案行数一致");
            return;
          }
          answer = opts.map(item => item.accept[0]).join("；");
        } else if (qType === "judge") {
          opts = [{ key: "A", text: "正确" }, { key: "B", text: "错误" }];
          answer = (ov.querySelector("input[name=nqAns]:checked") || {}).value || "";
          if (!answer) { Toast.warn("请选择正确或错误"); return; }
        } else {
          opts = [...ov.querySelectorAll("[data-opt]")].map(x => ({ key: x.dataset.opt, text: x.value.trim() }));
          if (opts.length < 2 || opts.some(o => !o.text)) { Toast.warn("请填写至少两个选项，且内容不能为空"); return; }
          const picked = [...ov.querySelectorAll("input[name=nqAns]:checked")].map(x => x.value).sort();
          if (qType === "multi" && picked.length < 2) { Toast.warn("多选题至少勾选两个正确答案"); return; }
          if (!picked.length) { Toast.warn("请勾选正确答案"); return; }
          answer = picked.join("");
        }
        const chapterId = $("#nqChapter") ? $("#nqChapter").value : "";
        const kpIds = [...selectedKps];
        if (!kpIds.length) { Toast.warn("请至少选择一个考查知识点标签"); return; }
        const q = {
          type: qType, difficulty: parseInt($("#nqDiff").value, 10) || 3,
          score: parseInt($("#nqScore").value, 10) || 5,
          stem, options: opts, answer,
          analysis: $("#nqAnalysis").value.trim(),
          chapterId,
          kp_id: kpIds[0],
          kp_ids: kpIds,
        };
        if ($("#nqHasFig").checked) {
          if ($("#nqFigSource").value === "file") {
            const picked = ($("#nqFigFileInput") || {}).files;
            if (!picked || !picked[0]) { Toast.warn("请选择题目图片"); return; }
            const fd = new FormData();
            fd.append("file", picked[0]);
            let uploaded;
            try { uploaded = await API.teacher.uploadQuestionFigure(fd); }
            catch (err) { Toast.warn(err.message || "图片上传失败"); return; }
            if (!uploaded || !U.httpImageUrl(uploaded.url)) { Toast.warn("图片上传失败"); return; }
            q.figure_json = { imageUrl: uploaded.url, has_image: true };
          } else if ($("#nqFigSource").value === "link") {
            const url = U.httpImageUrl($("#nqFigUrl").value);
            if (!url) { Toast.warn("请填写以 http:// 或 https:// 开头的图片链接"); return; }
            q.figure_json = { imageUrl: url, has_image: true };
          } else {
            const spec = buildSpec();
            if (!spec) { Toast.warn("图像结构不完整：请填写节点"); return; }
            q.figure_json = { graph: spec, has_image: true };
          }
        }
        API.teacher.importQuestions({ questions: [q] }).then(() => {
          close();
          Toast.ok("题目已加入草稿箱", "请到「草稿箱」发布后学生方可练习");
          if (onDone) onDone();
        }).catch(err => Toast.error("保存失败", err && err.message || ""));
      });
    }
  });
}

Router.register('question', { title: 'AI 出题与题库管理', mount: () => Question.render() });
