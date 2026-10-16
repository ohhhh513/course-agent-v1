'use strict';

/* 三端个人中心；裁剪在本地完成，保存时才上传最终图片。 */
window.AvatarCropper = {
  size: 320,
  clamp(state) {
    const scale = Math.max(this.size / state.width, this.size / state.height) * state.zoom;
    const maxX = Math.max(0, (state.width * scale - this.size) / 2);
    const maxY = Math.max(0, (state.height * scale - this.size) / 2);
    state.x = Math.max(-maxX, Math.min(maxX, state.x));
    state.y = Math.max(-maxY, Math.min(maxY, state.y));
    return scale;
  },
  async open(file, onApply) {
    if (!file || file.size > 5 * 1024 * 1024) throw new Error('请选择不超过 5MB 的图片');
    const header = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    const jpeg = header[0] === 255 && header[1] === 216 && header[2] === 255;
    const png = [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => header[i] === byte);
    const webp = String.fromCharCode(...header.slice(0, 4)) === 'RIFF' && String.fromCharCode(...header.slice(8, 12)) === 'WEBP';
    if (!/\.(jpe?g|png|webp)$/i.test(file.name) || !(jpeg || png || webp)) throw new Error('请选择 JPG、PNG 或 WEBP 格式的图片');
    const url = URL.createObjectURL(file), image = new Image();
    image.src = url;
    try { await image.decode(); } catch (_) { URL.revokeObjectURL(url); throw new Error('图片无法读取，请重新选择'); }
    if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth * image.naturalHeight > 40000000) {
      URL.revokeObjectURL(url); throw new Error('图片尺寸过大或无效，请换一张图片');
    }
    const state = {width: image.naturalWidth, height: image.naturalHeight, zoom: 1, x: 0, y: 0};
    let pointer = null;
    const paint = canvas => {
      const scale = this.clamp(state), ctx = canvas.getContext('2d');
      ctx.setTransform(canvas.width / this.size, 0, 0, canvas.height / this.size, 0, 0);
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, this.size, this.size);
      ctx.drawImage(image, (this.size - state.width * scale) / 2 + state.x, (this.size - state.height * scale) / 2 + state.y, state.width * scale, state.height * scale);
    };
    return Modal.open({
      title: '调整头像', closeOnBackdrop: false,
      body: `<div class="avatar-crop">
        <p class="t-dim fz-13">头像比例为 <b>1:1 正方形</b>，保存尺寸为 512×512。拖动图片调整位置，圆形区域为头像显示预览。</p>
        <div class="avatar-crop__frame"><canvas id="avatarCropCanvas" width="512" height="512" tabindex="0" aria-label="头像裁剪区域，可拖动图片或用方向键调整位置"></canvas><span class="avatar-crop__guide" aria-hidden="true"></span></div>
        <label class="avatar-crop__zoom"><span>缩放</span><input id="avatarCropZoom" type="range" min="1" max="4" step="0.01" value="1" aria-label="头像缩放比例"></label>
        <button class="btn btn--sm" type="button" id="avatarCropReset">重新居中</button>
      </div>`,
      footer: '<button class="btn" data-close>取消</button><button class="btn btn--primary" type="button" id="avatarCropApply">使用此头像</button>',
      onClose: () => URL.revokeObjectURL(url),
      onMount: (ov, close) => {
        const canvas = ov.querySelector('#avatarCropCanvas'), zoom = ov.querySelector('#avatarCropZoom');
        paint(canvas);
        canvas.addEventListener('pointerdown', event => {
          if (pointer || (event.pointerType === 'mouse' && event.button !== 0)) return;
          pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
          canvas.setPointerCapture(event.pointerId); canvas.focus();
        });
        canvas.addEventListener('pointermove', event => {
          if (!pointer || pointer.id !== event.pointerId) return;
          const factor = this.size / canvas.getBoundingClientRect().width;
          state.x += (event.clientX - pointer.x) * factor;
          state.y += (event.clientY - pointer.y) * factor;
          pointer.x = event.clientX; pointer.y = event.clientY;
          paint(canvas);
        });
        const release = event => { if (pointer?.id === event.pointerId) pointer = null; };
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => canvas.addEventListener(type, release));
        canvas.addEventListener('keydown', event => {
          const delta = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
          if (!delta) return;
          event.preventDefault();
          const step = event.shiftKey ? 20 : 5;
          state.x += delta[0] * step; state.y += delta[1] * step; paint(canvas);
        });
        zoom.addEventListener('input', () => {
          const value = Number(zoom.value), ratio = value / state.zoom;
          state.x *= ratio; state.y *= ratio; state.zoom = value; paint(canvas);
        });
        ov.querySelector('#avatarCropReset').onclick = () => {
          state.zoom = 1; state.x = 0; state.y = 0; zoom.value = '1'; paint(canvas);
        };
        ov.querySelector('#avatarCropApply').onclick = async event => {
          const button = event.currentTarget; button.disabled = true;
          try {
            paint(canvas);
            const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
            if (!blob) throw new Error('裁剪失败，请重新选择图片');
            if (!ov.isConnected) return;
            onApply(blob); close();
          } catch (error) { Toast.error('头像裁剪失败', error.message); }
          finally { if (ov.isConnected) button.disabled = false; }
        };
      },
    });
  },
};

