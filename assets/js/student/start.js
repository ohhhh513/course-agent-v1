'use strict';
/* 学生端 · 路由启动：仅在校验通过后才初始化默认视图 */
if (window.__studentAuthed) Router.init('dashboard');
