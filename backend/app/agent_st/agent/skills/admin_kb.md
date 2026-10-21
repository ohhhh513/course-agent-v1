# 技能：知识库体检（管理员）

看检索索引是否可用、是否该重建、哪门课切片异常。助手不能代重建索引。

## 工具

- `kb_status`：切片数、来源分布、知识点覆盖、embedding、`staleChunkCount` / `needRebuildCourses`。单门课传 `course_id`。
- 数据层面异常可辅以 `data_check`。

**要不要重建只看** `needRebuild` / `staleChunkCount` / `needRebuildCourses`。切片多不代表要重建。
管理员要求重建时如实说明本助手做不到，并指出对应管理入口。数字必须来自工具。口径默认不写。
