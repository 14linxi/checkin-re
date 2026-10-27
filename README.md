# ZaiZaiCat-Checkin 🐱

自用每日签到脚本,青龙签到脚本

> **⚠️ 免责声明**  
> 本项目中的大量代码由 AI 辅助编写生成，代码规范和格式可能存在不足之处，敬请见谅。  
> 本项目仅供学习交流使用，请勿用于商业用途。使用本项目所造成的一切后果由使用者自行承担。

## 📚 在线文档

项目介绍、部署方法、配置说明、脚本使用指南等内容已迁移至在线文档：
- https://cat-zaizai.github.io/ZaiZaiCat-Checkin-Docs/

## 🤖 在 GitHub Actions 运行

仓库内置工作流 [`.github/workflows/checkin.yml`](.github/workflows/checkin.yml)，每天自动运行以下四个脚本：

> 完整配置步骤（平台 Secrets、WxPusher、WorkBuddy 令牌回写、故障排查）见 [docs/github-actions-setup.md](docs/github-actions-setup.md)。

| 平台 | 脚本 |
|------|------|
| 📝 WPS Office | `script/wps/main.py` |
| 🚀 Agent Router | `script/agentrouter/main.py` |
| 🐅 Trae CN | `script/trae/main.py` |
| 🤖 WorkBuddy | `script/workbuddy/main.py` |

### 1. 配置 Secrets（每个平台单独维护）

在仓库 `Settings > Secrets and variables > Actions` 中添加：

| Secret | 必填 | 说明 |
|--------|------|------|
| `WPS_JSON` | 按需 | WPS 平台节点，即 `{"accounts": [...]}` |
| `AGENTROUTER_JSON` | 按需 | Agent Router 平台节点 |
| `TRAE_JSON` | 按需 | Trae CN 平台节点 |
| `WORKBUDDY_JSON` | 按需 | WorkBuddy 平台节点 |
| `GH_SECRETS_PAT` | 建议 | 用于自动回写轮换后的 WorkBuddy 令牌，见下文 |
| `WXPUSHER_SPT` | 可选 | WxPusher 极简推送 SPT（长消息会截断到 `WXPUSHER_MAX_CHARS`，默认 1200） |
| `WXPUSHER_APP_TOKEN` + `WXPUSHER_UIDS` / `WXPUSHER_TOPIC_IDS` | 可选 | WxPusher 官方 POST API，支持完整长消息，优先于 SPT |
| `PUSHPLUS_TOKEN` / `BARK_PUSH` / `TG_BOT_TOKEN` 等 | 可选 | `notification.py` 支持的其他通知渠道 |

每个 Secret 只放对应平台的节点，例如 `WPS_JSON`：

```json
{"accounts": [{"account_name": "大号", "user_id": 123456789, "cookies": "COOKIE", "user_agent": "UA"}]}
```

`AGENTROUTER_JSON`：

```json
{"accounts": [{"account_name": "主号", "github_session": "GITHUB_USER_SESSION"}]}
```

`TRAE_JSON`：

```json
{"accounts": [{"account_name": "主号", "session": "X-Cloudide-Session 值"}]}
```

`WORKBUDDY_JSON`：

```json
{"accounts": [{"account_name": "主号", "email": "you@example.com", "access_token": "ACCESS_TOKEN", "refresh_token": "REFRESH_TOKEN", "uid": "UID"}]}
```

也可以继续使用整包 `TOKEN_JSON`（兼容旧配置），平台独立 Secret 的优先级更高。完整字段参考 [`config/template_token.json`](config/template_token.json)。

### 2. 触发方式

- **定时**：每天北京时间 **06:37** 执行（UTC `37 22 * * *`），避开整点和 UTC 00:00 的调度高峰
- **手动**：`Actions > Daily Check-in > Run workflow`，面板中可勾选要运行的一个或多个平台；定时任务默认全部运行，手动触发时全不勾选会直接报错

批量入口为 [`run_all.py`](run_all.py)，仅调度已配置账号的平台，未配置的会自动跳过。

### 3. 统一推送

各平台脚本的推送会被写入缓冲区，**全部执行完后合并成一条消息**发送，不会每个平台单独推送。进程崩溃时会附带退出码说明，原始日志仍保留在 Actions 页面。

合并时默认启用压缩：去掉各平台重复的「总账号数/签到成功」统计头、`剩余次数: 0`、冗长的账户信息，以及“次数已用完”这类无意义的抽奖失败行。WPS 的「任务中心/天天领福利」只显示成功或失败状态，失败时保留原因。需要完整原文时可设置仓库变量 `CHECKIN_NOTIFY_COMPACT=false`。

消息长度默认限制 4000 字符，可通过仓库变量 `CHECKIN_SUMMARY_MAX_CHARS` 调整（设为 `0` 不限制）；单平台超时默认 1800 秒，可通过 `CHECKIN_TASK_TIMEOUT` 调整。

### 4. WorkBuddy 令牌自动回写

