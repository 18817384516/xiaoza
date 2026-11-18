# 第三方软件与服务

本项目原创源码采用MIT许可。下列软件、权重、素材与服务保留各自许可及条款；项目的MIT许可不替代它们，也不代表得到这些项目或公司的认可。

## 安装依赖

源码包不分发 `node_modules/`、Python环境或打包后的网页。安装时由包管理器从相应软件源取得依赖。以 `package-lock.json`、`requirements.txt` 和安装包自身的LICENSE / NOTICE为准。

| 直接依赖 | 许可标识 / 说明 |
| --- | --- |
| React、React DOM | MIT |
| Three.js、React Three Fiber、Drei | MIT |
| Lucide React | ISC |
| FastAPI、Trimesh、Pytest | MIT |
| Manifold | Apache-2.0 |
| Uvicorn、NumPy、SciPy、Shapely、HTTPX、NetworkX | BSD系列；部分发行包含额外组件，查看各包许可 |
| Pillow | MIT-CMU |
| lxml | BSD-3-Clause，及其底层库许可 |
| scikit-image | BSD系列及包内列出的组件许可 |
| Playwright、TypeScript | Apache-2.0 |
| Vite与React插件 | MIT |

发布自行构建的网页、完整安装包或修改后的依赖时，须保留实际包含组件要求的声明。本文件是导航，不是全部依赖许可文本的替代。

## Blender

Blender是独立的GPL软件，安装工具从官方发行站下载并校验官方便携包；项目源码不包含Blender。其版权和许可随官方包保留。本项目通过独立进程调用已安装的Blender，不将其许可改写为MIT。若重新分发Blender本身或修改版，按该版本的许可处理。

## 可选本地实验

Shap-E、CLIP及中文翻译模型不随本源码分发。现有实验代码可读取本机自行准备的上游源码和检查点；使用前查阅上游仓库和对应模型卡。Shap-E与CLIP代码以各自上游的MIT许可为准，权重及翻译模型还需核对具体版本的声明。

## 外部服务与用户素材

大模型和Meshy的服务费用、隐私与输出使用条件由提供方决定。使用者应有权上传文字、图片与已有模型。项目许可不自动授予第三方角色、商标、人物肖像、参考图和服务输出的权利。

公开示例与演示截图仅为本项目自有演示流程产生的造型，不附用户参考图、对话历史、角色游戏资产和个人模型库。它们用于展示工作流，不表示经过实物打印或具有工业性能。
