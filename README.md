# ChatGPT Registration Tool (chatgpt-register-cpa)

基于 grokRegister-cpa 架构的 ChatGPT/OpenAI 自动注册机（支持全自动与半自动）。

> 📖 **新手必读**：[完整使用教程 TUTORIAL.md](./TUTORIAL.md)（含半自动操作步骤、法律边界）
> ⚠️ **法律条款**：[NOTICE.md](./NOTICE.md)

## 功能特性

- **全自动注册**: 浏览器模式 OTP 后自动完成「继续 → 姓名/生日/年龄 → 服务条款 → 欢迎页」，无需人工介入
- **自动补号 (Auto-refill)**: `auto_register_agent.py` 轮询 gpt2api 号池，低于阈值自动注册补齐并上传
- **协议模式 (Protocol)**: 纯 HTTP 注册流程（curl_cffi 指纹模拟），无需浏览器
- **浏览器模式 (Browser)**: Playwright 自动化（有头/无头皆可），自动探测系统 Chrome，无则回退内置 Chromium
- **服务器部署**: tkinter 可选导入 + `--no-sandbox`，可在无桌面 Linux 服务器用 xvfb 运行
- **多种邮箱**: 支持 DuckMail/Mail.tm、Outlook、Cloudflare Workers（含随机子域名）等
- **GUI/CLI**: 图形界面和命令行双模式
- **Token 提取**: 自动提取 access_token, refresh_token 等
- **结果导出**: 保存为 JSON 和 accounts.txt 格式
- **CPA 上传**: 注册结果自动上传到自建 gpt2api 服务器

## 安装

```bash
# 克隆仓库
git clone <your-repo>
cd chatgpt-register-cpa

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器 (用于 Turnstile)
playwright install chromium
```

## 配置

复制配置文件并编辑：

```bash
cp config.example.json config.json
```

主要配置项：

```json
{
  "email_provider": "duckmail",      // 邮箱提供商
  "register_mode": "browser",        // 注册模式: protocol/browser
  "count": 1,                        // 注册数量
  "proxy": "",                       // 代理设置 (如 http://127.0.0.1:10808)
  "headless": false,                 // 浏览器是否无头运行 (服务器配合 xvfb 使用)
  "chrome_profile": "",              // Chrome profile 路径，留空用临时 profile
  "output_dir": "./accounts",        // 输出目录
  "cpa_remote_url": "",              // gpt2api 地址 (自动上传时填写)
  "cpa_management_key": "",          // gpt2api 管理密钥
  "timeout": 120,                    // 超时时间
  "delay_between": [5, 15]          // 注册间隔
}
```

## 使用

### GUI 模式

```bash
python chatgpt_register_ttk.py
# 或
python chatgpt_register_ttk.py gui
```

### CLI 模式

```bash
# 注册指定数量
python chatgpt_register_ttk.py cli --count 5

# 注册单个并退出
python chatgpt_register_ttk.py cli --once

# 使用代理
python chatgpt_register_ttk.py cli --once --config config.json
```

### 无桌面服务器 (headless 环境)

无头服务器上 tkinter 不可用，走 CLI 模式；配合 `xvfb` 以「有头模式」运行真实 Chrome（比无头更容易绕过 Cloudflare 拦截）：

```bash
# 安装 xvfb + Chrome
apt install -y xvfb google-chrome-stable

# 用 xvfb 跑有头模式注册（config.json 中 headless=false, proxy=代理）
xvfb-run -a python chatgpt_register_ttk.py cli --count 5
```

> 注意：`headless: true` 的纯无头模式（包括真 Chrome 无头）会被 Cloudflare "Just a moment" 拦截导致收不到验证码，推荐 xvfb + 有头模式。

### 自动补号 (Auto-refill agent)

配合 gpt2api 的 `/api/auto_register/status` 接口，自动检测号池并在低于阈值时补号：

