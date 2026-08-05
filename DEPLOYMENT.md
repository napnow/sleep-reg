# Deployment Guide

## Windows 部署

### 1. 环境准备

#### 安装 Python 3.9+
从 [python.org](https://www.python.org/downloads/) 下载并安装 Python 3.9 或更高版本。

确保勾选 "Add Python to PATH"。

#### 安装 Chrome/Chromium
浏览器模式需要 Chrome/Chromium（协议模式为纯 HTTP，不需要）：
- 自动安装：`playwright install chromium`
- 或手动安装 Google Chrome

### 2. 项目设置

```cmd
# 克隆或下载项目
cd chatgpt-register-cpa

# 创建虚拟环境 (推荐)
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装浏览器
playwright install chromium
```

### 3. 配置

```cmd
copy config.example.json config.json
notepad config.json
```

编辑配置，特别是：
- `email_provider`: 选择邮箱提供商
- `register_mode`: protocol 或 browser
- `proxy`: 如需要代理

### 4. 运行

#### GUI 模式
```cmd
start-gui.cmd
# 或
python chatgpt_register_ttk.py
```

#### CLI 模式
```cmd
start-cli.cmd --count 5
# 或
python chatgpt_register_ttk.py cli --count 5
```

## Linux/macOS 部署

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装浏览器
playwright install chromium

# 复制配置
cp config.example.json config.json

# 运行
python chatgpt_register_ttk.py
```

## 依赖说明

### 核心依赖
- `curl-cffi`: TLS 指纹伪装，模拟 Chrome
- `requests`: HTTP 请求
- `playwright`: 浏览器自动化（浏览器模式）

### 可选依赖
- `tkinter`: GUI 界面 (通常随 Python 内置)

## 常见问题

### Q: 提示找不到 Chrome
A: 运行 `playwright install chromium` 或安装 Google Chrome

### Q: 邮箱获取验证码超时
A:
1. 检查网络连接
2. 尝试更换邮箱提供商
3. 增加 `timeout` 配置值
4. 检查代理设置

### Q: 注册失败率高
A:
1. 使用高质量代理
2. 增加注册间隔 (`delay_between`)
3. 尝试 browser 模式而非 protocol
4. 更换邮箱提供商

### Q: GUI 界面无法打开
A:
- 确保有图形界面环境
- Windows: 确保 tkinter 已安装
- Linux: `apt-get install python3-tk`

## 性能优化

### 批量注册
- 使用 protocol 模式 (更快)
- 适当增加 `count` 批量注册
- 设置合理 `delay_between` 间隔

### 资源管理
- 定期清理 accounts/ 目录
- 监控内存使用 (大量并发时)
- 使用代理池分散请求

## 生产环境建议

1. **使用代理**: 始终配置高质量代理
2. **限制并发**: 避免过高并发触发风控
3. **错误处理**: 监控失败率，及时调整策略
4. **日志记录**: 保留详细日志便于排查
5. **定期更新**: OpenAI 可能更改流程，需要更新代码

## 安全提醒

⚠️ 切勿在生产环境或重要账户使用此工具
⚠️ 注册的账户可能随时被封禁
⚠️ 遵守 OpenAI 服务条款和当地法律
