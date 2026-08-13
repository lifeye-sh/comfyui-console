# V2 Iteration 5 验收记录（2026-08-13）

## 本轮交付

- 新增生成类型配置版本模型，区分草稿、已发布和已替代状态。
- 新增 Alembic `0006` 非破坏性迁移：配置版本表、生成类型发布指针、任务配置版本快照。
- 新增 `/api/v2/generation-types/{id}/config` 配置接口组。
- 支持读取/保存草稿、配置校验、发布不可变版本、版本列表、详情和差异比较。
- 支持从历史已发布版本回滚；回滚会创建新的发布版本，不修改历史版本。
- 支持停用生成类型，并记录保存草稿、发布、回滚和停用审计日志。
- 参数配置校验覆盖必填、键重复、参数类型、下拉选项、默认值范围和输出类型。
- 工作流绑定校验覆盖类型归属、唯一默认工作流和参数映射完整度。
- 批次提交时将当前发布配置版本写入任务；重新生成和修改参数执行继承原任务快照。
- V1 原有生成类型字段、工作流和任务执行接口保持兼容。

## API 清单

- `GET /api/v2/generation-types/{id}/config`
- `GET|PUT /api/v2/generation-types/{id}/config/draft`
- `POST /api/v2/generation-types/{id}/config/validate`
- `POST /api/v2/generation-types/{id}/config/publish`
- `GET /api/v2/generation-types/{id}/config/versions`
- `GET /api/v2/generation-types/{id}/config/versions/{versionId}`
- `GET /api/v2/generation-types/{id}/config/diff`
- `POST /api/v2/generation-types/{id}/config/rollback`
- `POST /api/v2/generation-types/{id}/config/deactivate`

## 自动化验收

| 检查项 | 结果 |
| --- | --- |
| 生成类型配置专项测试 | 4 passed |
| 后端全量回归 | 52 passed |
| 空数据库 Alembic 升级 | `0006 (head)` |
| 迁移表和快照字段检查 | 通过 |

## V1 影响与回退

- V1 读取和修改 `generation_types.param_template` 的行为不变。
- V2 发布配置存放在独立版本表；没有已发布版本时，V2 读取接口从现有 V1 配置生成兼容视图。
- 回退代码时可执行 `alembic downgrade 0005`；生产执行前应先确认不存在需要保留的 V2 发布配置。
