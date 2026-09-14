import os
import sys
import queue
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def convert(source, destination):
    import fitz
    from pdf2docx import Converter
    with fitz.open(source) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF 已加密，请先解密再转换。")
        if not len(pdf):
            raise ValueError("PDF 没有页面。")
        scanned = sum(not page.get_text().strip() for page in pdf)
    fd, temporary = tempfile.mkstemp(suffix=".docx", dir=str(Path(destination).parent))
    os.close(fd)
    converter = None
    try:
        converter = Converter(source)
        converter.convert(temporary, multi_processing=False)
        converter.close()
        converter = None
        os.replace(temporary, destination)
    finally:
        if converter is not None:
            converter.close()
        if os.path.exists(temporary):
            os.remove(temporary)
    return scanned

class App:
    def __init__(self, root):
        self.root = root
        root.title("PDF 转 Word")
        root.geometry("640x300")
        root.minsize(540, 300)
        self.events = queue.Queue()
        self.busy = False
        self.source = tk.StringVar()
        self.status = tk.StringVar(value="选择 PDF，转换为可编辑的 Word 文档。")
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="PDF 转 Word", font=("Microsoft YaHei UI", 20)).pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=18)
        ttk.Entry(row, textvariable=self.source, state="readonly").pack(side="left", fill="x", expand=True)
        self.choose = ttk.Button(row, text="选择 PDF", command=self.select)
        self.choose.pack(side="left", padx=(10,0))
        self.start = ttk.Button(body, text="转换并保存 Word", command=self.run)
        self.start.pack(anchor="w")
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=12)
        ttk.Label(body, textvariable=self.status, wraplength=560).pack(anchor="w")
        ttk.Label(body, text="本地转换，无需上传文件。扫描件暂不支持文字识别。").pack(anchor="w", pady=12)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.poll)

    def select(self):
        path = filedialog.askopenfilename(filetypes=[("PDF 文档", "*.pdf")])
        if path:
            self.source.set(path)

    def run(self):
        source = self.source.get()
        if not source or not Path(source).is_file():
            messagebox.showwarning("请选择文件", "请先选择一个有效的 PDF 文件。")
            return
        target = filedialog.asksaveasfilename(defaultextension=".docx",
            initialfile=Path(source).stem + ".docx", filetypes=[("Word 文档", "*.docx")])
        if not target:
            return
        if Path(source).resolve() == Path(target).resolve():
            messagebox.showerror("保存位置错误", "不能覆盖原始 PDF 文件。")
            return
        self.busy = True
        self.choose.config(state="disabled")
        self.start.config(state="disabled")
        self.progress.start()
        self.status.set("正在转换，请稍候。页数较多时可能需要几分钟。")
        threading.Thread(target=self.worker, args=(source, target), daemon=True).start()

    def worker(self, source, target):
        try:
            scanned = convert(source, target)
            self.events.put(("ok", target, scanned))
        except Exception as exc:
            self.events.put(("error", str(exc), 0))

    def poll(self):
        try:
            kind, value, scanned = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.choose.config(state="normal")
            self.start.config(state="normal")
            if kind == "ok":
                self.status.set("已保存：" + value)
                note = "\n其中 %s 页未检测到文字层，图中的文字仍不可编辑。" % scanned if scanned else ""
                messagebox.showinfo("转换完成", "Word 已保存。复杂排版请检查并调整。" + note)
            else:
                self.status.set("转换失败，原文件未修改。")
                messagebox.showerror("转换失败", value)
        self.root.after(150, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("正在转换", "请等待转换完成后再关闭。")
        else:
            self.root.destroy()

def smoke_test(folder):
    import fitz
    from docx import Document
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source, target = folder / "sample.pdf", folder / "sample.docx"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Editable PDF conversion test")
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(120)
        page.insert_image(fitz.Rect(72, 120, 152, 200), pixmap=pix)
        pdf.save(source)
    convert(str(source), str(target))
    document = Document(target)
    assert "Editable PDF conversion test" in "\n".join(p.text for p in document.paragraphs)
    assert len(document.inline_shapes) > 0, "Image missing from output"
    (folder / "success.txt").write_text("Text and image conversion passed.", encoding="utf-8")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        smoke_test(sys.argv[2])
    else:
        App(tk.Tk()).root.mainloop()