weread-bot 每次运行只刷新 `wr_skey`，长期凭据是 `WEREAD_CURL_STRING` 里的 Cookie，因此不需要回写。WorkBuddy 不同：`refresh_token` 刷新时会**轮换并使旧值失效**，GitHub Actions 的临时文件无法保留新值。

推荐配置 `GH_SECRETS_PAT` 解决：

1. 创建一个只授权当前仓库的 PAT：fine-grained 勾选 **Secrets: Read and write**（含 Metadata: Read），或 classic PAT 勾选 `repo` 权限
2. 存入仓库 Secret `GH_SECRETS_PAT`
3. 工作流在运行结束后（即使失败）会对比 `config/token.json` 中的 WorkBuddy 节点与 Secret，有变化就调用 `gh secret set` 自动更新 `WORKBUDDY_JSON`

未配置 PAT 时，脚本仍会正常签到；一旦 WorkBuddy 轮换了令牌，日志会提示你手动更新 `WORKBUDDY_JSON`。access_token 有效期 60 天，refresh_token 每次刷新后重新计 90 天，只要 90 天内成功运行过一次即可持续续期。

### 5. 注意事项

- Trae CN 多账号建议使用 `session` 模式；桌面 `access_token` 模式绑定本机设备，Actions 环境无法获取。
- 工作流默认关闭 `TRAE_JITTER_MAX` / `WORKBUDDY_JITTER_MAX` 的随机启动延迟。
- 定时任务可能因 GitHub 队列延迟数分钟；公开仓库连续 60 天无活动时，schedule 会被自动禁用。

## ✅ 脚本可用性状态

以下是各平台脚本的当前可用性状态：

| 平台           | 脚本路径 | 状态 | 说明                  |
|--------------|---------|------|---------------------|
| 🚚 顺丰速运      | `script/sf/main.py` | ✅ 可用 | 支持签到和积分任务           |
| 📱 恩山论坛      | `script/enshan/sign_in.py` | ✅ 可用 | 支持每日签到              |
| 🔐 看雪论坛      | `script/kanxue/sign_in.py` | ✅ 可用 | 支持每日签到              |
| 📺 上海杨浦      | `script/shyp/main.py` | ✅ 可用 | 支持任务列表和积分任务         |
| 🏢 华润通-万象星   | `script/huaruntong/999/main.py` | ✅ 可用 | 支持答题签到              |
| 💳 华润通-微信版   | `script/huaruntong/huaruntong_wx/main.py` | ✅ 可用 | 支持签到送积分             |
| 🛒 华润通-Ole'  | `script/huaruntong/ole/main.py` | ❌ 不可用 | 需要动态获取微信code换取token |
| 🎯 华润通-文体未来荟 | `script/huaruntong/wentiweilaihui/main.py` | ✅ 可用 | 支持签到和积分查询           |
| 👟 鸿星尔克      | `script/erke/main.py` | ✅ 可用 | 支持签到和积分明细查询         |
| 📝 WPS Office  | `script/wps/main.py` | ✅ 可用 | 支持任务中心和天天领福利双页面任务 |
| 💰 什么值得买      | `script/smzdm/sign_daily_task/main.py` | ✅ 可用 | 支持每日签到和众测任务         |
| 🤖 WorkBuddy    | `script/workbuddy/main.py` | ✅ 可用 | 支持每日签到、令牌自动续期与多账号管理 |
| 🐅 Trae CN       | `script/trae/main.py` | ✅ 可用 | 支持积分计费模式每日签到与多账号管理 |
| 🚀 Agent Router  | `script/agentrouter/main.py` | ✅ 可用 | 支持 OAuth 登录即签到、余额查询 |

### 状态说明

- ✅ **可用**: 脚本完整且功能正常，可以直接使用
- ⚠️ **部分可用**: 脚本基本可用，但可能存在某些功能限制
- 🚧 **开发中**: 脚本正在开发或测试阶段
- ❌ **不可用**: 脚本存在问题或已废弃

### 使用建议

1. **推荐使用**: 所有标记为"✅ 可用"的脚本都已经过测试，可以放心使用
2. **配置要求**: 使用前请确保在 `config/token.json` 中正确配置了相应平台的账号信息
3. **Cookie 有效期**: 建议定期更新 Cookie 等认证信息，以保证脚本正常运行
4. **测试建议**: 使用青龙命令拉取脚本可能会出现混乱的问题,建议直接clone整个项目到青龙的 scripts 目录下

## 📝 WPS 功能说明

WPS 脚本目前包含两个活动页面：

- `script/wps/task_center.py`：任务中心，支持签到、积分查询、抽奖
- `script/wps/daily_benefits.py`：天天领福利，支持打卡免费领会员、会员免费试用、天天抽奖
- `script/wps/main.py`：WPS 统一入口，按账号顺序依次执行上述两个页面任务

## 📝 WorkBuddy 功能说明