window.ProfileCenter = {
  _opening: false, _modal: null,
  origin() {
    const session = Auth.getSession();
    return session && Auth.isSessionUsable(session) ? `${session.user.userId}:${session.loginStartedAt}` : '';
  },
  async open() {
    if (this._opening || this._modal?.el.isConnected) return;
    const origin = this.origin();
    if (!origin) return;
    this._opening = true;
    let user;
    try {
      user = await API.auth.profile();
      if (this.origin() !== origin) return;
      Auth.updateUser(user);
    } catch (error) { Toast.error('个人中心加载失败', error.message); return; }
    finally { this._opening = false; }
    let avatar = null, useDefault = false, previewUrl = '', crop = null;
    let canClose = () => true, confirmation = null;
    const release = () => { if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = ''; };
    const isCurrent = () => this.origin() === origin;
    const modal = Modal.open({
      title: '个人中心', closeOnBackdrop: false,
      body: `<div class="profile-center">
        <form id="profileDetailsForm" class="stack">
          <fieldset id="profileDetailsFields" class="profile-center__fields">
            <div class="profile-center__identity"><span class="avatar profile-center__avatar" id="profileAvatar">${Auth.avatarHtml(user)}</span>
              <div><h3>${U.esc(user.name)}</h3><p class="t-dim fz-12">${U.esc(user.username || user.userId)} · ${{student:'学生',teacher:'教师',admin:'管理员'}[user.role] || ''}</p></div></div>
            <div class="row row--wrap"><button class="btn btn--sm" type="button" id="profileChooseAvatar">更换头像</button><button class="btn btn--ghost btn--sm" type="button" id="profileDefaultAvatar">恢复默认头像</button></div>
            <p class="t-dim fz-12">1:1 正方形头像，保存为 512×512；支持 JPG、PNG、WEBP，原图不超过 5MB。</p>
            <input type="file" id="profileAvatarFile" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" hidden>
            <label class="stack"><span>个性签名</span><textarea class="textarea" id="profileSignature" maxlength="120" rows="2" placeholder="写一句介绍自己的话">${U.esc(user.signature || '')}</textarea></label>
            <div class="row"><span class="t-dim fz-12" id="profileSignatureCount"></span><span class="spacer"></span><button class="btn btn--primary" type="submit">保存资料</button></div>
          </fieldset>
        </form>
        <form id="profilePasswordForm" class="stack profile-center__password">
          <fieldset id="profilePasswordFields" class="profile-center__fields">
            <h3>修改密码</h3>
            <label class="stack"><span>当前密码</span><input class="input" name="currentPassword" type="password" required autocomplete="current-password" placeholder="先输入当前密码"></label>
            <label class="stack"><span>新密码</span><input class="input" name="password" type="password" required minlength="6" maxlength="72" autocomplete="new-password" placeholder="至少 6 位"></label>
            <label class="stack"><span>确认新密码</span><input class="input" name="confirmPassword" type="password" required minlength="6" maxlength="72" autocomplete="new-password" placeholder="再次输入新密码"></label>
            <div class="row"><span class="spacer"></span><button class="btn" type="submit">修改密码</button></div>
          </fieldset>
        </form>
      </div>`,
      footer: '<button class="btn" data-close>关闭</button>',
      beforeClose: () => canClose(),
      onClose: () => { confirmation?.close(); crop?.close(); release(); if (this._modal === modal) this._modal = null; },
      onMount: (ov, close) => {
        const photo = ov.querySelector('#profileAvatar'), file = ov.querySelector('#profileAvatarFile');
        const signature = ov.querySelector('#profileSignature'), counter = ov.querySelector('#profileSignatureCount');
        const syncCount = () => { counter.textContent = `${signature.value.length} / 120`; };
        signature.addEventListener('input', syncCount); syncCount();
        ov.querySelector('#profileChooseAvatar').onclick = () => file.click();
        ov.querySelector('#profileDefaultAvatar').onclick = () => {
          avatar = null; useDefault = true; release(); photo.innerHTML = Auth.avatarHtml({...user, avatarUrl: ''});
        };
        let cropRequest = 0;
        file.addEventListener('change', async () => {
          const selected = file.files?.[0]; file.value = '';
          if (!selected) return;
          const request = ++cropRequest;
          try {
            const next = await AvatarCropper.open(selected, blob => {
              if (!ov.isConnected || !isCurrent()) return;
              avatar = blob; useDefault = false; release(); previewUrl = URL.createObjectURL(blob);
              photo.innerHTML = `<img src="${U.esc(previewUrl)}" alt="新头像预览">`;
            });
            if (!ov.isConnected || !isCurrent() || request !== cropRequest) { next.close(); return; }
            crop?.close(); crop = next;
          } catch (error) { if (ov.isConnected) Toast.error('图片无法使用', error.message); }
        });
        const passwordForm = ov.querySelector('#profilePasswordForm');
        const detailsFields = ov.querySelector('#profileDetailsFields'), passwordFields = ov.querySelector('#profilePasswordFields');
        let saving = false, exitSaving = false, allowClose = false;
        const lockFields = () => { detailsFields.disabled = passwordFields.disabled = saving || exitSaving; };
        const detailsChanged = () => !!avatar || (useDefault && !!user.avatarUrl) || signature.value.trim() !== (user.signature || '');
        const passwordChanged = () => ['currentPassword', 'password', 'confirmPassword'].some(name => passwordForm.elements[name].value !== '');
        const validatePassword = () => {
          const currentPassword = passwordForm.elements.currentPassword.value, password = passwordForm.elements.password.value;
          let message = '';
          if (!currentPassword) message = '请输入当前密码';
          else if (password.length < 6) message = '新密码至少 6 位';
          else if (new TextEncoder().encode(password).length > 72) message = '新密码过长，请缩短后再试';
          else if (password !== passwordForm.elements.confirmPassword.value) message = '两次新密码不一致';
          else if (currentPassword === password) message = '新密码不能与当前密码相同';
          if (message) { Toast.warn(message); return false; }
          return true;
        };
        const saveDetails = async () => {
          if (saving || !isCurrent()) return false;
          saving = true; lockFields();
          const form = new FormData();
          form.append('signature', signature.value.trim()); form.append('useDefaultAvatar', String(useDefault));
          if (avatar) form.append('avatar', avatar, 'avatar.png');
          try {
            const updated = await API.auth.saveProfile(form);
            if (!isCurrent()) return false;
            Auth.updateUser(updated); user = updated; avatar = null; useDefault = false;
            release();
            if (ov.isConnected) {
              photo.innerHTML = Auth.avatarHtml(updated);
              signature.value = updated.signature || ''; syncCount();
            }
            window.dispatchEvent(new CustomEvent('profileupdated', {detail: updated}));
            Toast.ok('个人资料已保存');
            return true;
          } catch (error) { if (isCurrent()) Toast.error('保存失败', error.message); }
          finally { saving = false; lockFields(); }
          return false;
        };
        const savePassword = async () => {
          if (saving || !isCurrent() || !validatePassword()) return false;
          const currentPassword = passwordForm.elements.currentPassword.value, password = passwordForm.elements.password.value;
          saving = true; lockFields();
          try {
            await API.auth.changePassword({currentPassword, password});
            if (!isCurrent()) return false;
            passwordForm.reset(); Toast.ok('密码已修改', '下次登录请使用新密码');
            return true;
          } catch (error) { if (isCurrent()) Toast.error('修改密码失败', error.message); }
          finally { saving = false; lockFields(); }
          return false;
        };
        ov.querySelector('#profileDetailsForm').addEventListener('submit', async event => {
          event.preventDefault();
          if (!exitSaving) await saveDetails();
        });
        passwordForm.addEventListener('submit', async event => {
          event.preventDefault();
          if (!exitSaving) await savePassword();
        });
        canClose = () => {
          if (saving || exitSaving) return false;
          if (allowClose || (!detailsChanged() && !passwordChanged())) return true;
          if (confirmation?.el.isConnected) return false;
          confirmation = Modal.open({
            title: '尚有修改未保存', closeOnBackdrop: false,
            body: '<p>头像、签名或填写的密码修改尚未保存。请选择保存后退出，或直接退出放弃未保存的修改。</p>',
            footer: '<button class="btn" data-close>继续编辑</button><button class="btn" type="button" id="profileDiscardExit">直接退出</button><button class="btn btn--primary" type="button" id="profileSaveExit">保存后退出</button>',
            beforeClose: () => !exitSaving,
            onClose: () => { confirmation = null; if (ov.isConnected) signature.focus(); },
            onMount: prompt => {
              prompt.querySelector('#profileDiscardExit').onclick = () => { allowClose = true; close(); };
              prompt.querySelector('#profileSaveExit').onclick = async () => {
                if (exitSaving || saving || !isCurrent()) return;
                // 先校验密码，避免输入不完整时已经保存其他资料。
                if (passwordChanged() && !validatePassword()) { confirmation.close(); return; }
                exitSaving = true; lockFields();
                prompt.querySelectorAll('button').forEach(button => { button.disabled = true; });
                let saved = false;
                try {
                  saved = (!detailsChanged() || await saveDetails()) && (!passwordChanged() || await savePassword());
                } finally {
                  exitSaving = false; lockFields();
                  prompt.querySelectorAll('button').forEach(button => { button.disabled = false; });
                }
                confirmation?.close();
                if (saved) { allowClose = true; close(); }
              };
            },
          });
          return false;
        };
      },
    });
    this._modal = modal;
  },
  init() {
    const button = document.querySelector('.sidebar__foot .user-chip');
    if (!button || button.dataset.profileBound) return;
    button.dataset.profileBound = '1'; button.type = 'button'; button.title = '个人中心';
    button.setAttribute('aria-label', '打开个人中心');
    button.addEventListener('click', () => this.open());
    document.addEventListener('error', event => {
      const img = event.target;
      if (img.matches?.('.avatar img[data-avatar-fallback], .msg__av img[data-avatar-fallback]')) img.replaceWith(document.createTextNode(img.dataset.avatarFallback));
    }, true);
    Auth.refreshUser().catch(() => {});
  },
};

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => ProfileCenter.init(), {once:true});
else ProfileCenter.init();
