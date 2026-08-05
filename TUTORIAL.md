# Sleep-Reg 使用教程（半自动注册机）

> 本项目是**半自动** ChatGPT 注册工具：邮箱创建、验证码收取自动完成，
> **姓名/年龄填写与"继续"按钮需要你自己手动点击**。请在开始前阅读本教程。

---

## 1. 项目简介

- **模式一：协议模式（Protocol，全自动）**：纯 HTTP 注册，自动填随机姓名/生日，全程无需人工。
- **模式二：浏览器模式（Browser，半自动）**：Playwright 打开 Chrome 窗口，自动填入邮箱和验证码，
  之后的页面（继续按钮、姓名、年龄）需要你**手动完成**，工具轮询检测注册完成后自动提取 token 并保存/上传。

> 为什么是半自动？因为 OpenAI 注册流程包含验证码输入、姓名年龄填写等环节，
> 人工介入可以有效降低被风控拦截的概率。

---

## 2. 环境要求

| 依赖 | 说明 |
|---|---|
| Python 3.9+ | 基础环境 |
| Windows / Linux / macOS | 跨平台 |
| Chrome 浏览器 | 仅浏览器模式需要（`playwright install chromium`） |
| Node.js | 可选，Sentinel VM 用（无 Node 自动降级为纯 Python PoW） |

## 3. 安装

```bash
git clone <你的仓库地址>
cd sleep-reg

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate    # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 浏览器模式需要 Chromium
playwright install chromium

# 复制配置
cp config.example.json config.json
```

## 4. 配置

编辑 `config.json`：

```jsonc
{
  "email_provider": "cloudflare_temp",  // 邮箱提供商: duckmail/mail_tm/outlook/cloudflare_temp
  "email_config": { ... },              // 各提供商的密钥配置
  "register_mode": "browser",           // 注册模式: protocol（全自动） / browser（半自动）
  "count": 1,                           // 注册数量
  "proxy": "http://127.0.0.1:10808",    // 代理（强烈建议配置）
  "chrome_profile": "",                 // 浏览器模式用的 Chrome 配置目录
  "cpa_remote_url": "https://你的gpt2api服务器",   // 留空则不上传
  "cpa_management_key": "你的管理密钥",             // 留空则不上传
  "delay_between": [5, 15]              // 批量注册间隔（秒）
}
```

### 邮箱提供商说明

| 提供商 | 配置 | 说明 |
|---|---|---|
| `duckmail` / `mail_tm` | 无需配置 | 开箱即用 |
| `cloudflare_temp` | `api_base` + `api_key` | 自建 Pages 临时邮箱 |
| `outlook` | `email` + `app_password` | 需要 Outlook 应用密码 |
| `yyds` | 不推荐 | 实验性占位实现，收不到验证码 |

## 5. 使用教程

### 5.1 GUI 方式（推荐新手）

```bash
start-gui.cmd   # 或 python chatgpt_register_ttk.py
```

1. 选择邮箱提供商、注册数量、模式（协议/浏览器）
2. 填入代理（如有）
3. 点击 **Start Registration**
4. 观察日志窗口

### 5.2 CLI 方式

```bash
# 注册 5 个（默认模式）
python chatgpt_register_ttk.py cli --count 5

# 注册 1 个就退出
python chatgpt_register_ttk.py cli --once
```

### 5.3 半自动（浏览器模式）完整步骤 ⭐

这是本工具的典型用法，请按顺序操作：

1. **启动**后，Chrome 窗口会自动打开并跳到 `chatgpt.com/auth/login`
2. **自动**：工具填入临时邮箱地址并回车
3. **自动**：工具收取邮箱验证码并自动填入
4. **⚠️ 手动**：验证码填好后，请你在浏览器里：
   - 点击 **Continue**（继续）按钮
   - 如出现姓名输入框，填入你的姓名（或任意昵称）
   - 如出现生日/年龄选择，选择一个 18+ 的出生日期
   - 继续点击下一步，直到页面显示已登录
5. **自动**：工具检测到登录成功后，自动提取 access_token，保存到 `accounts/` 并（可选）上传到你的 gpt2api 服务器
6. 整个过程有 **300 秒** 限时，超时未完成视为失败

> 如果验证码输入框没有被自动填充（页面结构变化），请手动粘贴验证码后继续。

### 5.4 全自动（协议模式）

无需任何人工操作，自动完成注册。适合批量。首次运行需要 Node.js 或纯 Python PoW 求解，耗时约 10~30 秒/个。

## 6. 输出与上传

注册成功后，在 `output_dir`（默认 `accounts/`）生成：

```
accounts/
├── accounts.txt                # email----password 格式
└── chatgpt_邮箱名.json          # 完整信息（含 access_token）
```

配置了 `cpa_remote_url` + `cpa_management_key` 后，每个注册成功的账号会自动 `POST /api/accounts` 上传到你的 gpt2api 服务器（日志中显示 `CPA upload OK` 即成功）。

## 7. 常见问题（FAQ）

**Q: 浏览器模式点了开始但 Chrome 没弹出来？**
A: 检查 `chrome_profile` 指向的目录是否存在；Windows 下需要 Chrome 已安装。

**Q: 验证码超时收不到？**
A: 检查代理连通性、邮箱提供商配置；`timeout` 默认 120 秒。

**Q: 注册显示成功但 accounts/ 里没有文件？**
A: 检查日志中是否有 `[OK] Successfully registered`；若只有 `[FAIL]` 则未成功。

**Q: 上传失败？**
A: 确认 gpt2api 服务器地址可达、管理密钥正确，日志会显示具体 HTTP 状态码。

**Q: 批量注册被风控？**
A: 建议使用高质量代理池、加大 `delay_between` 间隔、配合人工半自动模式。

---

## 8. 法律边界

> **在使用本项目前，请务必阅读并确认你可以合法使用它。**

### 允许 ✅
- 使用**你自己**的账号和环境进行测试
- 明确授权的安全研究
- CTF、学术协议研究与教学
- 离线阅读本项目源码

### 禁止 ❌
- 欺诈、批量注册转售
- 账号黑产（买卖、养号、恶意囤积）
- 对未授权目标的自动化
- 故意规避或滥用平台服务条款

### 责任 ⚠️
- 账号封禁、额度损失、数据泄露、民事、刑事或行政后果均由**使用者**承担
- 本项目的维护者不对任何使用后果负责

### 关联关系
- 本项目不隶属于 OpenAI / ChatGPT、Microsoft / Outlook、Cloudflare、TempMail / Mail.tm、YYDS Mail、chatgpt2api 上游或其他邮箱、验证码及代理服务商
- 本项目的任何技术实现（Sentinel、Turnstile、NextAuth 流程等）仅为协议研究，不代表任何第三方平台认可或背书

> 完整条款见 [NOTICE.md](./NOTICE.md)。
> 本项目采用 MIT License，但 MIT License 并非完整免责声明。
>
> **如果你无法确定用途是否合法，请不要运行；请先咨询执业律师，或联系目标平台的安全与合规团队。**

---

## 9. 致谢

- [linux.do](https://linux.do) — 技术社区与交流支持

## 10. 相关链接

- 参考实现：[grokRegister-cpa](https://github.com/Git-creat7/grokRegister-cpa)
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) - 多模型 API 代理