WorkBuddy（CodeBuddy）每日签到脚本，接口实现参考 [cockpit-tools](https://github.com/jlcodes99/cockpit-tools) 项目，与官方客户端行为保持一致：

- `script/workbuddy/api.py`：接口封装，签到状态查询（双端点回退）、每日签到、令牌刷新
- `script/workbuddy/import_accounts.py`：账号导入工具，一键导入官方 WorkBuddy 客户端当前登录账号（自动解密凭据库），也支持从 cockpit-tools 批量导入或指定 JSON 文件导入
- `script/workbuddy/main.py`：统一入口，多账号签到编排、令牌自动续期与结果推送

支持每日签到、连签奖励、多账号管理、令牌自动续期（access_token 60 天 / refresh_token 90 天，自动轮换续期）。详见 [script/workbuddy/README.md](script/workbuddy/README.md)。

## 📝 更新日志

### 2026-09-12
- ✨ 新增 Trae CN、Agent Router 自动签到模块，详见各脚本子目录 README
- 🧹 精简账号配置并移除签到前自动同步逻辑，详见 `script/trae/README.md`、`script/workbuddy/README.md`

### 2026-09-06
- ✨ **新增 WorkBuddy(CodeBuddy) 自动签到模块**:
  - 📅 支持每日自动签到与连签奖励
  - 🔄 支持令牌过期自动刷新并回写配置
  - 📥 支持从官方 WorkBuddy 客户端一键导入账号（自动解密凭据库），也支持从 cockpit-tools 批量导入
  - ⏱️ 内置启动随机延迟与账号间随机间隔，自动错峰
  - 📊 签到结果通过统一推送模块通知

### 2026-03-11
- ✨ **WPS脚本升级为多页面任务**:
  - 🧩 新增 `任务中心` 独立页面脚本
  - 🎁 新增 `天天领福利` 页面脚本
  - 📅 支持 `打卡免费领会员`
  - 🪪 支持 `会员免费试用`
  - 🎰 支持 `天天抽奖`
  - 🔄 `script/wps/main.py` 统一执行两个页面任务

### 2025-12-18 
- ✨ **WPS脚本新增抽奖相关任务**:
  - 🎟️ 支持自动参与每日抽奖
  - 🎁 支持自动领取抽奖奖励
  - 📝 更新 WPS 脚本说明文档，加入抽奖功能使用说明

### 2025-12-08 v2.0
- ✨ **新增什么值得买(SMZDM)任务模块**: 完整的自动化任务执行系统
  - 📅 **每日签到**: 自动完成每日签到，获取积分奖励
  - 🎯 **众测任务**: 自动执行众测相关任务
    - 浏览文章任务自动完成
    - 互动任务自动处理
    - 智能任务奖励领取
  - 🎯 **互动任务**: 全面的用户互动任务支持
    - 自动浏览指定文章
    - 智能关注用户任务
    - 自动领取任务奖励
  - 👥 **多账号管理**: 支持配置多个账号并行执行
  - 📊 **详细统计**: 完整的任务执行统计和结果汇总
  - 📝 **完善日志**: 详细的执行日志记录和错误追踪

### 2025-12-08
- ✨ 支持多平台统一推送：在 `notification.py` 中新增 多平台推送 支持，并将各平台推送整合到统一接口 `send_notification`。
- 🛠 新增推送配置文件：`config/notification.json`（支持从文件或环境变量加载配置，优先级：文件 > 环境 > 默认）。
- 📝 更新 `README.md` 的“通知推送”文档，加入 使用说明、配置示例和常用环境变量说明。

### 2025-12-01
- ✨ 新增 WPS Office 自动签到脚本
- 📝 更新项目说明文档

### 2025-11-28
- ✨ 新增鸿星尔克签到脚本
- ✨ 支持鸿星尔克积分明细查询功能
- ❌ Ole'精品超市脚本设为不可用（需要动态获取微信code换取token）
- 📝 更新项目说明文档

### 2025-11-24
- ✨ 新增顺丰速运签到脚本
- ✨ 新增恩山论坛签到脚本
- ✨ 新增看雪论坛签到脚本
- ✨ 新增上海杨浦任务脚本
- ✨ 新增华润通多个子平台支持
- ✨ ✨ 999 签到功能完善
- ✨ ✨ 华润通微信小程序签到功能完善
- ✨ ✨ Ole' 精品超市签到功能（已废弃）
- ✨ ✨ 文体未来荟签到功能完善
- ✨ 创建项目 README 文档
- 📝 完善项目说明和使用指南

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## ⚠️ 注意事项

1. 本项目仅供学习交流使用，请勿用于商业用途
2. 使用本项目所造成的一切后果由使用者自行承担
3. 请合理使用自动签到功能，避免对平台造成负担
4. Cookie 等敏感信息请妥善保管，不要泄露给他人
5. 定期更新 Cookie，避免失效影响使用
6. 代码由 AI 辅助生成，可能存在不规范之处

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

- 感谢所有为本项目提供帮助和支持的朋友
- 感谢青龙面板提供的自动化平台

## 📧 联系方式

如有问题或建议，欢迎通过以下方式联系：

- GitHub Issues: [提交问题](https://github.com/Cat-zaizai/ZaiZaiCat-Checkin/issues)
- Email: wusan503@gmail.com

---

**⭐ 如果这个项目对你有帮助，欢迎给个 Star！**