```bash
# 前台运行
python auto_register_agent.py

# 单次检查（配合 crontab/systemd 使用）
python auto_register_agent.py --once

# systemd 常驻示例 /etc/systemd/system/auto-register-agent.service
[Unit]
Description=Auto Register Agent
After=network-online.target

[Service]
Type=simple
ExecStart=/path/to/venv/bin/python /path/to/auto_register_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

配置 `auto_register_agent.json`：

```json
{ "interval_sec": 300 }   // 轮询间隔（秒）
```

agent 从 `config.json` 读取 `cpa_remote_url` 和 `cpa_management_key`（Bearer 认证）请求状态接口；当返回 `enabled=true && need_refill=true` 时自动运行 `cli --count N` 注册并把结果上传回号池。

## 邮箱提供商

### DuckMail / Mail.tm (默认)

无需配置，开箱即用。使用 mail.tm API 创建临时邮箱。

### 其他提供商

在 config.json 中配置：

```json
{
  "email_config": {
    "cloudflare_temp": {
      "api_base": "https://your-worker.pages.dev",
      "api_key": "your-token"
    },
    "cloudflare": {
      "worker_url": "https://your-worker.workers.dev",
      "admin_token": "your-token",
      "domain": "your-domain.com"
    },
    "outlook": {
      "email": "your-account@outlook.com",
      "app_password": "your-app-password"
    }
  }
}
```

> 注意：`yyds` 提供商为实验性占位实现，目前无法接收验证码，请勿在生产环境使用。

## 输出格式

注册成功后在 `output_dir` 目录生成：

1. `accounts.txt`: `email----password` 格式
2. `chatgpt_email_at_domain.json`: 完整注册信息

```json
{
  "email": "user@example.com",
  "password": "generated-password",
  "type": "chatgpt",
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "registered_at": "2026-01-01T12:00:00"
}
```

## 技术架构

```
chatgpt_register_ttk.py    # 主入口 (GUI/CLI)
├── protocol/
│   ├── gpt_register.py    # 协议注册核心 (GPTRegistrar)
│   ├── sentinel.py        # Sentinel token 生成
│   ├── pkce.py            # PKCE 工具
│   └── turnstile.py       # Turnstile token 获取
├── browser_register.py    # 浏览器模式 (含全自动注册流程)
├── auto_register_agent.py # 自动补号 agent (轮询 gpt2api 号池)
├── email_providers/       # 邮箱提供商模块
│   ├── common.py         # 抽象接口
│   └── duckmail.py       # Mail.tm 实现
└── scripts/
    └── turnstile_mint.py # Turnstile token 获取
```

### 浏览器模式全自动流程

`browser_register.py` 的 `_auto_complete_signup` 在 OTP 填入后自动处理：

1. 点击 OTP 页面的 Continue/提交
2. `_detect_profile_fields` 探测姓名/生日/年龄字段
3. `_fill_birthdate` 随机生成生日 (1995-2004)，`_fill` 姓名
4. `_accept_terms` 勾选服务条款并提交
5. 轮询等待注册完成；若进入欢迎页由 `_click_welcome_continue` 自动点掉

全部步骤自动完成，无需人工点击；失败时降级为提示手动操作。

## OpenAI 注册流程

协议模式实现流程：

1. **OAuth 初始化**: PKCE 流程启动
2. **Sentinel Token**: 获取反机器人令牌
3. **邮箱提交**: 提交邮箱地址
4. **OTP 发送**: 请求验证码
5. **OTP 验证**: 验证邮箱所有权
6. **账户创建**: 注册账户
7. **档案完善**: 完成资料设置
8. **Token 交换**: 获取访问令牌

关键端点：
- `auth.openai.com/api/accounts/authorize`
- `auth.openai.com/api/accounts/email-otp/*`
- `sentinel.openai.com/backend-api/sentinel/req`

## 注意事项

⚠️ **浏览器模式隐私提醒**

浏览器模式默认使用**全新临时 profile**（`chrome_profile` 留空时），不触碰本机 Chrome 数据。
若配置了 `chrome_profile`，会把该 profile 的 `Cookies`/`Local State`/`Preferences` 复制到临时目录用于会话持久化。
为避免泄露个人账号信息，建议：
- 保持 `chrome_profile` 为空（每次全新 profile）
- 或使用独立浏览器/虚拟机运行
- 不要在共用/办公电脑上配置个人 profile 运行浏览器模式

⚠️ **免责声明**

本工具仅用于：
- 自动化流程研究
- 测试环境验证
- 个人学习目的

请遵守：
- OpenAI 服务条款
- 当地法律法规
- 第三方使用限制

使用本工具可能导致：
- 账户被封禁
- IP 被限制
- 其他不可预知后果

风险自负。

## 相关项目

- [linux.do](https://linux.do) - 技术社区致谢
- [grokRegister-cpa](https://github.com/Git-creat7/grokRegister-cpa) - Grok 注册机 (本项目的参考实现)
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) - 多模型 API 代理

## 开发

```bash
# 环境自检
python test_setup.py
```

## License

MIT License - 仅供学习研究使用
