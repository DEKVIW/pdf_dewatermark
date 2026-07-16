import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import io

def select_pdf():
    filepath = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
    if filepath:
        extract_images(filepath)

def extract_images(pdf_path):
    global images, image_data, canvas, img_buttons
    doc = fitz.open(pdf_path)
    images.clear()
    image_data.clear()
    
    for page_num in range(len(doc)):
        for img_index, img in enumerate(doc[page_num].get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            img_pil = Image.open(io.BytesIO(img_bytes))
            image_data.append((img_pil, base_image["width"], base_image["height"]))
            
            img_pil.thumbnail((100, 100))  # 创建缩略图
            img_tk = ImageTk.PhotoImage(img_pil)
            
            btn = tk.Button(canvas, image=img_tk, command=lambda i=len(images): show_image_info(i))
            btn.image = img_tk
            btn.pack(side=tk.LEFT, padx=5, pady=5)
            images.append(btn)

def show_image_info(index):
    img_pil, width, height = image_data[index]
    messagebox.showinfo("图片信息", f"宽度: {width}px\n高度: {height}px")

root = tk.Tk()
root.title("PDF 图片选择器")
root.geometry("600x400")

btn_open = tk.Button(root, text="选择 PDF", command=select_pdf)
btn_open.pack(pady=10)

canvas = tk.Frame(root)
canvas.pack(fill=tk.BOTH, expand=True)

images = []
image_data = []

root.mainloop()
