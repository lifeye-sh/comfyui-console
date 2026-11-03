# Console 角色图库子项目

前端源自 anhao/ai-pose-gallery-zh 的 4464f7638826f57ed654430a3a7df57f88b2c03c。保留上游 LICENSE。图库数据、缩略图及原图使用独立素材卷，遵循来源授权。

在 Console 的父目录首次准备素材：

```sh
git clone https://github.com/anhao/ai-pose-gallery-zh.git ai-pose-gallery-zh
git -C ai-pose-gallery-zh checkout 4464f7638826f57ed654430a3a7df57f88b2c03c
```

已有素材包时可将 POSE_GALLERY_ASSETS 指向其根目录。Console 项目中运行 docker compose build、docker compose run --rm --no-deps backend alembic upgrade head、docker compose up -d。访问 /gallery/，后台使用 /v2/settings/gallery 发布工作流版本和图片槽位映射。选用额外参考图时需要配置 extras。可以选择将三个主要参考合成一张图传给 composite 参数。

合成任务沿用已选工作流的 Console 生成类型。批次来源为 gallery，global_params 保存配方与映射快照。请求 ID 按用户去重。离开图库后任务由后台继续执行。

「人像 + 服装 + 姿势」「人像 + 服装」「人像 + 姿势」分别在 Console 的图库工作流配置页发布。原有三图配置继续使用。双图模式应绑定对应的两个参考槽，或绑定拼图输入。用户可在各槽位从角色图库、Console 素材库或本地文件选图；选择 Console 已有图片时，独立输入槽直接使用其资源 ID。
