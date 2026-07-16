import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import os

class PDFRectangleDrawer:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF 矩形绘制工具")
        self.root.geometry("1000x700")
        
        # 初始化变量
        self.pdf_path = None
        self.doc = None
        self.current_page_num = 0
        self.total_pages = 0
        self.rectangles = []  # 存储所有绘制的矩形 [(page_num, rect_coords), ...]
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.zoom = 1.5
        self.page_image = None  # 存储当前页面的图像对象
        
        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建顶部控制区域
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 打开PDF按钮
        self.open_btn = ttk.Button(self.control_frame, text="打开PDF", command=self.open_pdf)
        self.open_btn.pack(side=tk.LEFT, padx=5)
        
        # 页面导航区域
        self.nav_frame = ttk.Frame(self.control_frame)
        self.nav_frame.pack(side=tk.LEFT, padx=20)
        
        self.prev_btn = ttk.Button(self.nav_frame, text="上一页", command=self.prev_page, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        
        self.page_label = ttk.Label(self.nav_frame, text="0/0")
        self.page_label.pack(side=tk.LEFT, padx=5)
        
        self.next_btn = ttk.Button(self.nav_frame, text="下一页", command=self.next_page, state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        
        self.goto_btn = ttk.Button(self.nav_frame, text="跳转到", command=self.goto_page, state=tk.DISABLED)
        self.goto_btn.pack(side=tk.LEFT, padx=5)
        
        # 处理按钮
        self.process_frame = ttk.Frame(self.control_frame)
        self.process_frame.pack(side=tk.RIGHT)
        
        self.clear_btn = ttk.Button(self.process_frame, text="清除矩形", command=self.clear_rectangles, state=tk.DISABLED)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        self.process_btn = ttk.Button(self.process_frame, text="处理PDF", command=self.process_pdf, state=tk.DISABLED)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        # 创建画布区域
        self.canvas_frame = ttk.Frame(self.main_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="lightgray")
        self.h_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 底部状态栏
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = ttk.Label(self.status_frame, text="就绪。请打开PDF文件...")
        self.status_label.pack(side=tk.LEFT)
        
        self.rect_count_label = ttk.Label(self.status_frame, text="矩形数量: 0")
        self.rect_count_label.pack(side=tk.RIGHT)
        
        # 页面范围选择框架
        self.range_frame = ttk.LabelFrame(self.main_frame, text="处理页面范围")
        self.range_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.range_var = tk.StringVar(value="all")
        self.range_all = ttk.Radiobutton(self.range_frame, text="所有页面", variable=self.range_var, value="all")
        self.range_all.pack(side=tk.LEFT, padx=10)
        
        self.range_current = ttk.Radiobutton(self.range_frame, text="当前页面", variable=self.range_var, value="current")
        self.range_current.pack(side=tk.LEFT, padx=10)
        
        # 自定义范围按钮（替代原来的单选按钮和输入框）
        self.custom_range_btn = ttk.Button(self.range_frame, text="自定义范围", 
                                          command=self.apply_current_rectangles_to_range, 
                                          state=tk.DISABLED)
        self.custom_range_btn.pack(side=tk.LEFT, padx=10)
        
        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        
        # 绑定鼠标滚轮事件用于滚动和缩放
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel_scroll)  # Windows
        self.canvas.bind("<Button-4>", self.on_mouse_wheel_scroll)  # Linux上滚
        self.canvas.bind("<Button-5>", self.on_mouse_wheel_scroll)  # Linux下滚
        self.canvas.bind("<Control-MouseWheel>", self.on_mouse_wheel_zoom)  # Windows缩放
        self.canvas.bind("<Control-Button-4>", self.on_mouse_wheel_zoom)  # Linux缩放
        self.canvas.bind("<Control-Button-5>", self.on_mouse_wheel_zoom)  # Linux缩放
        
        # 绑定窗口大小变化事件
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
    def open_pdf(self):
        """打开PDF文件"""
        pdf_path = filedialog.askopenfilename(title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf")])
        if not pdf_path:
            return
            
        self.pdf_path = pdf_path
        self.doc = fitz.open(self.pdf_path)
        self.total_pages = len(self.doc)
        self.current_page_num = 0
        
        # 更新状态
        self.status_label.config(text=f"已加载: {os.path.basename(self.pdf_path)}")
        
        # 启用按钮
        self.prev_btn.config(state=tk.NORMAL)
        self.next_btn.config(state=tk.NORMAL)
        self.goto_btn.config(state=tk.NORMAL)
        self.clear_btn.config(state=tk.NORMAL)
        self.process_btn.config(state=tk.NORMAL)
        self.custom_range_btn.config(state=tk.NORMAL)
        
        # 加载第一页
        self.load_page(0)
        
    def load_page(self, page_num):
        """加载指定页面"""
        if not self.doc or page_num < 0 or page_num >= self.total_pages:
            return
            
        self.current_page_num = page_num
        self.page = self.doc[page_num]
        
        # 更新页面标签
        self.page_label.config(text=f"{page_num + 1}/{self.total_pages}")
        
        # 渲染页面
        self.render_page()
        
        # 绘制已有的矩形
        self.draw_existing_rectangles()
        
    def render_page(self):
        """渲染当前页面到画布"""
        # 清除画布
        self.canvas.delete("all")
        
        # 设置缩放
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = self.page.get_pixmap(matrix=mat)
        
        # 创建图像
        img_data = pix.samples
        img_mode = "RGBA" if pix.alpha else "RGB"
        img_size = (pix.width, pix.height)
        
        from PIL import Image, ImageTk
        img = Image.frombytes(img_mode, img_size, img_data)
        self.page_image = ImageTk.PhotoImage(image=img)
        
        # 计算画布中心位置
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 计算图像位置，使其居中
        x_pos = max(0, (canvas_width - pix.width) // 2)
        y_pos = max(0, (canvas_height - pix.height) // 2)
        
        # 设置画布滚动区域，确保足够大以容纳图像和居中的空间
        scroll_width = max(canvas_width, pix.width + x_pos * 2)
        scroll_height = max(canvas_height, pix.height + y_pos * 2)
        self.canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        
        # 在计算的位置显示图像
        self.canvas.create_image(x_pos, y_pos, image=self.page_image, tags="page", anchor=tk.NW)
        
        # 初始滚动位置
        if pix.width > canvas_width:
            self.canvas.xview_moveto(x_pos / scroll_width)
        else:
            self.canvas.xview_moveto(0)
            
        if pix.height > canvas_height:
            self.canvas.yview_moveto(y_pos / scroll_height)
        else:
            self.canvas.yview_moveto(0)

    def on_canvas_configure(self, event):
        """当画布大小改变时重新居中图像"""
        if hasattr(self, 'page') and self.page_image:
            # 重新渲染页面以更新居中位置
            self.render_page()
            self.draw_existing_rectangles()
        
    def draw_existing_rectangles(self):
        """在当前页面上绘制已存在的矩形"""
        for page_num, rect_coords in self.rectangles:
            if page_num == self.current_page_num:
                # 将PDF坐标转换为画布坐标
                x0, y0, x1, y1 = rect_coords
                canvas_x0 = x0 * self.zoom
                canvas_y0 = y0 * self.zoom
                canvas_x1 = x1 * self.zoom
                canvas_y1 = y1 * self.zoom
                
                # 获取图像位置偏移
                image_item = self.canvas.find_withtag("page")
                if image_item:
                    image_coords = self.canvas.coords(image_item[0])
                    if image_coords:
                        offset_x, offset_y = image_coords[0], image_coords[1]
                        
                        # 绘制矩形 - 半透明白色，考虑图像偏移
                        self.canvas.create_rectangle(
                            offset_x + canvas_x0, offset_y + canvas_y0, 
                            offset_x + canvas_x1, offset_y + canvas_y1, 
                            outline="black", width=1, fill="white", stipple="gray50", tags="rect"
                        )
    
    def prev_page(self):
        """显示上一页"""
        if self.current_page_num > 0:
            self.load_page(self.current_page_num - 1)
    
    def next_page(self):
        """显示下一页"""
        if self.current_page_num < self.total_pages - 1:
            self.load_page(self.current_page_num + 1)
    
    def goto_page(self):
        """跳转到指定页面"""
        page = simpledialog.askinteger("跳转到页面", 
                                        f"输入页码 (1-{self.total_pages}):",
                                        minvalue=1, maxvalue=self.total_pages)
        if page:
            self.load_page(page - 1)  # 转换为0索引
    
    def on_button_press(self, event):
        """鼠标按下事件"""
        if not self.doc:
            return
            
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
    
    def on_mouse_drag(self, event):
        """鼠标拖动事件"""
        if not self.doc or self.start_x is None:
            return
            
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        
        # 删除之前的临时矩形
        if self.rect:
            self.canvas.delete(self.rect)
            
        # 创建新的临时矩形 - 半透明白色
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, cur_x, cur_y,
            outline="black", width=1, fill="white", stipple="gray50", tags="temp_rect"
        )
    
    def on_button_release(self, event):
        """鼠标释放事件"""
        if not self.doc or self.start_x is None:
            return
            
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        
        # 确保矩形有一定大小
        if abs(end_x - self.start_x) < 5 or abs(end_y - self.start_y) < 5:
            if self.rect:
                self.canvas.delete(self.rect)
            self.rect = None
            self.start_x = None
            self.start_y = None
            return
        
        # 获取图像位置偏移
        image_item = self.canvas.find_withtag("page")
        if not image_item:
            return
            
        image_coords = self.canvas.coords(image_item[0])
        if not image_coords:
            return
            
        offset_x, offset_y = image_coords[0], image_coords[1]
        
        # 计算矩形坐标（PDF坐标系），考虑图像偏移
        pdf_x0 = (min(self.start_x, end_x) - offset_x) / self.zoom
        pdf_y0 = (min(self.start_y, end_y) - offset_y) / self.zoom
        pdf_x1 = (max(self.start_x, end_x) - offset_x) / self.zoom
        pdf_y1 = (max(self.start_y, end_y) - offset_y) / self.zoom
        
        # 添加到矩形列表
        self.rectangles.append((self.current_page_num, (pdf_x0, pdf_y0, pdf_x1, pdf_y1)))
        
        # 更新矩形计数
        self.rect_count_label.config(text=f"矩形数量: {len(self.rectangles)}")
        
        # 清除临时矩形
        if self.rect:
            self.canvas.delete(self.rect)
        
        # 绘制永久矩形 - 半透明白色
        self.canvas.create_rectangle(
            self.start_x, self.start_y, end_x, end_y,
            outline="black", width=1, fill="white", stipple="gray50", tags="rect"
        )
        
        self.rect = None
        self.start_x = None
        self.start_y = None
        
        # 更新状态栏
        self.status_label.config(text=f"已添加白色矩形 ({pdf_x0:.1f}, {pdf_y0:.1f}) - ({pdf_x1:.1f}, {pdf_y1:.1f})")
    
    def on_mouse_wheel_scroll(self, event):
        """鼠标滚轮事件用于滚动"""
        if not self.doc:
            return
            
        # 根据不同平台处理滚轮事件
        if event.num == 4 or event.num == 5:  # Linux
            delta = -1 if event.num == 5 else 1
        else:  # Windows
            delta = event.delta // 120
        
        # 滚动画布
        self.canvas.yview_scroll(-delta, "units")
    
    def on_mouse_wheel_zoom(self, event):
        """鼠标滚轮+Ctrl事件用于缩放"""
        if not self.doc:
            return
            
        # 根据不同平台处理滚轮事件
        if event.num == 4 or event.num == 5:  # Linux
            delta = -1 if event.num == 5 else 1
        else:  # Windows
            delta = event.delta // 120
        
        # 缩放因子
        factor = 0.1 if delta > 0 else -0.1
        new_zoom = max(0.5, min(3.0, self.zoom + factor))
        
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self.render_page()
            self.draw_existing_rectangles()
            self.status_label.config(text=f"缩放: {self.zoom:.1f}x")
    
    def clear_rectangles(self):
        """清除所有矩形"""
        if not self.rectangles:
            return
            
        if messagebox.askyesno("确认", "确定要清除所有矩形吗？"):
            self.rectangles = []
            self.rect_count_label.config(text="矩形数量: 0")
            self.render_page()  # 重新渲染页面，清除所有矩形
            self.status_label.config(text="已清除所有矩形")
    
    def parse_page_range(self, range_str, max_pages):
        """解析页面范围字符串，返回页码列表"""
        pages = []
        if not range_str:
            return pages
            
        parts = range_str.split(',')
        for part in parts:
            if '-' in part:
                start, end = part.split('-')
                try:
                    start_num = int(start.strip())
                    end_num = int(end.strip())
                    if 1 <= start_num <= max_pages and 1 <= end_num <= max_pages:
                        pages.extend(range(start_num, end_num + 1))
                except ValueError:
                    messagebox.showerror("错误", f"无效的页面范围: {part}")
                    return []
            else:
                try:
                    page_num = int(part.strip())
                    if 1 <= page_num <= max_pages:
                        pages.append(page_num)
                except ValueError:
                    messagebox.showerror("错误", f"无效的页码: {part}")
                    return []
                    
        return sorted(set(pages))  # 去重并排序
    
    def process_pdf(self):
        """处理PDF，应用白色矩形"""
        if not self.doc or not self.rectangles:
            messagebox.showinfo("提示", "没有PDF文件或矩形可处理")
            return
        
        # 确定处理页面范围
        range_type = self.range_var.get()
        pages_to_process = []
        
        if range_type == "all":
            # 处理所有页面
            pages_to_process = list(range(1, self.total_pages + 1))
        elif range_type == "current":
            # 只处理当前页面
            pages_to_process = [self.current_page_num + 1]
        elif range_type == "custom":
            # 自定义范围 - 由于移除了输入框，这里直接使用存储的自定义范围
            if hasattr(self, 'custom_pages') and self.custom_pages:
                pages_to_process = self.custom_pages
            else:
                messagebox.showerror("错误", "未设置自定义页面范围")
                return
        
        # 询问保存路径
        output_pdf = filedialog.asksaveasfilename(
            title="保存修改后的 PDF 文件", 
            defaultextension=".pdf", 
            filetypes=[("PDF 文件", "*.pdf")],
            initialfile=f"{os.path.splitext(os.path.basename(self.pdf_path))[0]}_modified.pdf"
        )
        
        if not output_pdf:
            return
        
        # 创建一个新的PDF文档
        doc_out = fitz.open(self.pdf_path)
        
        # 处理页面
        processed_count = 0
        for page_idx in range(len(doc_out)):
            page_num = page_idx + 1  # 转换为1-based索引
            
            # 如果页面不在处理范围内，则跳过
            if page_num not in pages_to_process:
                continue
                
            page = doc_out[page_idx]
            
            # 应用矩形
            for rect_page_num, rect_coords in self.rectangles:
                # 如果是当前页面的矩形，或者需要应用到所有页面
                if rect_page_num == page_idx or range_type == "all":
                    # 创建矩形对象
                    rect = fitz.Rect(*rect_coords)
                    
                    # 绘制白色填充矩形
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
            
            processed_count += 1
        
        # 保存修改后的PDF
        doc_out.save(output_pdf)
        doc_out.close()
        
        # 更新状态
        self.status_label.config(text=f"已处理 {processed_count} 页并保存到: {os.path.basename(output_pdf)}")
        messagebox.showinfo("处理完成", f"已成功处理 {processed_count} 页并保存到:\n{output_pdf}")

    def apply_current_rectangles_to_range(self):
        """将当前页面的矩形应用到指定的页面范围"""
        if not self.doc:
            messagebox.showinfo("提示", "请先打开PDF文件")
            return
            
        # 获取当前页面的矩形
        current_page_rectangles = []
        for page_num, rect_coords in self.rectangles:
            if page_num == self.current_page_num:
                current_page_rectangles.append(rect_coords)
        
        if not current_page_rectangles:
            messagebox.showinfo("提示", "当前页面没有绘制矩形")
            return
        
        # 弹出对话框，让用户输入要应用的页面范围
        range_str = simpledialog.askstring("应用到页面范围", 
                                       "输入要应用矩形的页面范围 (例如: 1-5,8,11-13):",
                                       initialvalue="")
        
        if not range_str:
            return
            
        pages = self.parse_page_range(range_str, self.total_pages)
        if not pages:
            return
        
        # 应用矩形到指定页面
        for page_num in pages:
            if page_num - 1 != self.current_page_num:  # 转换为0索引并排除当前页面
                for rect_coords in current_page_rectangles:
                    self.rectangles.append((page_num - 1, rect_coords))
        
        # 设置范围变量为"custom"并存储自定义页面列表
        self.range_var.set("custom")
        self.custom_pages = pages
        
        # 更新矩形计数
        self.rect_count_label.config(text=f"矩形数量: {len(self.rectangles)}")
        self.status_label.config(text=f"已将当前页面的矩形应用到 {len(pages)} 个页面")

# 创建主窗口
if __name__ == "__main__":
    root = tk.Tk()
    app = PDFRectangleDrawer(root)
    root.mainloop()