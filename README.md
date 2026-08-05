# ChatGPT Registration Tool (chatgpt-register-cpa)

基于 grokRegister-cpa 架构的 ChatGPT/OpenAI 半自动注册机。

> 📖 **新手必读**：[完整使用教程 TUTORIAL.md](./TUTORIAL.md)（含半自动操作步骤、法律边界）
> ⚠️ **法律条款**：[NOTICE.md](./NOTICE.md)

## 功能特性

- **协议模式 (Protocol)**: 纯 HTTP 注册流程（curl_cffi 指纹模拟），无需浏览器
- **浏览器模式 (Browser)**: Playwright 浏览器自动化作为备选
- **多种邮箱**: 支持 DuckMail/Mail.tm、Outlook、Cloudflare Workers 等
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
  "register_mode": "protocol",       // 注册模式: protocol/browser
  "count": 1,                        // 注册数量
  "proxy": "",                       // 代理设置
  "output_dir": "./accounts",        // 输出目录
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
├── browser_register.py    # 浏览器模式
├── email_providers/       # 邮箱提供商模块
│   ├── common.py         # 抽象接口
│   └── duckmail.py       # Mail.tm 实现
└── scripts/
    └── turnstile_mint.py # Turnstile token 获取
```

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

浏览器模式会把本机 Chrome 的 `Cookies`/`Local State`/`Preferences` 复制到临时目录用于会话持久化。
为避免泄露个人账号信息，建议：
- 使用独立浏览器或虚拟机运行
- 或清空 `chrome_profile` 配置项并定期清理临时目录
- 不要在共用/办公电脑上运行浏览器模式

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
