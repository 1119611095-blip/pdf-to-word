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


def convert_ocr(source, destination, keep_image=True, progress=lambda value: None):
    import io
    import fitz
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.oxml.ns import qn
    engine = RapidOCR()
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    empty_pages = []
    with fitz.open(source) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF 已加密，请先解密再转换。")
        if not len(pdf):
            raise ValueError("PDF 没有页面。")
        for index, page in enumerate(pdf):
            progress("正在识别第 %s / %s 页…" % (index + 1, len(pdf)))
            if index:
                document.add_page_break()
            document.add_heading("第 %s 页" % (index + 1), level=2)
            # Limit rendering size for unusually large engineering drawings.
            scale = min(3.0, 3200 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                                  colorspace=fitz.csRGB, alpha=False)
            rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            result, _ = engine(rgb[:, :, ::-1].copy())
            if result:
                for box, line, confidence in result:
                    document.add_paragraph(line)
            else:
                empty_pages.append(index + 1)
                document.add_paragraph("本页未识别到文字，请核对原图。")
            if keep_image or not result:
                document.add_paragraph("原页图片（用于核对）")
                image_scale = min(1.5, 1800 / max(page.rect.width, page.rect.height))
                preview = page.get_pixmap(matrix=fitz.Matrix(image_scale, image_scale),
                                         colorspace=fitz.csRGB, alpha=False)
                document.add_picture(io.BytesIO(preview.tobytes("png")), width=Inches(5.8))
    fd, temporary = tempfile.mkstemp(suffix=".docx", dir=str(Path(destination).parent))
    os.close(fd)
    try:
        document.save(temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return empty_pages

class App:
    def __init__(self, root):
        self.root = root
        root.title("PDF 转 Word")
        root.geometry("680x440")
        root.minsize(640, 440)
        self.events = queue.Queue()
        self.busy = False
        self.source = tk.StringVar()
        self.ocr_mode = tk.BooleanVar(value=True)
        self.keep_image = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="选择 PDF，转换为可编辑的 Word 文档。")
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="PDF 转 Word", font=("Microsoft YaHei UI", 20)).pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=18)
        ttk.Entry(row, textvariable=self.source, state="readonly").pack(side="left", fill="x", expand=True)
        self.choose = ttk.Button(row, text="选择 PDF", command=self.select)
        self.choose.pack(side="left", padx=(10,0))
        self.mode_button = ttk.Checkbutton(body, text="扫描件 OCR（中文 / 英文，逐行输出可编辑文字）", variable=self.ocr_mode)
        self.mode_button.pack(anchor="w", pady=4)
        self.image_button = ttk.Checkbutton(body, text="OCR 时附上原页图片，便于核对", variable=self.keep_image)
        self.image_button.pack(anchor="w", pady=4)
        ttk.Label(body, text="普通 PDF 如需保留排版，请取消勾选扫描件 OCR。").pack(anchor="w", pady=4)
        self.start = ttk.Button(body, text="转换并保存 Word", command=self.run)
        self.start.pack(anchor="w")
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=12)
        ttk.Label(body, textvariable=self.status, wraplength=560).pack(anchor="w")
        ttk.Label(body, text="离线识别，无需上传文件。识别结果请核对，扫描表格暂不还原结构。").pack(anchor="w", pady=12)
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
        self.mode_button.config(state="disabled")
        self.image_button.config(state="disabled")
        self.start.config(state="disabled")
        self.progress.start()
        self.status.set("正在转换，请稍候。页数较多时可能需要几分钟。")
        threading.Thread(target=self.worker, args=(source, target, self.ocr_mode.get(), self.keep_image.get()), daemon=True).start()

    def worker(self, source, target, ocr_mode, keep_image):
        try:
            if ocr_mode:
                empty_pages = convert_ocr(source, target, keep_image,
                    lambda text: self.events.put(("progress", text, "")))
                note = "OCR 已完成，请核对识别文字。"
                if empty_pages:
                    note += "\n未识别到文字的页码：" + ", ".join(map(str, empty_pages))
            else:
                scanned = convert(source, target)
                note = "复杂排版请检查并调整。"
                if scanned:
                    note += "\n有 %s 页没有文字层，可勾选扫描件 OCR 重试。" % scanned
            self.events.put(("ok", target, note))
        except Exception as exc:
            self.events.put(("error", str(exc), 0))

    def poll(self):
        try:
            kind, value, scanned = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            if kind == "progress":
                self.status.set(value)
                self.root.after(150, self.poll)
                return
            self.busy = False
            self.mode_button.config(state="normal")
            self.image_button.config(state="normal")
            self.progress.stop()
            self.choose.config(state="normal")
            self.start.config(state="normal")
            if kind == "ok":
                self.status.set("已保存：" + value)
                note = scanned
                messagebox.showinfo("转换完成", "Word 已保存。\n" + note)
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

    # Raster-only PDF: ensure OCR really recognizes pixels, not an existing text layer.
    scan_pdf = folder / "scan.pdf"
    with fitz.open() as original:
        page = original.new_page()
        page.insert_text((60, 80), "扫描文字识别测试", fontname="china-s", fontsize=24)
        page.insert_text((60, 130), "Hello OCR 12345", fontsize=24)
        pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        with fitz.open() as scan:
            scan.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, pixmap=pixels)
            scan.save(scan_pdf)
    with fitz.open(scan_pdf) as scan:
        assert not scan[0].get_text().strip()
    ocr_target = folder / "ocr.docx"
    assert convert_ocr(str(scan_pdf), str(ocr_target)) == []
    ocr_document = Document(ocr_target)
    recognized = "".join(p.text for p in ocr_document.paragraphs).replace(" ", "")
    assert "12345" in recognized, recognized
    assert "扫描文字识别测试" in recognized, recognized
    assert len(ocr_document.inline_shapes) == 1

    (folder / "success.txt").write_text("Text and image conversion passed.", encoding="utf-8")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        smoke_test(sys.argv[2])
    else:
        App(tk.Tk()).root.mainloop()
