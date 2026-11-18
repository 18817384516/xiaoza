# 发布到 GitHub

建议仓库名：`xiaozao`。建议简介：`用文字、草图和参考图创作3D模型，结合本地Blender与打印网格检查。`

建议主题：`3d-printing`、`blender`、`text-to-3d`、`image-to-3d`、`react`、`fastapi`、`chinese`。

## 使用准备好的公开目录

本机开发目录可能存在个人设置与历史作品。使用打包工具生成的 **`artifacts/xiaozao-open-source/`** 作为公开源码根目录，或解压 `xiaozao-open-source-v0.1.0.zip` 后进入其中的 `xiaozao/`。

公开目录含源码、文档、模板和经过筛选的演示示例；不含依赖、Blender、模型权重、个人作品库、服务配置、运行日志、历史验收记录及Git历史。

### 方式一：网页上传

1. 在自己的GitHub账户创建空仓库 `xiaozao`，选择公开；无需另外生成README / LICENSE。
2. 将公开目录中的**内容**上传到仓库根目录，而非只上传ZIP或套一层父目录。
3. 确认 `.github/`、`.gitignore`、`.gitattributes` 等隐藏文件也被包含。若网页限制数量，请分批上传；隐藏文件不方便操作时优先使用下面的Git方式。
4. 检查README图片与链接，再查看Actions首次运行结果。

### 方式二：Git推送

在公开目录打开终端：

```sh
git init -b main
git add .
git status
git commit -m "Initial open-source release"
git remote add origin <复制你刚创建的GitHub仓库地址>
git push -u origin main
```

尖括号内容是需要替换的地址，不要原样执行。Git可能要求设置自己的提交姓名和邮箱；本项目没有替你写入身份信息。若你的Git不支持 `git init -b main`，用 `git init` 后再运行 `git branch -M main`。

## 仓库设置

- 默认分支为 `main`；在About中填写简介、主题。
- 确认Actions可以运行，首次应检查Linux后端任务与Windows Blender集成任务的实际结果。配置文件存在不等于Hosted CI已经成功。
- 开启Issues、Discussions（可选）和依赖更新。
- 在Security设置开启私密漏洞报告。若项目有维护者联系渠道，在SECURITY.md补充；不要填无效邮箱。
- 有协作者后设置main分支保护，要求通过CI与PR评审。

## 首次Release

CI通过并检查公开内容后，可创建 `v0.1.0` 标签和Release，将 [发布说明](release-v0.1.0.md) 作为描述。源码ZIP可作为附件；它不包含运行依赖，用户仍需安装。若以后发布带依赖 / Blender的安装包，需另外处理包含软件的许可声明。

`.github/workflows/source-package.yml` 是手动打包流程，只生成可下载的源码制品，不自动创建Release或推送代码。当前交付未替你创建远程仓库或公开上传。

## 每次更新

更新CHANGELOG和版本，运行构建与必要测试，运行 `python tools/package_open_source.py`。打包工具包含公开文件清单、路径 / 密钥检查和SHA256清单，默认不覆盖已有公开目录；需明确使用 `--replace` 才会替换工具自己的固定输出目录。对新加入图片和模型确认传播权限。

`PUBLIC_MANIFEST.json` 校验的是生成目录 / ZIP中的原始字节。Git换行转换后应重新打包生成清单，不要将Git检出后的换行差异误认为源码包被篡改。
