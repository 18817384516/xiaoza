# 开发与验证

主要验证环境：Windows x64，Python3.13、Node.js24、Blender4.5。支持依赖最低Python3.11和Node22.12；其他组合未逐一验证。

## 准备

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm run build
```

Blender可运行 `安装Blender建模.cmd` 安装固定版本，或设置 `XIAOZAO_BLENDER_PATH`。安装脚本下载官方便携包并验证SHA256，不随仓库分发二进制。更换Blender版本应重新验证API和示例。

## 两个开发终端

```powershell
# 后端；避免与已启动的工作台占用同一端口
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765 --reload
```

```powershell
# 前端，使用终端显示的 Vite 地址
npm run dev
```

前端会将 `/api` 代理到本机8765。已构建的 `dist/` 由后端直接提供。

Linux / macOS的手动启动示例（完整平台行为未验收）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
npm run build
export XIAOZAO_BLENDER_PATH=/path/to/your/blender
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8765
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run build
npx playwright install chromium
npm run test:e2e
```

单元 / 接口测试使用临时目录与模拟模型服务。实际Blender测试需要本机安装，没有安装则明确跳过。

浏览器测试由 `tools/e2e_server.py` 在临时目录复制后端和已构建前端，在8766端口启动专用服务。它不读取工作台的 `data/` 与 `.runtime/`，清除测试服务的默认云密钥来源。新生成的免费基础作品用于端到端验证；模型服务请求被模拟，实际Blender重建使用公开示例。不要将8766用于自己的工作台。

可以设置 `CHROME_PATH` 使用已有浏览器，设置 `PYTHON` 指定测试启动器使用的Python。不要设置个人绝对路径到仓库。CI不能设置真实模型服务密钥。

GitHub工作流包含Linux后端测试与Windows完整集成测试，运行后保留浏览器报告；首次上传前无法声称Hosted CI已通过。`npm run build` 同时进行TypeScript检查。

## 公开包

```powershell
.\.venv\Scripts\python.exe tools/package_open_source.py
```

输出到 `artifacts/xiaozao-open-source/` 和 `artifacts/xiaozao-open-source-v0.1.0.zip`，附文件摘要。采用公开文件清单，不复制本机用户数据、历史交付报告和未审阅的二进制。新功能需要公开新文件时同时更新清单。
