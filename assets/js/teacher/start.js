'use strict';
/* 教师端 · 路由启动：仅在校验通过后才初始化默认视图 */
if (window.__teacherAuthed) Router.init('dashboard');
