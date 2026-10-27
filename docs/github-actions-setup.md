# GitHub Actions 配置指南

本文档说明如何把本项目部署到 GitHub Actions，只运行以下四个平台：

- WPS Office
- Agent Router
- Trae CN
- WorkBuddy

工作流文件：[`.github/workflows/checkin.yml`](../.github/workflows/checkin.yml)
批量入口：[`run_all.py`](../run_all.py)

---

## 1. 工作流做了什么

```text
GitHub Actions（每天 06:37 或手动触发）
        ↓
run_all.py
        ├─ WPS        script/wps/main.py
        ├─ Agent Router script/agentrouter/main.py
        ├─ Trae CN    script/trae/main.py
        └─ WorkBuddy  script/workbuddy/main.py
        ↓
合并所有平台结果，统一发送一条通知
```

特点：

- 每个平台单独配置 Secret，某个平台换 Cookie 不影响其他平台
- 未配置账号的平台自动跳过
- 子任务不单独推送，全部跑完后合并为一条消息
- 默认压缩通知内容，去掉重复统计和零值信息
- 某个脚本进程异常时，Actions 任务会标记失败，并补发异常汇总

---

## 2. 前置条件

1. 仓库已启用 Actions（公开仓库默认启用）
2. 你对仓库有 `Secrets` 和 `Actions` 的写入权限
3. 工作流文件已合并到默认分支（`schedule` 只在默认分支生效）

所有敏感信息都放在：

```text
仓库 → Settings → Secrets and variables → Actions → Secrets 标签页
```

不要放在 `Variables` 标签页，`Variables` 只用于非敏感参数。

---

## 3. 配置平台 Secrets

四个平台的 Secret 都是**平台节点 JSON**，不是整包 `token.json`。

| Secret | 内容 |
|---|---|
| `WPS_JSON` | WPS 平台节点 |
| `AGENTROUTER_JSON` | Agent Router 平台节点 |
| `TRAE_JSON` | Trae CN 平台节点 |
| `WORKBUDDY_JSON` | WorkBuddy 平台节点 |

只配置你实际使用的平台即可，至少配置一个。

### 3.1 WPS_JSON

