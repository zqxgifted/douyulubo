# 贡献指南

欢迎提 Issue / PR。几点约定：

## 开发前

1. 复制 `examples/config.example.json` 为 `config.json` 并填本地值；**不要提交 `config.json`**
2. Python：`pip install -r requirements.txt`；Node：18+（无需 npm 依赖）
3. 改动后用真实但**非敏感**的主播 ID 做一次最小流程验证（step1 → step2 → 单场下载）

## 约定

- 所有脚本统一通过 `src/config.py` / `src/config.mjs` 读配置；**不要在源码里写死**
  `up_id`、设备号、本机绝对路径、主播昵称或任何会话 / 网盘私有路径
- 新增公开接口逻辑放 `src/douyu.mjs`，不要在每个脚本里复制签名 / 取流代码
- **不要直接粘贴第三方源码**。若参考了别人的实现，在源码注释里写明来源，并同步更新
  [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) / `NOTICE`；同时确认上游许可证与 MIT 是否兼容
  （GPL/AGPL 系代码不能并入本仓库）
- 脚本输出目录固定为 `<work_dir>/data|downloads|danmaku|danmaku_ass|tmp`
- 提交信息用 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:`）
- 文档用中文，代码注释可中可英，保持一致

## 提交前自检

```bash
# 确认没有误提交敏感项
git status
git diff --cached
```

重点检查：本机绝对路径、Windows 用户目录、真实主播 ID / 昵称 / 房间号、
固定设备号、会话记录路径、网盘私有目录。若命中，说明源码里混入了实例数据，必须先清理。

> 建议把这类特征维护成本仓库自己的自查清单，不要直接照抄任何真实值。

## 接口变更

斗鱼的播放页结构与签名函数会轮换。若 `loadSigner()` / `extract()` 失效，
请优先在 [docs/API.md](docs/API.md) 记录新的页面结构，再改代码，并在 PR 里说明实测日期。
