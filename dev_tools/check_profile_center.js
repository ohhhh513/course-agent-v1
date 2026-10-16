/* 运行真实个人中心、裁剪与认证代码；DOM/Canvas 替身只验逻辑，不代替浏览器验收。 */
'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class Element {
  constructor() { this.value=''; this.innerHTML=''; this.textContent=''; this.style={}; this.dataset={}; this.events={}; this.attributes={}; this.disabled=false; this.isConnected=true; }
  addEventListener(type, fn) { (this.events[type] ||= []).push(fn); }
  setAttribute(name,value) { this.attributes[name]=value; }
  focus() {} setPointerCapture() {}
  closest() { return null; }
  getBoundingClientRect() { return {width:320}; }
  async emit(type, more={}) { const event={type,target:this,currentTarget:this,preventDefault(){},...more}; for(const fn of this.events[type]||[]) await fn(event); if(this['on'+type]) await this['on'+type](event); }
  click() { if(!this.disabled)return this.emit('click'); }
}
const storage=new Map(), urls=new Set(), events=[], requests=[], modals=[];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const session={token:'x.'+Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.x',user:{userId:'ST',name:'林书瑶',role:'student'},loginStartedAt:42,activeCourseId:'C1'};
storage.set('ca_session',JSON.stringify(session));
let user={...session.user,username:'student',signature:'初始签名',avatarUrl:'',avatarChar:'林'},imageWidth=1600,imageHeight=800;
let profileFailure=false, profilePending=null;
const nodes=Object.fromEntries(['#tbAvatar','#tbUserName','#tbUid','.sidebar__foot .user-chip','#fRole','#fKey','#userTable tbody','#pickAll'].map(key=>[key,new Element()]));
const messageAvatars=[new Element(),new Element(),new Element()];
messageAvatars.forEach((el,index)=>{el.dataset.userAvatar=index===2?'OTHER':'ST';el.innerHTML='旧头像';});
const api={auth:{
 profile:async()=>({...user}),
 saveProfile:async form=>{requests.push({kind:'profile',form});if(profilePending)await profilePending;if(profileFailure)throw new Error('保存失败');user={...user,signature:form.get('signature'),avatarUrl:form.get('useDefaultAvatar')==='true'?'':form.get('avatar')?'/api/v1/auth/avatars/'+ 'a'.repeat(32)+'.png':user.avatarUrl};return {...user};},
 changePassword:async body=>{requests.push({kind:'password',body});if(body.currentPassword!=='Start123')throw new Error('当前密码不正确');return {ok:true};},
},admin:{listUsers:async()=>({list:[user]})}};
const document={readyState:'loading',addEventListener(){},querySelector:selector=>nodes[selector]||null,createTextNode:text=>({textContent:text})};
const context=vm.createContext({console,Blob,FormData,TextEncoder,atob,Date,window:{},document,API:api,
 localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 U:{$:(selector,parent)=>parent?parent.querySelector(selector):nodes[selector]||null,$$:selector=>selector==='[data-user-avatar]'?messageAvatars:[],esc},
 Toast:{ok:(...args)=>events.push(['ok',...args]),error:(...args)=>events.push(['error',...args]),warn:(...args)=>events.push(['warn',...args])},
 Router:{current:'users',views:{},register(key,cfg){this.views[key]=cfg;}},
 CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts.detail;}},
 URL:{createObjectURL:()=>{const url='blob:'+(urls.size+1)+':'+Math.random();urls.add(url);return url;},revokeObjectURL:url=>urls.delete(url)},
 Image:class{constructor(){this.naturalWidth=imageWidth;this.naturalHeight=imageHeight;}async decode(){}},
});
context.window.dispatchEvent=event=>events.push(['event',event.type]);
context.window.addEventListener=(type,fn)=>{(context.window.listeners||={})[type]=fn;};
context.Modal={open(opts){
 const ov=new Element(),map={};
 const names=opts.title==='尚有修改未保存'?['profileDiscardExit','profileSaveExit']:opts.title==='调整头像'?['avatarCropCanvas','avatarCropZoom','avatarCropReset','avatarCropApply']:
 ['profileAvatar','profileAvatarFile','profileSignature','profileSignatureCount','profileChooseAvatar','profileDefaultAvatar','profileDetailsForm','profileDetailsFields','profilePasswordForm','profilePasswordFields'];
 names.forEach(name=>map['#'+name]=new Element());ov.querySelector=selector=>map[selector]||null;ov.querySelectorAll=()=>Object.values(map);
 if(opts.title==='调整头像'){
  const canvas=map['#avatarCropCanvas'];canvas.width=canvas.height=512;
  canvas.getContext=()=>({setTransform(){},fillRect(){},drawImage(...args){canvas.draw=args.slice(1);}});
  canvas.toBlob=callback=>callback(new Blob(['cropped avatar'],{type:'image/png'}));
  map['#avatarCropZoom'].value='1';
 }else if(opts.title==='个人中心'){
  map['#profileSignature'].value=user.signature;
  const form=map['#profilePasswordForm'];form.elements={currentPassword:new Element(),password:new Element(),confirmPassword:new Element()};form.reset=()=>Object.values(form.elements).forEach(input=>input.value='');
 }
 const modal={el:ov,options:opts,close(){if(!ov.isConnected||opts.beforeClose?.(ov)===false)return;ov.isConnected=false;opts.onClose?.(ov);}};
 modals.push(modal);opts.onMount?.(ov,modal.close);return modal;
}};
vm.runInContext(fs.readFileSync('assets/js/auth.js','utf8'),context);context.Auth=context.window.Auth;
context.icon=()=>'';
vm.runInContext(fs.readFileSync('assets/js/shared/agent-chat.js','utf8'),context);
const chat=context.window.AgentChatView.create({viewKey:'ai',api:{}});
vm.runInContext(fs.readFileSync('assets/js/shared/profile-center.js','utf8'),context);
context.AvatarCropper=context.window.AvatarCropper;context.ProfileCenter=context.window.ProfileCenter;
const cropper=context.AvatarCropper,profile=context.ProfileCenter;
const pngFile={name:'picture.png',size:1000,slice:()=>({arrayBuffer:async()=>new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,0,0,0,0,0]).buffer})};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
(async()=>{
 // 共享弹窗的真实关闭入口：标题栏/底部 data-close、遮罩与程序调用均经过同一守卫。
 const modalContext=vm.createContext({document:{createElement:()=>{const el=new Element();el.remove=()=>{el.isConnected=false;};return el;},body:{appendChild(){}}},icon:()=>''});
 const commonSource=fs.readFileSync('assets/js/common.js','utf8');
 vm.runInContext(commonSource.slice(commonSource.indexOf('const Modal = {'),commonSource.indexOf('/* ---------------- 6.')),modalContext);
 const actualModal=vm.runInContext('Modal',modalContext);
 let permitted=false,closedCount=0,guardCount=0;
 const guarded=actualModal.open({title:'guard',body:'',closeOnBackdrop:false,beforeClose:()=>{guardCount++;return permitted;},onClose:()=>closedCount++});
 await guarded.el.emit('click',{target:guarded.el,}); // 遮罩不触发关闭/提醒
 assert.equal(guardCount,0);
 for(let i=0;i<2;i++)await guarded.el.emit('click',{target:{closest:selector=>selector==='[data-close]'?{}:null}});
 guarded.close();assert.equal(guardCount,3);assert(guarded.el.isConnected);assert.equal(closedCount,0);
 permitted=true;guarded.close();guarded.close();assert.equal(closedCount,1);assert(!guarded.el.isConnected);
 const unguarded=actualModal.open({title:'ordinary',body:''});unguarded.close();assert(!unguarded.el.isConnected);
 console.log('PASS 真实 Modal 关闭守卫、data-close 与程序关闭入口、外部点击静默保持、默认行为及重复清理');
 for(const [width,height]of [[1600,800],[800,1600],[300,300]])for(const zoom of [1,2,4])for(const direction of [-1,1]){
  const state={width,height,zoom,x:direction*10000,y:direction*10000},scale=cropper.clamp(state);
  const x=(320-width*scale)/2+state.x,y=(320-height*scale)/2+state.y;
  assert(x<=0&&y<=0&&x+width*scale>=320&&y+height*scale>=320);
 }
 await assert.rejects(cropper.open({...pngFile,size:5*1024*1024+1},()=>{}));
 await assert.rejects(cropper.open({...pngFile,name:'picture.svg'},()=>{}));
 let applied=null;
 const crop=await cropper.open(pngFile,blob=>applied=blob),canvas=crop.el.querySelector('#avatarCropCanvas');
 const before=canvas.draw[0];await canvas.emit('pointerdown',{pointerId:1,pointerType:'mouse',button:0,clientX:0,clientY:0});
 await canvas.emit('pointermove',{pointerId:1,clientX:20,clientY:10});assert(canvas.draw[0]>before);
 const zoom=crop.el.querySelector('#avatarCropZoom');zoom.value='2';await zoom.emit('input');assert.equal(canvas.draw[2],1280);
 await canvas.emit('keydown',{key:'ArrowLeft',shiftKey:true});
 await crop.el.querySelector('#avatarCropReset').click();assert.equal(canvas.draw[0],-160);assert.equal(canvas.draw[2],640);
 await crop.el.querySelector('#avatarCropApply').click();assert(applied instanceof Blob);assert.equal(applied.type,'image/png');assert.equal(crop.el.isConnected,false);assert.equal(urls.size,0);
 console.log('PASS 横/竖/方图裁剪覆盖、边界限制、拖动、缩放、键盘、居中、512输出及文件校验（Canvas 替身）');

 profile.init();await flush();assert.equal(nodes['.sidebar__foot .user-chip'].attributes['aria-label'],'打开个人中心');
 await profile.open();const modal=profile._modal,ov=modal.el;assert.equal(modal.options.closeOnBackdrop,false);
 const file=ov.querySelector('#profileAvatarFile');file.files=[pngFile];await file.emit('change');
 const currentCrop=modals.at(-1);assert.equal(currentCrop.options.title,'调整头像');assert.equal(requests.length,0);
 await currentCrop.el.querySelector('#avatarCropApply').click();assert(ov.querySelector('#profileAvatar').innerHTML.includes('blob:'));assert.equal(requests.length,0);
 ov.querySelector('#profileSignature').value=' 新签名 ';await ov.querySelector('#profileDetailsForm').emit('submit');
 assert.equal(requests[0].form.get('signature'),'新签名');assert.equal(requests[0].form.get('avatar').name,'avatar.png');
 assert.equal(context.Auth.currentUser().signature,'新签名');assert.equal(nodes['#tbUid'].textContent,'新签名');assert(nodes['#tbAvatar'].innerHTML.includes('/auth/avatars/'));
 assert(messageAvatars.slice(0,2).every(el=>el.innerHTML.includes(user.avatarUrl)));assert.equal(messageAvatars[2].innerHTML,'旧头像');
 for(const viewKey of ['ai','chat','assistant']){
  const view=context.window.AgentChatView.create({viewKey,api:{}}),html=view.tpl({role:'me',content:'保留原消息'});
  assert(html.includes('data-user-avatar="ST"'));assert(html.includes(user.avatarUrl));assert(html.includes('保留原消息'));
 }
 assert.equal(JSON.parse(storage.get('ca_session')).loginStartedAt,42);assert.equal(JSON.parse(storage.get('ca_session')).activeCourseId,'C1');
 await ov.querySelector('#profileDefaultAvatar').click();await ov.querySelector('#profileDetailsForm').emit('submit');assert.equal(requests.at(-1).form.get('useDefaultAvatar'),'true');assert.equal(context.Auth.currentUser().avatarUrl,'');
 assert(messageAvatars.slice(0,2).every(el=>el.innerHTML==='林'));assert(!chat.tpl({role:'me',content:'默认头像'}).includes('/auth/avatars/'));
 const passwordForm=ov.querySelector('#profilePasswordForm'),inputs=passwordForm.elements;
 inputs.currentPassword.value='Start123';inputs.password.value='Changed123';inputs.confirmPassword.value='wrong';
 const count=requests.length;await passwordForm.emit('submit');assert.equal(requests.length,count);
 inputs.confirmPassword.value='Changed123';inputs.currentPassword.value='wrong';await passwordForm.emit('submit');assert.equal(inputs.currentPassword.value,'wrong');assert.equal(events.at(-1)[0],'error');
 inputs.currentPassword.value='Start123';await passwordForm.emit('submit');assert.equal(requests.at(-1).body.currentPassword,'Start123');assert.equal(inputs.password.value,'');
 assert.equal(context.Auth.updateUser({userId:'OTHER',signature:'错误账号'}),false);
 modal.close();assert.equal(urls.size,0);assert.equal(profile._modal,null);
 console.log('PASS 个人中心入口、外部关闭保护、裁剪后才待保存、头像/默认/签名保存、会话及侧栏同步、改密字段/重复校验/错误恢复与资源释放（DOM 替身）');

 const openProfile=async()=>{await profile.open();return profile._modal;};
 const promptFor=modal=>{modal.close();assert(modal.el.isConnected);const prompt=modals.at(-1);assert.equal(prompt.options.title,'尚有修改未保存');return prompt;};
 let edited=await openProfile();edited.close();assert(!edited.el.isConnected);
 edited=await openProfile();let signature=edited.el.querySelector('#profileSignature');
 signature.value='临时修改';let prompt=promptFor(edited),beforeRequests=requests.length;
 edited.close();assert.equal(modals.at(-1),prompt); // 不重复堆叠确认框
 prompt.close();assert(edited.el.isConnected);assert.equal(signature.value,'临时修改');
 signature.value=user.signature;edited.close();assert(!edited.el.isConnected);
 edited=await openProfile();signature=edited.el.querySelector('#profileSignature');signature.value='放弃修改';
 prompt=promptFor(edited);await prompt.el.querySelector('#profileDiscardExit').click();
 assert(!edited.el.isConnected);assert(!prompt.el.isConnected);assert.equal(requests.length,beforeRequests);
 edited=await openProfile();signature=edited.el.querySelector('#profileSignature');signature.value='退出并保存';
 prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();
 assert(!edited.el.isConnected);assert.equal(user.signature,'退出并保存');
 edited=await openProfile();signature=edited.el.querySelector('#profileSignature');signature.value='失败要保留';profileFailure=true;
 prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();
 assert(edited.el.isConnected);assert.equal(signature.value,'失败要保留');assert(!edited.el.querySelector('#profileDetailsFields').disabled);
 profileFailure=false;prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();assert(!edited.el.isConnected);
 edited=await openProfile();const pendingInputs=edited.el.querySelector('#profilePasswordForm').elements;
 edited.el.querySelector('#profileSignature').value='资料和密码同时修改';
 pendingInputs.currentPassword.value='Start123';prompt=promptFor(edited);beforeRequests=requests.length;
 await prompt.el.querySelector('#profileSaveExit').click();assert.equal(requests.length,beforeRequests);assert(edited.el.isConnected);assert.equal(pendingInputs.currentPassword.value,'Start123');
 assert.equal(edited.el.querySelector('#profileSignature').value,'资料和密码同时修改');assert.notEqual(user.signature,'资料和密码同时修改');
 pendingInputs.password.value='Changed123';pendingInputs.confirmPassword.value='Changed123';pendingInputs.currentPassword.value='wrong';
 prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();assert(edited.el.isConnected);assert.equal(pendingInputs.password.value,'Changed123');
 assert.equal(user.signature,'资料和密码同时修改'); // 资料已保存，密码校验失败仍留在编辑界面
 beforeRequests=requests.filter(request=>request.kind==='profile').length;
 pendingInputs.currentPassword.value='Start123';prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();assert(!edited.el.isConnected);
 assert.equal(requests.filter(request=>request.kind==='profile').length,beforeRequests); // 重试只保存仍未成功的密码
 edited=await openProfile();signature=edited.el.querySelector('#profileSignature');signature.value='保存中';
 let resolveSave;profilePending=new Promise(resolve=>resolveSave=resolve);
 prompt=promptFor(edited);const saveAndExit=prompt.el.querySelector('#profileSaveExit').click();await flush();
 beforeRequests=requests.length;edited.close();prompt.close();await prompt.el.querySelector('#profileDiscardExit').click();
 await edited.el.querySelector('#profileDetailsForm').emit('submit');
 assert(edited.el.isConnected&&prompt.el.isConnected);assert.equal(requests.length,beforeRequests);assert(edited.el.querySelector('#profilePasswordFields').disabled);
 resolveSave();await saveAndExit;profilePending=null;assert(!edited.el.isConnected);
 // 仅头像变更也必须提醒，放弃后释放裁剪预览；默认头像恢复到原样不提示。
 edited=await openProfile();const avatarFile=edited.el.querySelector('#profileAvatarFile');avatarFile.files=[pngFile];await avatarFile.emit('change');
 await modals.at(-1).el.querySelector('#avatarCropApply').click();assert(urls.size>0);
 prompt=promptFor(edited);await prompt.el.querySelector('#profileDiscardExit').click();assert.equal(urls.size,0);
 user.avatarUrl='/api/v1/auth/avatars/'+'c'.repeat(32)+'.png';edited=await openProfile();
 await edited.el.querySelector('#profileDefaultAvatar').click();prompt=promptFor(edited);await prompt.el.querySelector('#profileSaveExit').click();assert.equal(user.avatarUrl,'');assert(!edited.el.isConnected);
 edited=await openProfile();await edited.el.querySelector('#profileDefaultAvatar').click();edited.close();assert(!edited.el.isConnected);
 console.log('PASS 未修改/还原关闭、签名/头像/默认头像/密码未保存提醒、继续编辑、放弃退出、保存后退出、失败保留、重复关闭及保存中保护（DOM 替身）');

 const originalProfile=api.auth.profile,oldUser={...context.Auth.currentUser()};
 let resolveOld;api.auth.profile=()=>new Promise(resolve=>resolveOld=resolve);
 const staleRefresh=context.Auth.refreshUser();
 const newest={...oldUser,signature:'已保存的新资料',avatarUrl:'/api/v1/auth/avatars/'+'d'.repeat(32)+'.png'};
 context.Auth.updateUser(newest);resolveOld(oldUser);await staleRefresh;
 assert.equal(context.Auth.currentUser().avatarUrl,newest.avatarUrl);assert.equal(context.Auth.currentUser().signature,newest.signature);
 assert(nodes['#tbAvatar'].innerHTML.includes(newest.avatarUrl));assert(messageAvatars[0].innerHTML.includes(newest.avatarUrl));
 let resolveFirst,resolveSecond;
 api.auth.profile=()=>new Promise(resolve=>resolveFirst=resolve);const firstRefresh=context.Auth.refreshUser();
 api.auth.profile=()=>new Promise(resolve=>resolveSecond=resolve);const secondRefresh=context.Auth.refreshUser();
 resolveFirst(oldUser);await firstRefresh;assert.equal(context.Auth.currentUser().avatarUrl,newest.avatarUrl);
 resolveSecond({...newest,signature:'最近一次读取'});await secondRefresh;assert.equal(context.Auth.currentUser().signature,'最近一次读取');
 api.auth.profile=originalProfile;user={...context.Auth.currentUser()};
 assert(!context.Auth.avatarHtml(user).includes('loading="lazy"'));
 assert(!context.Auth.avatarHtml({...user,avatarUrl:'https://example.com/unsafe.png'}).includes('<img'));
 console.log('PASS 三端新消息图片头像、已显示消息及侧栏即时同步、默认头像恢复、其他用户隔离与旧异步资料覆盖保护（DOM 替身）');

 vm.runInContext(fs.readFileSync('assets/js/admin/views/users.js','utf8'),context);
 const admin=vm.runInContext('AdminUsers',context);user={...user,signature:'<script>签名</script>',avatarUrl:'/api/v1/auth/avatars/'+'b'.repeat(32)+'.png'};
 admin.load();await flush();const table=nodes['#userTable tbody'].innerHTML;
 assert(table.includes('&lt;script&gt;签名&lt;/script&gt;'));assert(!table.includes('<script>'));assert(table.includes(user.avatarUrl));assert.equal(typeof context.Router.views.users.update,'function');
 user.signature='最新签名';context.window.listeners.focus();await flush();assert(nodes['#userTable tbody'].innerHTML.includes('最新签名'));
 console.log('PASS 管理员账号头像、签名转义显示及重新进入刷新入口（DOM 替身）；未执行任何真实账号写入。');
})().catch(error=>{console.error(error);process.exitCode=1;});
