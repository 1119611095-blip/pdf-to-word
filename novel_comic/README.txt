1.0.1 修复版：改用内置官方 7-Zip，修复 BCJ2 不支持导致的安装失败。
更新方法：关闭旧程序，只替换 NovelComic.exe，再点击“安装 / 检查环境”。
保留 downloads、模型和已解压目录；校验通过的下载不会重新下载，未完成解压会重新解压补齐。

小说漫画工坊 · 本地部署包

1. 把 NovelComic.exe 放到 D:\NovelComic 文件夹（没有就新建）。
2. 双击 NovelComic.exe，点击“安装 / 检查环境”。
3. 等待 ComfyUI、Ollama 和模型下载、解压完成；首次需要联网访问 GitHub、Hugging Face 和 Ollama。
4. 界面提示“部署完成”后，输入小说或导入 TXT，点击“生成分镜”。
5. 修改分镜 JSON 中的 prompt（画面）和 caption（中文对白/旁白）后，点击“绘制漫画”。
6. 图片和 PDF 在 D:\NovelComic\output，每次任务单独保存。

模型与缓存默认均在 D:\NovelComic。无需管理员权限，不更改系统 Python，不覆盖已安装的 Ollama。
初次需要下载约 20～35GB（随压缩包大小变化），安装连同缓存预计需要 40～70GB。200GB 空间足够。
模型下载会显示进度，支持中断后重试并校验 SHA256。已完成的软件包通过标记跳过。
需要 NVIDIA 5070 Ti 兼容的较新驱动。安装时会检测 CUDA 是否能执行张量运算。
如果下载失败，可以再次点击安装重试；不能连接下载站时请检查电脑网络。

首次运行本地服务使用 11435（Ollama）和 8189（ComfyUI）端口，仅监听本机。
关闭应用不会立即停止后台模型服务；电脑重启后会结束，下次应用会重新启动。
日志在 D:\NovelComic\logs。

当前版本每次 1～6000 字、最多 12 格，中文对白作为图片下方文字区域排版。
采用逐格生成并导出逐页 PDF。保持人物描述一致，但此版本还未接入参考图锁定角色，不保证每格长相完全一致。
生成效果、速度和显存占用需要在你的真实电脑验证。首次建议输入 300～500 字，生成 2 格。
请保留原文并人工检查分镜，模型可能遗漏或改写情节。

已验证：Windows 打包、分镜数据检查、绘图工作流连接、异常传播、下载文件校验及 PNG/PDF 导出。
云端测试使用模拟绘图结果，不代表已经完成 5070 Ti 实际推理测试，也不表示你的电脑已安装完成。

来源：
https://github.com/Comfy-Org/ComfyUI
https://github.com/ollama/ollama
https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8
https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b
https://ollama.com/library/qwen3:8b
软件和模型遵循各自许可证。

内置 7-Zip 26.03（7za.exe），版权与许可证随包附带于 7zip 目录。
https://github.com/ip7z/7zip
