import os
import re
import sys
import time
import tempfile
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import imageio_ffmpeg
from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QLineEdit, QProgressBar, QMessageBox, QSlider
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


@dataclass
class Subtitle:
    start: float
    end: float
    text: str


def srt_time(sec: float) -> str:
    ms = max(0, int(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration_of(path: str) -> float:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr or "")
    if not m:
        return 0.0
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))


def audio_chunk(path: str, start: float, seconds: float) -> str:
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = [
        ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{max(0,start):.3f}",
        "-i", path, "-t", f"{max(.3,seconds):.3f}", "-vn", "-ac", "1",
        "-ar", "16000", "-c:a", "pcm_s16le", wav,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        try: os.remove(wav)
        except OSError: pass
        raise RuntimeError("FFmpeg 提取音频失败：" + (p.stderr or "")[-1000:])
    return wav


def translate(text: str, model: str) -> str:
    prompt = (
        "你是影视字幕翻译器。把下面内容准确、自然、简洁地翻译成简体中文。"
        "只输出译文，不解释，不加引号。\n原文：" + text.strip()
    )
    r = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.1}}, timeout=90,
    )
    r.raise_for_status()
    return (r.json().get("response") or "").strip()


class LiveWorker(QThread):
    message = Signal(str)
    percent = Signal(int)
    subtitle = Signal(object)
    ready = Signal()
    failed = Signal(str)
    completed = Signal()

    def __init__(self, video: str, whisper_name: str, ollama_name: str,
                 gpu: bool, chunk: float):
        super().__init__()
        self.video = video
        self.whisper_name = whisper_name
        self.ollama_name = ollama_name
        self.gpu = gpu
        self.chunk = chunk
        self._lock = threading.Lock()
        self._play_pos = 0.0
        self._seek: Optional[float] = None
        self._buffer_sent = False

    def set_position(self, pos: float):
        with self._lock:
            self._play_pos = max(0.0, pos)

    def seek(self, pos: float):
        with self._lock:
            self._seek = max(0.0, pos)
            self._play_pos = max(0.0, pos)

    def state(self):
        with self._lock:
            p, s = self._play_pos, self._seek
            self._seek = None
            return p, s

    def load_model(self):
        from faster_whisper import WhisperModel
        if self.gpu:
            try:
                self.message.emit(f"正在加载 Whisper {self.whisper_name}（GPU）…")
                return WhisperModel(self.whisper_name, device="cuda", compute_type="float16"), "GPU"
            except Exception:
                self.message.emit("GPU 初始化失败，自动切换 CPU…")
        return WhisperModel(self.whisper_name, device="cpu", compute_type="int8"), "CPU"

    def run(self):
        try:
            total = duration_of(self.video)
            if total <= 0:
                raise RuntimeError("无法读取视频时长。")
            model, device = self.load_model()
            self.message.emit(f"实时翻译已启动（{device}）")
            cursor = 0.0
            language = None
            overlap = 0.6
            ahead = max(12.0, self.chunk * 2)

            while cursor < total and not self.isInterruptionRequested():
                play_pos, seek = self.state()
                if seek is not None and abs(seek - cursor) > self.chunk:
                    cursor = max(0.0, seek - 0.4)
                if self._buffer_sent and cursor > play_pos + ahead:
                    time.sleep(0.12)
                    continue

                logical_start = cursor
                logical_end = min(total, cursor + self.chunk)
                extract_start = max(0.0, logical_start - overlap)
                wav = None
                try:
                    self.message.emit(
                        f"识别 {int(logical_start//60):02d}:{int(logical_start%60):02d} → "
                        f"{int(logical_end//60):02d}:{int(logical_end%60):02d}"
                    )
                    wav = audio_chunk(self.video, extract_start,
                                      logical_end - extract_start + overlap)
                    segs, info = model.transcribe(
                        wav, beam_size=1, best_of=1, vad_filter=True,
                        word_timestamps=False, language=language,
                        condition_on_previous_text=False,
                    )
                    if language is None:
                        language = getattr(info, "language", None)
                    for seg in segs:
                        if self.isInterruptionRequested():
                            return
                        src = (seg.text or "").strip()
                        if not src:
                            continue
                        a = extract_start + float(seg.start)
                        b = extract_start + float(seg.end)
                        mid = (a+b)/2
                        if mid < logical_start - .15 or mid >= logical_end + .15:
                            continue
                        self.message.emit("正在翻译成中文…")
                        zh = translate(src, self.ollama_name) or src
                        self.subtitle.emit(Subtitle(max(0,a), min(total,max(a+.15,b)), zh))
                finally:
                    if wav:
                        try: os.remove(wav)
                        except OSError: pass

                cursor = logical_end
                self.percent.emit(min(100, int(cursor/total*100)))
                if not self._buffer_sent:
                    self._buffer_sent = True
                    self.ready.emit()

            if not self.isInterruptionRequested():
                self.completed.emit()
        except Exception as e:
            self.failed.emit(str(e))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频中文实时翻译器")
        self.resize(1120, 780)
        self.video = ""
        self.items: list[Subtitle] = []
        self.worker: Optional[LiveWorker] = None

        root = QWidget(); self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        bar = QHBoxLayout()
        self.open_btn = QPushButton("打开视频")
        self.live_btn = QPushButton("开始实时翻译"); self.live_btn.setEnabled(False)
        self.whisper = QComboBox(); self.whisper.addItems(["tiny","base","small","medium"]); self.whisper.setCurrentText("small")
        self.ollama = QLineEdit("qwen2.5:7b")
        self.device = QComboBox(); self.device.addItems(["GPU 优先","CPU"])
        self.chunk = QComboBox(); self.chunk.addItems(["4 秒","6 秒","10 秒"]); self.chunk.setCurrentText("6 秒")
        for w in [self.open_btn,QLabel("Whisper"),self.whisper,QLabel("Qwen/Ollama"),self.ollama,self.device,QLabel("分段"),self.chunk,self.live_btn]:
            bar.addWidget(w)
        lay.addLayout(bar)

        self.view = QVideoWidget(); self.view.setMinimumHeight(470); lay.addWidget(self.view,1)
        self.caption = QLabel("打开视频后点击“开始实时翻译”")
        self.caption.setAlignment(Qt.AlignCenter); self.caption.setWordWrap(True); self.caption.setMinimumHeight(68)
        self.caption.setStyleSheet("QLabel{background:#111;color:white;font-size:22px;padding:10px;border-radius:8px}")
        lay.addWidget(self.caption)

        ctl = QHBoxLayout()
        self.play_btn = QPushButton("播放"); self.play_btn.setEnabled(False)
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0,0)
        self.clock = QLabel("00:00 / 00:00")
        ctl.addWidget(self.play_btn); ctl.addWidget(self.slider,1); ctl.addWidget(self.clock); lay.addLayout(ctl)
        self.progress = QProgressBar(); lay.addWidget(self.progress)
        self.status = QLabel("就绪"); lay.addWidget(self.status)

        self.audio = QAudioOutput(); self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.view)
        self.open_btn.clicked.connect(self.open_video)
        self.live_btn.clicked.connect(self.toggle_live)
        self.play_btn.clicked.connect(self.toggle_play)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.slider.sliderReleased.connect(self.seek_released)
        self.timer = QTimer(self); self.timer.timeout.connect(self.show_caption); self.timer.start(100)

    def open_video(self):
        p, _ = QFileDialog.getOpenFileName(self,"选择视频","","视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;所有文件 (*.*)")
        if not p: return
        self.stop_worker()
        self.video = p; self.items = []
        self.player.stop(); self.player.setSource(QUrl.fromLocalFile(p))
        self.live_btn.setEnabled(True); self.play_btn.setEnabled(True)
        self.progress.setValue(0); self.status.setText("已打开：" + Path(p).name)
        self.caption.setText("点击“开始实时翻译”，首段字幕准备好后会自动播放")

    def toggle_live(self):
        if self.worker and self.worker.isRunning():
            self.stop_worker(); self.status.setText("已停止实时翻译")
            return
        if not self.video: return
        self.items = []; self.player.pause(); self.player.setPosition(0); self.progress.setValue(0)
        self.caption.setText("正在准备第一段中文字幕…")
        self.live_btn.setText("停止实时翻译")
        self.worker = LiveWorker(self.video, self.whisper.currentText(), self.ollama.text().strip() or "qwen2.5:7b",
                                 self.device.currentIndex()==0, float(self.chunk.currentText().split()[0]))
        self.worker.message.connect(self.status.setText)
        self.worker.percent.connect(self.progress.setValue)
        self.worker.subtitle.connect(self.add_subtitle)
        self.worker.ready.connect(self.start_after_buffer)
        self.worker.failed.connect(self.worker_error)
        self.worker.completed.connect(self.worker_done)
        self.worker.start()

    def stop_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption(); self.worker.wait(3000)
        self.worker = None; self.live_btn.setText("开始实时翻译")

    def start_after_buffer(self):
        self.player.play(); self.play_btn.setText("暂停")
        self.status.setText("首段字幕已完成，正在边播边翻译…")

    def add_subtitle(self, item):
        for i, old in enumerate(self.items):
            if abs(old.start-item.start)<.45 and abs(old.end-item.end)<.7:
                self.items[i]=item; break
        else:
            self.items.append(item)
        self.items.sort(key=lambda x:(x.start,x.end)); self.save_srt()

    def save_srt(self):
        if not self.video or not self.items: return
        out = str(Path(self.video).with_suffix("")) + ".live.zh.srt"
        with open(out,"w",encoding="utf-8-sig") as f:
            for n,x in enumerate(self.items,1):
                f.write(f"{n}\n{srt_time(x.start)} --> {srt_time(x.end)}\n{x.text}\n\n")

    def worker_error(self, msg):
        self.live_btn.setText("开始实时翻译"); self.worker=None
        QMessageBox.critical(self,"实时翻译错误",msg+"\n\n请确认：1. Ollama 已启动；2. 已安装填写的 Qwen 模型；3. 首次使用 Whisper 时电脑可联网下载模型。")

    def worker_done(self):
        self.save_srt(); self.progress.setValue(100); self.live_btn.setText("开始实时翻译"); self.worker=None
        self.status.setText("视频已处理完，中文字幕已保存为 .live.zh.srt")

    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:
            self.player.pause(); self.play_btn.setText("播放")
        else:
            self.player.play(); self.play_btn.setText("暂停")

    def position_changed(self, pos):
        if not self.slider.isSliderDown(): self.slider.setValue(pos)
        self.update_clock(pos,self.player.duration())
        if self.worker and self.worker.isRunning(): self.worker.set_position(pos/1000)

    def duration_changed(self, dur):
        self.slider.setRange(0,dur); self.update_clock(self.player.position(),dur)

    def update_clock(self,pos,dur):
        def f(ms):
            s=max(0,ms//1000); return f"{s//60:02d}:{s%60:02d}"
        self.clock.setText(f"{f(pos)} / {f(dur)}")

    def seek_released(self):
        if self.worker and self.worker.isRunning(): self.worker.seek(self.player.position()/1000)

    def show_caption(self):
        if not self.items: return
        t=self.player.position()/1000
        m=[x.text for x in self.items if x.start-.08<=t<=x.end+.12]
        self.caption.setText("\n".join(m[-2:]) if m else " ")

    def closeEvent(self,event):
        self.stop_worker(); event.accept()


def main():
    app=QApplication(sys.argv)
    w=Window(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