```json
{
  "accounts": [
    {
      "account_name": "大号",
      "user_id": 123456789,
      "cookies": "你的 WPS Cookie",
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 建议 | 通知中显示的账号名 |
| `user_id` | 是 | WPS 用户 ID |
| `cookies` | 是 | 登录后的 Cookie |
| `user_agent` | 建议 | 与获取 Cookie 时一致的 UA |

多账号在 `accounts` 数组中继续追加对象。

### 3.2 AGENTROUTER_JSON

```json
{
  "accounts": [
    {
      "account_name": "主号",
      "github_session": "GitHub 登录后的 user_session"
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 建议 | 通知中显示的账号名 |
| `github_session` | 是 | GitHub 登录态 `user_session` |
| `base_url` | 否 | 默认 `https://ps.air-outer.com` |

### 3.3 TRAE_JSON

推荐使用长效 `sessionid`，Actions 中不需要本机客户端设备：

```json
{
  "accounts": [
    {
      "account_name": "主号",
      "sessionid": "浏览器 Cookie 中的 sessionid"
    }
  ]
}
```

也可以直接填 `session`（X-Cloudide-Session）：

```json
{
  "accounts": [
    {
      "account_name": "主号",
      "session": "X-Cloudide-Session 的值"
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 建议 | 通知中显示的账号名 |
| `sessionid` | 推荐 | 长效登录 Cookie，脚本会先刷新出 `session` |
| `session` | 可选 | 网页会话 JWT，不绑定设备 |
| `access_token` | 可选 | 桌面令牌模式，需要本机已注册设备，Actions 不推荐 |
| `device_id` | 可选 | 桌面令牌模式下的签到设备 ID |

多账号建议使用 `sessionid` 或 `session`，否则可能提示设备缺失。

### 3.4 WORKBUDDY_JSON

```json
{
  "accounts": [
    {
      "account_name": "主号",
      "email": "you@example.com",
      "access_token": "你的 access_token",
      "refresh_token": "你的 refresh_token",
      "uid": "你的用户 ID",
      "enterprise_id": "",
      "domain": ""
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 建议 | 通知中显示的账号名 |
| `email` | 建议 | 用于区分账号 |
| `access_token` | 是 | 访问令牌 |
| `refresh_token` | 强烈建议 | 令牌过期时续期 |
| `uid` | 建议 | 请求头 `X-User-Id` |
| `enterprise_id` | 否 | 企业 ID，个人账号留空 |
| `domain` | 否 | 一般留空 |

`refresh_token` 会在刷新时轮换，Actions 中的持久化配置见第 5 节。

### 3.5 兼容旧配置

如果已有整包 `TOKEN_JSON`，仍可继续使用：

```json
{
  "wps": { "accounts": [] },
  "agentrouter": { "accounts": [] },
  "trae": { "accounts": [] },
  "workbuddy": { "accounts": [] }
}
```

优先级：

```text
平台独立 Secret > TOKEN_JSON > 本地 config/token.json
```

平台独立 Secret 会覆盖整包配置中的同名平台。

---

## 4. 配置通知

目前支持 WxPusher 以及 `notification.py` 中的其他渠道。

### 4.1 WxPusher SPT（简单）

最少只需要一个 Secret：

| Secret | 说明 |
|---|---|
| `WXPUSHER_SPT` | WxPusher 极简推送 SPT |

SPT 模式把消息放在 GET URL 中，内容过长会被截断。默认上限 1200 字符，可通过仓库变量 `WXPUSHER_MAX_CHARS` 调整。

### 4.2 WxPusher POST（推荐长消息）

如果需要完整保留多账号明细，配置：

| Secret | 说明 |
|---|---|
| `WXPUSHER_APP_TOKEN` | WxPusher 应用 appToken |
| `WXPUSHER_UIDS` | 接收用户 UID，多个用逗号分隔 |
| `WXPUSHER_TOPIC_IDS` | 接收主题 ID，多个用逗号分隔 |

配置了 `app_token` 且至少有一个 UID 或 Topic 时，会优先调用官方 POST API，不受 URL 长度限制。

### 4.3 其他通知渠道

以下 Secret 与 `notification.py` 原有环境变量一致，按需配置：

| 渠道 | Secret |
|---|---|
| Bark | `BARK_PUSH`、`BARK_ICON`、`BARK_SOUND`、`BARK_GROUP`、`BARK_LEVEL`、`BARK_URL` |
| Server酱 | `SCKEY` 或 `SENDKEY` |
| PushPlus | `PUSHPLUS_TOKEN`、`PUSHPLUS_TOPIC` |
| Telegram | `TG_BOT_TOKEN`、`TG_USER_ID`、`TG_API_HOST`、`TG_PROXY` |
| 飞书 | `FSKEY` |
| 钉钉 | `DINGTALK_ACCESS_TOKEN`、`DINGTALK_SECRET` |
| 企业微信机器人 | `QYWX_KEY` |
| 企业微信应用 | `QYWX_CORPID`、`QYWX_AGENTID`、`QYWX_CORPSECRET`、`QYWX_TOUSER` |
| PushDeer | `PUSHDEER_PUSHKEY` |
| Gotify | `GOTIFY_URL`、`GOTIFY_TOKEN` |
| Ntfy | `NTFY_URL`、`NTFY_TOPIC` |

### 4.4 通知内容压缩

统一汇总默认启用压缩：

- 删除重复的「总账号数 / 签到成功 / 今日已签」统计头
- 删除 `剩余次数: 0` 和冗长的账户信息
- 删除「今日次数已用完」这类无意义抽奖失败
- WPS 的「任务中心 / 天天领福利」只显示成功或失败，失败时保留原因

如需完整原文，设置仓库变量：

```text
CHECKIN_NOTIFY_COMPACT = false
```

---

## 5. WorkBuddy 令牌自动回写

### 5.1 为什么需要回写

weread-bot 每次运行只刷新 `wr_skey`，长期凭据是 `WEREAD_CURL_STRING` 中的 Cookie，所以不需要回写。

WorkBuddy 不同：

- `access_token` 有效期约 60 天
- `refresh_token` 有效期约 90 天
- 刷新时 `refresh_token` 会轮换，旧值失效

GitHub Actions 的临时文件不会跨运行保留，因此轮换后的令牌必须写回 Secret，否则下一次运行会失效。

### 5.2 配置 GH_SECRETS_PAT

1. 创建一个只授权当前仓库的 PAT
   - fine-grained：勾选 **Secrets: Read and write**（含 Metadata: Read）
   - 或 classic PAT：勾选 `repo`
2. 保存为仓库 Secret：`GH_SECRETS_PAT`
3. 工作流在运行结束后（即使失败）会：
   - 对比 `config/token.json` 中的 WorkBuddy 节点和 `WORKBUDDY_JSON`
   - 有变化时调用 `gh secret set` 自动更新 `WORKBUDDY_JSON`

### 5.3 不配置 PAT 时

签到仍能正常运行，但 WorkBuddy 轮换令牌后需要手动更新 `WORKBUDDY_JSON`。日志会提示令牌已刷新。

如果不想使用 PAT，也可以改用自托管 runner 或青龙面板持久化配置。

---

## 6. 可选仓库变量

这些值放在：

```text
Settings → Secrets and variables → Actions → Variables 标签页
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CHECKIN_SUMMARY_MAX_CHARS` | `4000` | 统一汇总最大字符数，`0` 表示不限制 |
| `CHECKIN_TASK_TIMEOUT` | `1800` | 单个平台超时时间（秒） |
| `CHECKIN_NOTIFY_COMPACT` | `true` | 设为 `false` 输出完整原文 |
| `WXPUSHER_MAX_CHARS` | `1200` | SPT 模式下的内容上限 |

---

## 7. 运行

### 7.1 手动触发

```text
Actions → Daily Check-in → Run workflow
```

面板中会显示四个勾选框：

- WPS Office
- Agent Router
- Trae CN
- WorkBuddy

默认全部勾选。手动触发时如果全部取消，会直接报错。

### 7.2 定时触发

```text
每天北京时间 06:37（UTC 37 22 * * *）
```

说明：

- GitHub 使用 UTC
- 已避开整点和 UTC 00:00 的调度高峰
- GitHub 仍可能延迟数分钟
- 公开仓库连续 60 天无活动时，schedule 可能被自动禁用

### 7.3 查看结果

- 在 Actions 运行页面查看每个平台的完整日志
- 通知中只包含汇总和关键结果
- 某个脚本进程失败时，任务会标红并退出码非 0

---

## 8. 本地运行

```bash
cp config/template_token.json config/token.json
# 编辑 config/token.json，填入账号信息

pip install -r requirements.txt
python run_all.py --platforms all
```

常用命令：

```bash
python run_all.py --list
python run_all.py --platforms wps,trae
python run_all.py --platforms workbuddy
```

本地通知配置：

```bash
cp config/template_notification.json config/notification.json
# 编辑 config/notification.json
```

`config/token.json` 和 `config/notification.json` 已被 `.gitignore` 忽略，不要提交。

---

## 9. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `未配置任何平台 Secret` | 四个平台 Secret 都为空 | 至少添加一个平台 Secret |
| `没有找到已配置账号的平台` | Secret JSON 中没有 `accounts` 或数组为空 | 检查 JSON 结构和账号字段 |
| `WPS_JSON 不是合法 JSON` | Secret 内容格式错误 | 用 JSON 校验工具检查，注意不要带多余逗号 |
| WorkBuddy 返回 401 | access_token 过期或 refresh_token 已轮换 | 配置 `GH_SECRETS_PAT` 自动回写，或手动更新 `WORKBUDDY_JSON` |
| Trae 提示设备缺失 | 使用了桌面 `access_token` 模式 | 改用 `sessionid` 或 `session` |
| 通知内容被截断 | SPT 模式 URL 长度限制 | 提高 `WXPUSHER_MAX_CHARS`，或改用 `WXPUSHER_APP_TOKEN` POST |
| 定时任务没有运行 | 工作流不在默认分支，或 60 天无活动被禁用 | 合并到默认分支，或手动触发一次保活 |
| 国内平台签到异常 | GitHub 境外 IP 风控 | 观察日志；必要时使用自托管 runner 或配置代理 |

---

## 10. 安全注意事项

1. 不要把 `config/token.json`、`config/notification.json` 提交到仓库
2. `WPS_JSON`、`TRAE_JSON` 等 Secret 只放在 GitHub Secrets
3. `GH_SECRETS_PAT` 只授权当前仓库，权限最小化
4. Actions 日志可能显示账号名，但不会主动打印令牌
5. 一旦怀疑令牌泄露，立即重新登录对应平台并更新 Secret
6. 不要在不信任的分支上运行带 `GH_SECRETS_PAT` 的工作流
