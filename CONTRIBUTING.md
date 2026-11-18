# 参与贡献

欢迎提交问题、改进文档和贡献代码。界面与默认文档使用中文，英文 issue 和 PR 也欢迎。

## 开始开发

安装和运行见 [README](README.md)，开发流程见 [开发指南](docs/development.md)。建议 Python 3.13、Node.js 24；Windows 是当前完整流程的主要验证平台。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm run build
.\.venv\Scripts\python.exe -m pytest -q
npx playwright install chromium
npm run test:e2e
```

浏览器测试自动启动8766端口的临时工作台，不读取个人作品和服务密钥。测试实际 Blender 重建前先运行 `安装Blender建模.cmd`；未安装时该条和真实 Blender 后端测试会明确跳过。测试报告应注明跳过项。

## 提交变更

1. 从 `main` 创建自己的分支，一次 PR 聚焦一个问题。
2. 描述具体触发条件、修改后的行为和验证结果；界面变更附桌面 / 手机截图。
3. 针对实际行为改变补充必要的回归测试。不要将付费服务调用放入自动测试。
4. 确认未提交 `data/`、`.runtime/`、密钥、用户图片、模型权重、依赖目录和个人运行日志。
5. 通过 pull request 提交，接受评审后再合并。

没有真实模型验证时，请写“模拟接口验证”，不要声称生成质量达标。涉及打印的改动应重新读取导出的网格，而非只验证内存中的对象。

## 许可与素材

提交本项目原创代码即表示你同意按 [MIT License](LICENSE) 发布该贡献。引用第三方代码、图像、模型和字体时保留其许可与来源。不要提交无法确认传播权限的角色、人物照片或参考图。第三方服务输出还受该服务条款约束。

## 问题与安全报告

普通问题请使用仓库的 issue 模板。安全问题按 [SECURITY.md](SECURITY.md) 私下报告，勿公开密钥或可直接利用的细节。
