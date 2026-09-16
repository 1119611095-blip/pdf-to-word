# 视频中文实时翻译器

Windows 10/11 64 位桌面程序。打开本地视频后，使用 faster-whisper 识别人声，并调用本机 Ollama/Qwen 翻译为简体中文，边播放边显示字幕，同时保存 `.live.zh.srt`。

## EXE 使用前准备

1. 安装并启动 Ollama。
2. 在 Ollama 中准备一个 Qwen 模型；程序默认模型名为 `qwen2.5:7b`，也可以在界面中改成你本机已有的模型。
3. 首次选择 Whisper 模型时，faster-whisper 会下载对应模型文件，因此首次运行需要联网；下载后可复用本地缓存。

EXE 自带 Python 运行环境和 FFmpeg，不需要另装 Python。

## 默认建议

- Whisper: `small`
- 实时分段: `6 秒`
- 设备: `GPU 优先`，失败时会自动切换 CPU

## 输出

与原视频同目录生成：`原视频名.live.zh.srt`
