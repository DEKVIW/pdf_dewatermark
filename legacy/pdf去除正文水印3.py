import fitz
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk, ImageEnhance
import numpy as np
import tempfile
import os
import threading
import webbrowser
from datetime import datetime
import time
import gc
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

class PDFViewer:
    def __init__(self, root, pdf_path=None):
        self.root = root
        self.pdf_path = pdf_path
        self.selected_color = None
        self.bg_color_value = (255, 255, 255)  # 默认背景色为白色
        self.color_pick_mode = "watermark"  # 颜色选择模式：watermark或background
        self.tolerance = 30  # 默认颜色容差
        self.dpi = 300  # 默认DPI
        self.contrast = 1.2  # 默认对比度
        self.zoom = 2.0  # 默认缩放比例
        self.current_page_idx = 0  # 初始化当前页面索引
        self.preview_mode = False  # 预览模式标志
        self.original_image = None
        self.doc = None
        self.page = None
        self.pix = None
        self.image = None
        self.tk_image = None
        
        # 色阶去水印功能参数
        self.remove_method = "color_pick"  # 默认使用颜色点选方法
        self.resolution_factor = 3.0  # 默认渲染分辨率因子
        self.apply_sharpening = False  # 默认不应用锐化
        self.sharpening_strength = 1.0  # 默认锐化强度
        self.sensitivity = 20  # 默认颜色匹配敏感度
        self.image_format = "png"  # 默认图像格式
        self.image_quality = 95  # 默认图像质量
        
        # 设置主题样式
        self.style = ttk.Style()
        self.style.theme_use('clam')  # 使用更现代的主题
        
        # 配置颜色方案
        self.bg_color = "#f0f0f0"
        self.accent_color = "#4a86e8"
        self.highlight_color = "#e8f0fe"
        
        # 设置窗口图标
        try:
            self.root.iconbitmap("icon.ico")  # 如果有图标文件的话
        except:
            pass
        
        # 创建菜单栏
        self.create_menu()
        
        # 创建主界面
        self.create_ui()
        
        # 如果提供了PDF路径，则加载PDF
        if self.pdf_path:
            self.load_pdf(self.pdf_path)
        else:
            self.show_welcome_screen()
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开PDF", command=self.open_pdf, accelerator="Ctrl+O")
        file_menu.add_command(label="保存处理结果", command=self.save_processed_pdf, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="转换为灰度PDF", command=self.convert_to_grayscale)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit, accelerator="Alt+F4")
        menubar.add_cascade(label="文件", menu=file_menu)
        
        # 编辑菜单
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="重置颜色选择", command=self.reset_color_selection)
        edit_menu.add_command(label="恢复默认设置", command=self.reset_settings)
        menubar.add_cascade(label="编辑", menu=edit_menu)
        
        # 视图菜单
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="放大", command=lambda: self.change_zoom_level(0.5))
        view_menu.add_command(label="缩小", command=lambda: self.change_zoom_level(-0.5))
        view_menu.add_command(label="适合窗口", command=self.fit_to_window)
        menubar.add_cascade(label="视图", menu=view_menu)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        
        self.root.config(menu=menubar)
        
        # 绑定快捷键
        self.root.bind("<Control-o>", lambda e: self.open_pdf())
        self.root.bind("<Control-s>", lambda e: self.save_processed_pdf())
        
    def create_ui(self):
        """创建用户界面"""
        # 主框架
        self.main_frame = tk.Frame(self.root, bg=self.bg_color)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部控制区域
        self.top_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 创建页面导航区域
        self.create_page_navigation()
        
        # 创建工具栏
        self.create_toolbar()
        
        # 中间区域 - 左侧设置面板和右侧预览区域
        self.middle_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.middle_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧设置面板
        self.settings_frame = tk.LabelFrame(self.middle_frame, text="设置面板", bg=self.bg_color, padx=10, pady=10)
        self.settings_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # 创建设置控件
        self.create_settings_panel()
        
        # 右侧预览区域
        self.preview_frame = tk.LabelFrame(self.middle_frame, text="预览区域", bg=self.bg_color)
        self.preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 创建画布和滚动条
        self.create_canvas()
        
        # 底部状态栏
        self.create_statusbar()
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        self.progress_bar.pack_forget()  # 默认隐藏
    
    def create_page_navigation(self):
        """创建页面导航区域"""
        self.page_frame = tk.Frame(self.top_frame, bg=self.bg_color)
        self.page_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # 页面导航按钮
        self.nav_frame = tk.Frame(self.page_frame, bg=self.bg_color)
        self.nav_frame.pack(fill=tk.X)
        
        self.first_page_btn = ttk.Button(self.nav_frame, text="<<", width=3, command=self.goto_first_page)
        self.first_page_btn.pack(side=tk.LEFT, padx=2)
        
        self.prev_page_btn = ttk.Button(self.nav_frame, text="<", width=3, command=self.goto_prev_page)
        self.prev_page_btn.pack(side=tk.LEFT, padx=2)
        
        # 页面选择
        self.page_var = tk.StringVar(value="1")
        self.page_entry = ttk.Entry(self.nav_frame, textvariable=self.page_var, width=5)
        self.page_entry.pack(side=tk.LEFT, padx=2)
        self.page_entry.bind("<Return>", self.change_page_from_entry)
        
        self.page_count_label = ttk.Label(self.nav_frame, text="/0", background=self.bg_color)
        self.page_count_label.pack(side=tk.LEFT, padx=2)
        
        self.next_page_btn = ttk.Button(self.nav_frame, text=">", width=3, command=self.goto_next_page)
        self.next_page_btn.pack(side=tk.LEFT, padx=2)
        
        self.last_page_btn = ttk.Button(self.nav_frame, text=">>", width=3, command=self.goto_last_page)
        self.last_page_btn.pack(side=tk.LEFT, padx=2)
    
    def create_toolbar(self):
        """创建工具栏"""
        self.toolbar_frame = tk.Frame(self.top_frame, bg=self.bg_color)
        self.toolbar_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 放大/缩小按钮
        self.zoom_frame = tk.Frame(self.toolbar_frame, bg=self.bg_color)
        self.zoom_frame.pack(side=tk.RIGHT, padx=10)
        
        self.zoom_out_btn = ttk.Button(self.zoom_frame, text="-", width=3, command=lambda: self.change_zoom_level(-0.5))
        self.zoom_out_btn.pack(side=tk.LEFT, padx=2)
        
        self.zoom_var = tk.StringVar(value="200%")
        self.zoom_label = ttk.Label(self.zoom_frame, textvariable=self.zoom_var, background=self.bg_color, width=6)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        
        self.zoom_in_btn = ttk.Button(self.zoom_frame, text="+", width=3, command=lambda: self.change_zoom_level(0.5))
        self.zoom_in_btn.pack(side=tk.LEFT, padx=2)
        
        # 预览/处理按钮
        self.action_frame = tk.Frame(self.toolbar_frame, bg=self.bg_color)
        self.action_frame.pack(side=tk.RIGHT, padx=10)
        
        self.preview_button = ttk.Button(self.action_frame, text="预览效果", command=self.preview_watermark_removal)
        self.preview_button.pack(side=tk.LEFT, padx=5)
        self.preview_button.config(state=tk.DISABLED)
        
        self.process_curr_button = ttk.Button(self.action_frame, text="处理当前页", command=self.process_current_page)
        self.process_curr_button.pack(side=tk.LEFT, padx=5)
        self.process_curr_button.config(state=tk.DISABLED)
        
        self.process_range_button = ttk.Button(self.action_frame, text="处理页面范围", command=self.process_page_range)
        self.process_range_button.pack(side=tk.LEFT, padx=5)
        self.process_range_button.config(state=tk.DISABLED)
        
        self.process_button = ttk.Button(self.action_frame, text="处理全部", command=self.process_pdf)
        self.process_button.pack(side=tk.LEFT, padx=5)
        self.process_button.config(state=tk.DISABLED)
    
    def create_settings_panel(self):
        """创建设置面板"""
        # 处理方法选择
        self.method_frame = tk.LabelFrame(self.settings_frame, text="处理方法", bg=self.bg_color, padx=5, pady=5)
        self.method_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.method_var = tk.StringVar(value="color_pick")
        self.color_pick_radio = ttk.Radiobutton(self.method_frame, text="颜色点选", 
                                               variable=self.method_var,
                                               value="color_pick",
                                               command=self.update_method_settings)
        self.color_pick_radio.pack(side=tk.LEFT)
        
        self.threshold_radio = ttk.Radiobutton(self.method_frame, text="色阶阈值", 
                                              variable=self.method_var,
                                              value="threshold",
                                              command=self.update_method_settings)
        self.threshold_radio.pack(side=tk.LEFT, padx=(10, 0))
        
        # 颜色选择区域
        self.color_frame = tk.LabelFrame(self.settings_frame, text="水印颜色", bg=self.bg_color, padx=5, pady=5)
        self.color_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.color_info_label = ttk.Label(self.color_frame, text="点击图像选择水印颜色", background=self.bg_color)
        self.color_info_label.pack(anchor=tk.W, pady=5)
        
        self.color_display = tk.Frame(self.color_frame, width=50, height=25, bd=1, relief=tk.SUNKEN, bg="white")
        self.color_display.pack(fill=tk.X, pady=5)
        
        self.color_value_label = ttk.Label(self.color_frame, text="RGB: ---", background=self.bg_color)
        self.color_value_label.pack(anchor=tk.W, pady=5)
        
        # 背景颜色选择区域
        self.bg_color_frame = tk.LabelFrame(self.settings_frame, text="背景颜色", bg=self.bg_color, padx=5, pady=5)
        self.bg_color_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.bg_color_info_frame = tk.Frame(self.bg_color_frame, bg=self.bg_color)
        self.bg_color_info_frame.pack(fill=tk.X, pady=5)
        
        self.bg_color_mode = tk.StringVar(value="white")
        self.bg_white_radio = ttk.Radiobutton(self.bg_color_info_frame, text="白色背景", 
                                             variable=self.bg_color_mode,
                                             value="white",
                                             command=self.update_bg_color_mode)
        self.bg_white_radio.pack(side=tk.LEFT)
        
        self.bg_custom_radio = ttk.Radiobutton(self.bg_color_info_frame, text="自定义背景", 
                                              variable=self.bg_color_mode,
                                              value="custom",
                                              command=self.update_bg_color_mode)
        self.bg_custom_radio.pack(side=tk.LEFT, padx=(10, 0))
        
        self.bg_pick_button = ttk.Button(self.bg_color_frame, text="选择背景颜色", command=self.start_bg_color_pick)
        self.bg_pick_button.pack(fill=tk.X, pady=5)
        self.bg_pick_button.config(state=tk.DISABLED)
        
        self.bg_color_display = tk.Frame(self.bg_color_frame, width=50, height=25, bd=1, relief=tk.SUNKEN, bg="white")
        self.bg_color_display.pack(fill=tk.X, pady=5)
        
        self.bg_color_value_label = ttk.Label(self.bg_color_frame, text="RGB: (255, 255, 255)", background=self.bg_color)
        self.bg_color_value_label.pack(anchor=tk.W, pady=5)
        
        # 颜色容差/敏感度设置
        self.tolerance_frame = tk.LabelFrame(self.settings_frame, text="颜色容差", bg=self.bg_color, padx=5, pady=5)
        self.tolerance_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.tolerance_var = tk.IntVar(value=30)
        self.tolerance_slider = ttk.Scale(self.tolerance_frame, from_=5, to=100, 
                                         variable=self.tolerance_var, 
                                         orient=tk.HORIZONTAL)
        self.tolerance_slider.pack(fill=tk.X, pady=5)
        
        self.tolerance_value_frame = tk.Frame(self.tolerance_frame, bg=self.bg_color)
        self.tolerance_value_frame.pack(fill=tk.X)
        
        ttk.Label(self.tolerance_value_frame, text="小", background=self.bg_color).pack(side=tk.LEFT)
        ttk.Label(self.tolerance_value_frame, textvariable=self.tolerance_var, background=self.bg_color, width=5).pack(side=tk.LEFT, expand=True)
        ttk.Label(self.tolerance_value_frame, text="大", background=self.bg_color).pack(side=tk.RIGHT)
        
        # 色阶去水印高级设置
        self.advanced_frame = tk.LabelFrame(self.settings_frame, text="高级设置", bg=self.bg_color, padx=5, pady=5)
        
        # 分辨率因子设置
        self.resolution_frame = tk.Frame(self.advanced_frame, bg=self.bg_color)
        self.resolution_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.resolution_frame, text="分辨率因子:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.resolution_var = tk.DoubleVar(value=3.0)
        self.resolution_combo = ttk.Combobox(self.resolution_frame, textvariable=self.resolution_var, 
                                            values=["2.0", "3.0", "4.0", "5.0", "6.0"],
                                            width=5, state="readonly")
        self.resolution_combo.pack(side=tk.RIGHT)
        
        # 锐化设置
        self.sharpen_frame = tk.Frame(self.advanced_frame, bg=self.bg_color)
        self.sharpen_frame.pack(fill=tk.X, pady=5)
        
        self.sharpen_var = tk.BooleanVar(value=False)
        self.sharpen_check = ttk.Checkbutton(self.sharpen_frame, text="应用锐化", 
                                            variable=self.sharpen_var,
                                            command=self.update_sharpen_settings)
        self.sharpen_check.pack(side=tk.LEFT)
        
        # 锐化强度
        self.sharpen_strength_frame = tk.Frame(self.advanced_frame, bg=self.bg_color)
        self.sharpen_strength_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.sharpen_strength_frame, text="锐化强度:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.sharpen_strength_var = tk.DoubleVar(value=1.0)
        self.sharpen_strength_slider = ttk.Scale(self.sharpen_strength_frame, from_=0.5, to=2.0, 
                                               variable=self.sharpen_strength_var, 
                                               orient=tk.HORIZONTAL)
        self.sharpen_strength_slider.pack(fill=tk.X, pady=5)
        
        self.sharpen_strength_value_frame = tk.Frame(self.sharpen_strength_frame, bg=self.bg_color)
        self.sharpen_strength_value_frame.pack(fill=tk.X)
        
        ttk.Label(self.sharpen_strength_value_frame, text="弱", background=self.bg_color).pack(side=tk.LEFT)
        self.sharpen_strength_value_label = ttk.Label(self.sharpen_strength_value_frame, text="1.0", background=self.bg_color, width=5)
        self.sharpen_strength_value_label.pack(side=tk.LEFT, expand=True)
        ttk.Label(self.sharpen_strength_value_frame, text="强", background=self.bg_color).pack(side=tk.RIGHT)
        
        # 图像格式设置
        self.format_frame = tk.Frame(self.advanced_frame, bg=self.bg_color)
        self.format_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.format_frame, text="图像格式:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.format_var = tk.StringVar(value="png")
        self.format_combo = ttk.Combobox(self.format_frame, textvariable=self.format_var, 
                                        values=["png", "jpg"],
                                        width=5, state="readonly")
        self.format_combo.pack(side=tk.RIGHT)
        
        # 图像质量设置 (仅用于jpg)
        self.quality_frame = tk.Frame(self.advanced_frame, bg=self.bg_color)
        self.quality_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.quality_frame, text="JPG质量:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.quality_var = tk.IntVar(value=95)
        self.quality_slider = ttk.Scale(self.quality_frame, from_=70, to=100, 
                                       variable=self.quality_var, 
                                       orient=tk.HORIZONTAL)
        self.quality_slider.pack(fill=tk.X, pady=5)
        
        self.quality_value_frame = tk.Frame(self.quality_frame, bg=self.bg_color)
        self.quality_value_frame.pack(fill=tk.X)
        
        ttk.Label(self.quality_value_frame, text="低", background=self.bg_color).pack(side=tk.LEFT)
        ttk.Label(self.quality_value_frame, textvariable=self.quality_var, background=self.bg_color, width=5).pack(side=tk.LEFT, expand=True)
        ttk.Label(self.quality_value_frame, text="高", background=self.bg_color).pack(side=tk.RIGHT)
        
        # 图像质量设置
        self.quality_dpi_frame = tk.LabelFrame(self.settings_frame, text="图像质量", bg=self.bg_color, padx=5, pady=5)
        self.quality_dpi_frame.pack(fill=tk.X, pady=(0, 10))
        
        # DPI设置
        self.dpi_frame = tk.Frame(self.quality_dpi_frame, bg=self.bg_color)
        self.dpi_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.dpi_frame, text="DPI:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.dpi_var = tk.IntVar(value=300)
        self.dpi_combo = ttk.Combobox(self.dpi_frame, textvariable=self.dpi_var, 
                                     values=["150", "200", "300", "400", "600"],
                                     width=5, state="readonly")
        self.dpi_combo.pack(side=tk.RIGHT)
        
        # 对比度设置
        self.contrast_frame = tk.Frame(self.quality_dpi_frame, bg=self.bg_color)
        self.contrast_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.contrast_frame, text="对比度:", background=self.bg_color).pack(side=tk.LEFT)
        
        self.contrast_var = tk.DoubleVar(value=1.2)
        self.contrast_slider = ttk.Scale(self.contrast_frame, from_=1.0, to=2.0, 
                                        variable=self.contrast_var, 
                                        orient=tk.HORIZONTAL)
        self.contrast_slider.pack(fill=tk.X, pady=5)
        
        self.contrast_value_frame = tk.Frame(self.contrast_frame, bg=self.bg_color)
        self.contrast_value_frame.pack(fill=tk.X)
        
        ttk.Label(self.contrast_value_frame, text="低", background=self.bg_color).pack(side=tk.LEFT)
        self.contrast_value_label = ttk.Label(self.contrast_value_frame, text="1.2", background=self.bg_color, width=5)
        self.contrast_value_label.pack(side=tk.LEFT, expand=True)
        ttk.Label(self.contrast_value_frame, text="高", background=self.bg_color).pack(side=tk.RIGHT)
        
        # 根据初始处理方法更新UI
        self.update_method_settings()
        
        # 绑定事件
        self.tolerance_slider.bind("<ButtonRelease-1>", self.update_tolerance)
        self.contrast_slider.bind("<ButtonRelease-1>", self.update_contrast)
        self.sharpen_strength_slider.bind("<ButtonRelease-1>", self.update_sharpen_strength)
        self.format_combo.bind("<<ComboboxSelected>>", self.update_format_settings)
    
    def create_canvas(self):
        """创建画布和滚动条"""
        self.canvas_container = tk.Frame(self.preview_frame)
        self.canvas_container.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_container, bg="white", cursor="cross")
        self.h_scroll = ttk.Scrollbar(self.canvas_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(self.canvas_container, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 绑定事件
        self.canvas.bind("<Button-1>", self.get_color)
        self.canvas.bind("<MouseWheel>", self.mouse_wheel)  # Windows滚轮
        self.canvas.bind("<Button-4>", self.mouse_wheel)  # Linux上滚
        self.canvas.bind("<Button-5>", self.mouse_wheel)  # Linux下滚
        
        # 添加拖动和缩放功能
        self.canvas.bind("<Shift-Button-1>", self.start_move)
        self.canvas.bind("<Shift-B1-Motion>", self.move_canvas)
        self.canvas.bind("<Shift-ButtonRelease-1>", self.stop_move)
        
        # 变量用于拖动功能
        self.move_start = None
    
    def create_statusbar(self):
        """创建状态栏"""
        self.status_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_var = tk.StringVar(value="请打开PDF文件")
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_var, 
                                    anchor=tk.W, relief=tk.SUNKEN, padding=(5, 2))
        self.status_label.pack(fill=tk.X)
    
    def show_welcome_screen(self):
        """显示欢迎界面"""
        welcome_frame = tk.Frame(self.canvas, bg="white", bd=0)
        welcome_window = self.canvas.create_window(400, 300, window=welcome_frame, anchor=tk.CENTER)
        
        tk.Label(welcome_frame, text="PDF水印去除工具", font=("Arial", 24, "bold"), bg="white").pack(pady=10)
        tk.Label(welcome_frame, text="一键去除PDF文档中的水印", font=("Arial", 14), bg="white").pack(pady=5)
        
        button_frame = tk.Frame(welcome_frame, bg="white")
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="打开PDF文件", command=self.open_pdf, width=20).pack(side=tk.LEFT, padx=10)
        
        # 调整画布大小
        self.canvas.config(scrollregion=(0, 0, 800, 600))
    
    def open_pdf(self):
        """打开PDF文件"""
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            self.load_pdf(file_path)
    
    def load_pdf(self, pdf_path):
        """加载PDF文件"""
        try:
            # 关闭之前打开的文档
            if self.doc:
                self.doc.close()
            
            self.pdf_path = pdf_path
            self.doc = fitz.open(self.pdf_path)
            
            # 更新页面计数
            self.page_count_label.config(text=f"/{len(self.doc)}")
            
            # 重置页面索引
            self.current_page_idx = 0
            self.page_var.set("1")
            
            # 加载第一页
            self.load_page()
            
            # 更新状态栏
            filename = os.path.basename(self.pdf_path)
            self.status_var.set(f"已加载: {filename} - 点击图像选择水印颜色")
            
            # 重置颜色选择
            self.reset_color_selection()
            
            # 启用导航按钮
            self.update_navigation_buttons()
        except Exception as e:
            messagebox.showerror("错误", f"无法加载PDF文件:\n{str(e)}")
    
    def load_page(self):
        """加载当前页面"""
        if not self.doc:
            return
            
        self.page = self.doc[self.current_page_idx]
        self.update_image()
        self.preview_mode = False
    
    def update_image(self):
        """更新图像"""
        if not self.page:
            return
            
        self.mat = fitz.Matrix(self.zoom, self.zoom)
        self.pix = self.page.get_pixmap(matrix=self.mat)
        self.image = Image.frombytes("RGB", [self.pix.width, self.pix.height], self.pix.samples)
        self.original_image = self.image.copy()  # 保存原始图像用于预览
        self.tk_image = ImageTk.PhotoImage(self.image)
        self.update_canvas()
    
    def update_canvas(self):
        """更新画布内容"""
        self.canvas.delete("all")
        if self.tk_image:
            self.canvas.config(scrollregion=(0, 0, self.pix.width, self.pix.height))
            self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
    
    def change_page_from_entry(self, event=None):
        """从输入框更改页面"""
        try:
            page_num = int(self.page_var.get())
            if 1 <= page_num <= len(self.doc):
                self.current_page_idx = page_num - 1
                self.preview_mode = False
                self.load_page()
                self.update_navigation_buttons()
            else:
                self.page_var.set(str(self.current_page_idx + 1))
        except:
            self.page_var.set(str(self.current_page_idx + 1))
    
    def goto_first_page(self):
        """跳转到第一页"""
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx = 0
            self.page_var.set("1")
            self.preview_mode = False
            self.load_page()
            self.update_navigation_buttons()
    
    def goto_prev_page(self):
        """跳转到上一页"""
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.page_var.set(str(self.current_page_idx + 1))
            self.preview_mode = False
            self.load_page()
            self.update_navigation_buttons()
    
    def goto_next_page(self):
        """跳转到下一页"""
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx += 1
            self.page_var.set(str(self.current_page_idx + 1))
            self.preview_mode = False
            self.load_page()
            self.update_navigation_buttons()
    
    def goto_last_page(self):
        """跳转到最后一页"""
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx = len(self.doc) - 1
            self.page_var.set(str(self.current_page_idx + 1))
            self.preview_mode = False
            self.load_page()
            self.update_navigation_buttons()
    
    def update_navigation_buttons(self):
        """更新导航按钮状态"""
        if not self.doc:
            state = tk.DISABLED
        else:
            # 第一页和上一页按钮
            if self.current_page_idx <= 0:
                self.first_page_btn.config(state=tk.DISABLED)
                self.prev_page_btn.config(state=tk.DISABLED)
            else:
                self.first_page_btn.config(state=tk.NORMAL)
                self.prev_page_btn.config(state=tk.NORMAL)
            
            # 下一页和最后一页按钮
            if self.current_page_idx >= len(self.doc) - 1:
                self.next_page_btn.config(state=tk.DISABLED)
                self.last_page_btn.config(state=tk.DISABLED)
            else:
                self.next_page_btn.config(state=tk.NORMAL)
                self.last_page_btn.config(state=tk.NORMAL)
    
    def change_zoom_level(self, delta):
        """更改缩放级别"""
        new_zoom = self.zoom + delta
        if 0.5 <= new_zoom <= 5.0:
            self.zoom = new_zoom
            self.zoom_var.set(f"{int(self.zoom * 100)}%")
            self.update_image()
    
    def fit_to_window(self):
        """适应窗口大小"""
        if not self.page:
            return
            
        # 获取画布尺寸
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 获取页面尺寸
        page_width = self.page.rect.width
        page_height = self.page.rect.height
        
        # 计算合适的缩放比例
        width_ratio = canvas_width / page_width
        height_ratio = canvas_height / page_height
        
        # 使用较小的比例，确保整个页面可见
        self.zoom = min(width_ratio, height_ratio) * 0.9
        self.zoom_var.set(f"{int(self.zoom * 100)}%")
        
        self.update_image()
    
    def mouse_wheel(self, event):
        """鼠标滚轮事件处理"""
        # 检查是否按下Ctrl键
        ctrl_pressed = event.state & 0x4  # 0x4 是Ctrl键的掩码值
        
        if ctrl_pressed:
            # 使用滚轮进行缩放
            if event.num == 4 or event.delta > 0:  # 向上滚动，放大
                self.change_zoom_level(0.2)
            elif event.num == 5 or event.delta < 0:  # 向下滚动，缩小
                self.change_zoom_level(-0.2)
        else:
            # 普通滚动
            if event.num == 4 or event.delta > 0:  # 向上滚动
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:  # 向下滚动
                self.canvas.yview_scroll(1, "units")
    
    def start_move(self, event):
        """开始移动画布"""
        self.canvas.config(cursor="hand2")  # 改变鼠标光标为手形
        self.move_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    
    def move_canvas(self, event):
        """移动画布内容"""
        if self.move_start:
            # 计算移动距离
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)
            dx = x - self.move_start[0]
            dy = y - self.move_start[1]
            
            # 移动画布
            self.canvas.xview_scroll(-int(dx), "units")
            self.canvas.yview_scroll(-int(dy), "units")
            
            # 更新起始位置
            self.move_start = (x, y)
    
    def stop_move(self, event):
        """停止移动画布"""
        self.canvas.config(cursor="cross")  # 恢复默认光标
        self.move_start = None
    
    def get_color(self, event):
        """用户点击获取颜色"""
        if not self.doc:
            return
            
        # 检查是否按下Shift键（拖动模式）
        shift_pressed = event.state & 0x1  # 0x1 是Shift键的掩码值
        if shift_pressed:
            return
            
        if self.preview_mode:
            # 如果在预览模式，切换回原始模式
            self.preview_mode = False
            self.image = self.original_image.copy()
            self.tk_image = ImageTk.PhotoImage(self.image)
            self.update_canvas()
            if self.selected_color:
                self.status_var.set(f"已选颜色: RGB{self.selected_color}, 容差: {self.tolerance}")
            return
            
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # 确保坐标在图像范围内
        if 0 <= x < self.pix.width and 0 <= y < self.pix.height:
            color = self.image.getpixel((x, y))  # 获取 RGB 颜色
            
            if self.color_pick_mode == "watermark":
                # 水印颜色选择模式
                self.selected_color = color
                
                # 更新状态栏
                self.status_var.set(f"已选颜色: RGB{color}, 容差: {self.tolerance}")
                
                # 更新颜色显示
                self.color_display.config(bg=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
                self.color_value_label.config(text=f"RGB: {color}")
                
                # 启用预览和处理按钮
                self.preview_button.config(state=tk.NORMAL)
                self.process_curr_button.config(state=tk.NORMAL)
                self.process_range_button.config(state=tk.NORMAL)
                self.process_button.config(state=tk.NORMAL)
                
            elif self.color_pick_mode == "background":
                # 背景颜色选择模式
                self.bg_color_value = color
                
                # 更新背景颜色显示
                self.bg_color_display.config(bg=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
                self.bg_color_value_label.config(text=f"RGB: {color}")
                
                # 更新状态栏
                self.status_var.set(f"已选背景颜色: RGB{color}")
                
                # 切换回水印选择模式
                self.color_pick_mode = "watermark"
                self.color_info_label.config(text="点击图像选择水印颜色")
                self.root.unbind("<Escape>")
                
                # 如果已经选择了水印颜色，启用预览按钮
                if self.selected_color:
                    self.preview_button.config(state=tk.NORMAL)
    
    def update_tolerance(self, event):
        """更新颜色容差"""
        self.tolerance = self.tolerance_var.get()
        if self.selected_color:
            self.status_var.set(f"已选颜色: RGB{self.selected_color}, 容差: {self.tolerance}")
            self.preview_button.config(state=tk.NORMAL)
    
    def update_contrast(self, event):
        """更新对比度设置"""
        self.contrast = self.contrast_var.get()
        self.contrast_value_label.config(text=f"{self.contrast:.1f}")
        if self.selected_color:
            self.preview_button.config(state=tk.NORMAL)
    
    def update_method_settings(self):
        """根据所选处理方法更新设置界面"""
        method = self.method_var.get()
        self.remove_method = method
        
        if method == "color_pick":
            # 颜色点选模式
            self.tolerance_frame.config(text="颜色容差")
            if hasattr(self, 'advanced_frame'):
                self.advanced_frame.pack_forget()
            if self.selected_color:
                self.preview_button.config(state=tk.NORMAL)
        else:
            # 色阶阈值模式
            self.tolerance_frame.config(text="颜色敏感度")
            if hasattr(self, 'advanced_frame'):
                self.advanced_frame.pack(fill=tk.X, pady=(0, 10))
            if self.selected_color:
                self.preview_button.config(state=tk.NORMAL)
    
    def update_sharpen_settings(self):
        """更新锐化设置"""
        if self.sharpen_var.get():
            self.apply_sharpening = True
            self.sharpen_strength_slider.config(state=tk.NORMAL)
            if self.selected_color:
                self.preview_button.config(state=tk.NORMAL)
        else:
            self.apply_sharpening = False
            self.sharpen_strength_slider.config(state=tk.DISABLED)
            if self.selected_color:
                self.preview_button.config(state=tk.NORMAL)
    
    def update_sharpen_strength(self, event):
        """更新锐化强度"""
        self.sharpening_strength = self.sharpen_strength_var.get()
        self.sharpen_strength_value_label.config(text=f"{self.sharpening_strength:.1f}")
        if self.selected_color:
            self.preview_button.config(state=tk.NORMAL)
    
    def update_format_settings(self, event):
        """更新图像格式设置"""
        format_value = self.format_var.get()
        self.image_format = format_value
        
        # 根据格式更新质量滑块状态
        if format_value == "jpg":
            self.quality_slider.config(state=tk.NORMAL)
        else:
            self.quality_slider.config(state=tk.DISABLED)
        
        if self.selected_color:
            self.preview_button.config(state=tk.NORMAL)
    
    def preview_watermark_removal(self):
        """预览水印去除效果"""
        if not self.selected_color or not self.doc:
            return
            
        self.status_var.set("正在生成预览...")
        self.root.update()
        
        try:
            if self.remove_method == "color_pick":
                # 原始颜色点选方法
                img_data = np.array(self.original_image)
                
                # 计算与目标颜色的距离，去水印
                mask = np.sqrt(np.sum((img_data - np.array(self.selected_color)) ** 2, axis=-1)) < self.tolerance
                img_data[mask] = self.bg_color_value  # 变为背景色

                # 转换回 PIL 图片
                img_no_watermark = Image.fromarray(img_data)
                img_no_watermark = ImageEnhance.Contrast(img_no_watermark).enhance(self.contrast)  # 提高对比度
            else:
                # 色阶阈值方法
                img_data = np.array(self.original_image)
                
                # 获取水印颜色范围
                sensitivity = self.tolerance_var.get()
                watermark_color = list(self.selected_color)
                color_lower = [max(0, c - sensitivity) for c in watermark_color]
                color_upper = [min(255, c + sensitivity) for c in watermark_color]
                
                # 创建水印掩码
                mask = np.zeros(img_data.shape[:2], dtype=bool)
                for i in range(3):  # 对RGB三个通道分别处理
                    mask = mask | ((img_data[:, :, i] >= color_lower[i]) & 
                                  (img_data[:, :, i] <= color_upper[i]))
                
                # 将水印区域替换为背景色
                for i in range(3):
                    img_data[:, :, i][mask] = self.bg_color_value[i]
                
                # 转换回PIL图像
                img_no_watermark = Image.fromarray(img_data)
                
                # 应用对比度增强
                img_no_watermark = ImageEnhance.Contrast(img_no_watermark).enhance(self.contrast)
                
                # 可选：应用锐化
                if self.apply_sharpening:
                    enhancer = ImageEnhance.Sharpness(img_no_watermark)
                    img_no_watermark = enhancer.enhance(self.sharpening_strength)
            
            # 更新图像
            self.image = img_no_watermark
            self.tk_image = ImageTk.PhotoImage(self.image)
            self.update_canvas()
            
            self.preview_mode = True
            self.status_var.set("预览模式 - 点击图像返回原始视图")
        except Exception as e:
            messagebox.showerror("预览错误", f"生成预览时出错:\n{str(e)}")
    
    def process_pdf(self):
        """处理整个PDF文件"""
        if not self.selected_color or not self.doc:
            return
            
        # 询问保存位置
        output_pdf = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=self._get_default_output_filename()
        )
        
        if not output_pdf:
            return
            
        # 显示进度条
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        self.status_var.set("正在处理PDF...")
        self.root.update()
        
        # 禁用界面元素
        self._set_ui_state(tk.DISABLED)
        
        # 在单独的线程中处理PDF
        processing_thread = threading.Thread(
            target=self._process_pdf_thread,
            args=(output_pdf,)
        )
        processing_thread.daemon = True
        processing_thread.start()
    
    def _process_pdf_thread(self, output_pdf, page_indices=None):
        """在单独的线程中处理PDF"""
        try:
            self._remove_watermark(output_pdf, page_indices)
            
            # 在主线程中更新UI
            self.root.after(0, lambda: self._processing_complete(True, output_pdf))
        except Exception as e:
            # 在主线程中显示错误
            self.root.after(0, lambda: self._processing_complete(False, str(e)))
    
    def _remove_watermark(self, output_pdf, page_indices=None):
        """去除PDF中的水印"""
        new_doc = fitz.open()
        
        # 如果没有指定页面索引，则处理所有页面
        if page_indices is None:
            page_indices = range(len(self.doc))
        
        total_pages = len(page_indices)
        
        # 获取处理参数
        method = self.remove_method
        tolerance = self.tolerance_var.get()
        watermark_color = list(self.selected_color)
        bg_color = list(self.bg_color_value)
        
        # 色阶阈值参数
        if method == "threshold":
            color_lower = [max(0, c - tolerance) for c in watermark_color]
            color_upper = [min(255, c + tolerance) for c in watermark_color]
            resolution_factor = float(self.resolution_var.get())
            apply_sharpening = self.apply_sharpening
            sharpening_strength = self.sharpening_strength
            image_format = self.image_format
            image_quality = self.quality_var.get()
        else:
            # 原始方法参数
            scale_factor = self.dpi_var.get() / 72.0  # PDF默认是72 DPI
        
        for i, page_idx in enumerate(page_indices):
            # 更新进度
            progress = (i / total_pages) * 100
            self.root.after(0, lambda p=progress: self.progress_var.set(p))
            self.root.after(0, lambda p=i, t=total_pages, idx=page_idx: 
                           self.status_var.set(f"正在处理 {p+1}/{t} 页 (第{idx+1}页)..."))
            
            page = self.doc[page_idx]
            
            if method == "color_pick":
                # 原始颜色点选方法
                pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 转换为 numpy 数组
                img_data = np.array(img)

                # 计算与目标颜色的距离，去水印
                mask = np.sqrt(np.sum((img_data - np.array(watermark_color)) ** 2, axis=-1)) < tolerance
                img_data[mask] = bg_color  # 变为背景色

                # 转换回 PIL 图片
                img_no_watermark = Image.fromarray(img_data)
                img_no_watermark = ImageEnhance.Contrast(img_no_watermark).enhance(self.contrast)  # 提高对比度
                
                # 保存为临时文件
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    temp_file_path = temp_file.name
                    img_no_watermark.save(temp_file_path, dpi=(self.dpi_var.get(), self.dpi_var.get()))
            else:
                # 色阶阈值方法
                # 将页面渲染为高分辨率图像
                matrix = fitz.Matrix(resolution_factor, resolution_factor)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                
                # 将图像转换为PIL Image对象
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img_data = np.array(img)
                
                # 创建水印掩码
                mask = np.zeros(img_data.shape[:2], dtype=bool)
                for c in range(3):  # 对RGB三个通道分别处理
                    mask = mask | ((img_data[:, :, c] >= color_lower[c]) & 
                                  (img_data[:, :, c] <= color_upper[c]))
                
                # 将水印区域替换为背景色
                for c in range(3):
                    img_data[:, :, c][mask] = bg_color[c]
                
                # 转换回PIL图像
                processed_img = Image.fromarray(img_data)
                
                # 应用对比度增强
                processed_img = ImageEnhance.Contrast(processed_img).enhance(self.contrast)
                
                # 可选：应用锐化
                if apply_sharpening:
                    enhancer = ImageEnhance.Sharpness(processed_img)
                    processed_img = enhancer.enhance(sharpening_strength)
                
                # 保存为临时文件
                with tempfile.NamedTemporaryFile(suffix=f".{image_format}", delete=False) as temp_file:
                    temp_file_path = temp_file.name
                    if image_format == "jpg":
                        processed_img.save(temp_file_path, format="JPEG", quality=image_quality, optimize=True, 
                                         dpi=(self.dpi_var.get(), self.dpi_var.get()))
                    else:  # png
                        processed_img.save(temp_file_path, format="PNG", optimize=True, 
                                         dpi=(self.dpi_var.get(), self.dpi_var.get()))

            # 插入图像
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, filename=temp_file_path)
            
            # 删除临时文件
            try:
                os.unlink(temp_file_path)
            except:
                pass

        # 保存去水印后的 PDF - 应用优化选项
        new_doc.save(output_pdf, garbage=4, deflate=True, clean=True)
        new_doc.close()
    
    def _processing_complete(self, success, result):
        """处理完成后的回调"""
        # 隐藏进度条
        self.progress_bar.pack_forget()
        
        # 启用界面元素
        self._set_ui_state(tk.NORMAL)
        
        if success:
            self.status_var.set(f"处理完成，已保存为: {os.path.basename(result)}")
            messagebox.showinfo("处理完成", f"PDF水印去除完成，已保存为:\n{result}")
            
            # 询问是否打开处理后的文件
            if messagebox.askyesno("打开文件", "是否打开处理后的文件?"):
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(result)
                    else:  # macOS 和 Linux
                        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                        subprocess.call([opener, result])
                except:
                    messagebox.showinfo("提示", "无法自动打开文件，请手动打开。")
        else:
            self.status_var.set(f"处理出错: {result}")
            messagebox.showerror("处理错误", f"处理出错:\n{result}")
    
    def _set_ui_state(self, state):
        """设置UI元素状态"""
        # 禁用/启用各种按钮和控件
        self.preview_button.config(state=state)
        self.process_curr_button.config(state=state)
        self.process_range_button.config(state=state)
        self.process_button.config(state=state)
        self.page_entry.config(state=state)
        self.dpi_combo.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
        self.tolerance_slider.config(state=state)
        self.contrast_slider.config(state=state)
        self.first_page_btn.config(state=state)
        self.prev_page_btn.config(state=state)
        self.next_page_btn.config(state=state)
        self.last_page_btn.config(state=state)
        self.zoom_in_btn.config(state=state)
        self.zoom_out_btn.config(state=state)
    
    def _get_default_output_filename(self, suffix="全部"):
        """获取默认的输出文件名"""
        if not self.pdf_path:
            return "output.pdf"
            
        base_name = os.path.basename(self.pdf_path)
        name_without_ext = os.path.splitext(base_name)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name_without_ext}_无水印_{suffix}_{timestamp}.pdf"
    
    def reset_color_selection(self):
        """重置颜色选择"""
        self.selected_color = None
        self.color_display.config(bg="white")
        self.color_value_label.config(text="RGB: ---")
        self.preview_button.config(state=tk.DISABLED)
        self.process_curr_button.config(state=tk.DISABLED)
        self.process_range_button.config(state=tk.DISABLED)
        self.process_button.config(state=tk.DISABLED)
        self.status_var.set("请点击图像选择水印颜色")
        
        # 恢复到水印颜色选择模式
        self.color_pick_mode = "watermark"
        self.color_info_label.config(text="点击图像选择水印颜色")
    
    def reset_settings(self):
        """恢复默认设置"""
        self.tolerance_var.set(30)
        self.dpi_var.set(300)
        self.contrast_var.set(1.2)
        self.zoom = 2.0
        self.zoom_var.set("200%")
        
        self.tolerance = 30
        self.dpi = 300
        self.contrast = 1.2
        
        # 重置背景颜色为白色
        self.bg_color_value = (255, 255, 255)
        self.bg_color_mode.set("white")
        self.bg_color_display.config(bg="white")
        self.bg_color_value_label.config(text="RGB: (255, 255, 255)")
        self.bg_pick_button.config(state=tk.DISABLED)
        
        # 重置色阶去水印设置
        self.method_var.set("color_pick")
        self.remove_method = "color_pick"
        self.resolution_var.set(3.0)
        self.sharpen_var.set(False)
        self.apply_sharpening = False
        self.sharpening_strength = 1.0
        self.format_var.set("png")
        self.image_format = "png"
        self.quality_var.set(95)
        self.image_quality = 95
        
        # 更新界面
        self.update_method_settings()
        self.contrast_value_label.config(text="1.2")
        self.sharpen_strength_value_label.config(text="1.0")
        
        if self.page:
            self.update_image()
    
    def save_processed_pdf(self):
        """保存处理后的PDF"""
        if self.selected_color and self.doc:
            self.process_pdf()
        else:
            messagebox.showinfo("提示", "请先选择水印颜色")
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
使用说明:

1. 打开PDF文件: 点击"文件 > 打开PDF"或使用Ctrl+O快捷键。

2. 选择处理方法:
   - 颜色点选: 通过点击选择水印颜色
   - 色阶阈值: 使用色阶范围识别水印

3. 选择水印颜色: 在预览区域点击水印部分，选择水印的颜色。

4. 选择背景颜色(可选): 
   - 默认使用白色背景
   - 可选择"自定义背景"并点击"选择背景颜色"按钮
   - 在图像上点击选择背景颜色，使水印更好地融入背景

5. 调整设置:
   - 颜色容差/敏感度: 调整可识别为水印的颜色范围
   - DPI: 设置输出质量，更高的DPI意味着更清晰的结果
   - 对比度: 调整去水印后的对比度
   
6. 高级设置(色阶阈值模式):
   - 分辨率因子: 影响渲染质量和处理速度
   - 应用锐化: 提高图像清晰度
   - 图像格式: 选择PNG(无损)或JPG(有损但体积小)
   - JPG质量: 调整JPG格式的压缩质量

7. 操作技巧:
   - Ctrl+滚轮: 放大/缩小图像
   - Shift+鼠标左键拖动: 移动图像

8. 处理选项:
   - 预览效果: 查看当前页面的去水印效果
   - 处理当前页: 仅处理当前显示的页面
   - 处理页面范围: 处理指定页面范围
   - 处理全部: 处理整个PDF文档
   
9. 其他功能:
   - 转换为灰度PDF: 将彩色PDF转换为灰度，点击"文件 > 转换为灰度PDF"
   - 灰度转换可以帮助减轻某些类型的水印，也可作为预处理步骤

10. 保存结果: 处理完成后，选择保存位置。

提示: 在预览模式下，点击图像可返回原始视图。
        """
        messagebox.showinfo("使用说明", help_text)
    
    def show_about(self):
        """显示关于信息"""
        about_text = """
PDF水印去除工具

版本: 1.0.0

功能: 一键去除PDF文档中的水印

技术支持: example@example.com

© 2023 All Rights Reserved
        """
        messagebox.showinfo("关于", about_text)

    def process_current_page(self):
        """处理当前页面"""
        if not self.selected_color or not self.doc:
            return
        
        # 询问保存位置
        output_pdf = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=self._get_default_output_filename("当前页")
        )
        
        if not output_pdf:
            return
        
        # 显示进度条
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        self.status_var.set("正在处理当前页...")
        self.root.update()
        
        # 禁用界面元素
        self._set_ui_state(tk.DISABLED)
        
        # 在单独的线程中处理PDF
        processing_thread = threading.Thread(
            target=self._process_pdf_thread,
            args=(output_pdf, [self.current_page_idx])
        )
        processing_thread.daemon = True
        processing_thread.start()

    def process_page_range(self):
        """处理自定义页面范围"""
        if not self.selected_color or not self.doc:
            return
        
        # 创建对话框
        range_dialog = tk.Toplevel(self.root)
        range_dialog.title("设置页面范围")
        range_dialog.geometry("300x150")
        range_dialog.resizable(False, False)
        range_dialog.transient(self.root)  # 设置为主窗口的子窗口
        range_dialog.grab_set()  # 模态对话框
        
        # 页面范围输入
        frame = tk.Frame(range_dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="输入页面范围 (例如: 1-5,8,10-12):").pack(anchor=tk.W, pady=(0, 10))
        
        range_var = tk.StringVar()
        range_entry = ttk.Entry(frame, textvariable=range_var, width=30)
        range_entry.pack(fill=tk.X, pady=(0, 20))
        range_entry.focus_set()
        
        # 按钮区域
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        
        def on_cancel():
            range_dialog.destroy()
        
        def on_ok():
            page_range = range_var.get().strip()
            if not page_range:
                messagebox.showwarning("警告", "请输入有效的页面范围", parent=range_dialog)
                return
            
            try:
                # 解析页面范围
                page_indices = []
                for part in page_range.split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        # 将页码转换为索引 (页码从1开始，索引从0开始)
                        page_indices.extend(range(start-1, end))
                    else:
                        page_indices.append(int(part)-1)
                    
                # 验证页面范围
                total_pages = len(self.doc)
                valid_indices = [idx for idx in page_indices if 0 <= idx < total_pages]
                
                if not valid_indices:
                    messagebox.showwarning("警告", f"没有有效的页面。页面范围应为1-{total_pages}。", parent=range_dialog)
                    return
                
                if len(valid_indices) != len(page_indices):
                    messagebox.showwarning("警告", f"部分页面超出范围。已自动忽略无效页面。", parent=range_dialog)
                
                # 关闭对话框
                range_dialog.destroy()
                
                # 处理选中的页面
                self._process_selected_pages(valid_indices)
                
            except ValueError:
                messagebox.showwarning("警告", "页面范围格式无效，请使用正确的格式，例如: 1-5,8,10-12", parent=range_dialog)
        
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=5)
        
        # 绑定回车键
        range_dialog.bind("<Return>", lambda e: on_ok())
        range_dialog.bind("<Escape>", lambda e: on_cancel())

    def _process_selected_pages(self, page_indices):
        """处理选定的页面"""
        if not page_indices:
            return
        
        # 询问保存位置
        output_pdf = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=self._get_default_output_filename("自定义范围")
        )
        
        if not output_pdf:
            return
        
        # 显示进度条
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        self.status_var.set(f"正在处理 {len(page_indices)} 个页面...")
        self.root.update()
        
        # 禁用界面元素
        self._set_ui_state(tk.DISABLED)
        
        # 在单独的线程中处理PDF
        processing_thread = threading.Thread(
            target=self._process_pdf_thread,
            args=(output_pdf, page_indices)
        )
        processing_thread.daemon = True
        processing_thread.start()

    def update_bg_color_mode(self):
        """更新背景颜色模式"""
        mode = self.bg_color_mode.get()
        if mode == "white":
            self.bg_color_value = (255, 255, 255)
            self.bg_color_display.config(bg="white")
            self.bg_color_value_label.config(text="RGB: (255, 255, 255)")
            self.bg_pick_button.config(state=tk.DISABLED)
        else:
            self.bg_pick_button.config(state=tk.NORMAL)

    def start_bg_color_pick(self):
        """开始背景颜色选择模式"""
        if not self.doc:
            messagebox.showinfo("提示", "请先打开PDF文件")
            return
        
        self.color_pick_mode = "background"
        self.status_var.set("请点击图像选择背景颜色 (按ESC取消)")
        self.color_info_label.config(text="当前模式: 选择背景颜色")
        
        # 绑定ESC键退出背景取色模式
        self.root.bind("<Escape>", self.cancel_bg_color_pick)

    def cancel_bg_color_pick(self, event=None):
        """取消背景颜色选择模式"""
        self.color_pick_mode = "watermark"
        self.status_var.set("背景颜色选择已取消")
        self.color_info_label.config(text="点击图像选择水印颜色")
        self.root.unbind("<Escape>")

    def convert_to_grayscale(self):
        """将彩色PDF转换为灰度PDF"""
        if not self.pdf_path:
            messagebox.showinfo("提示", "请先打开PDF文件")
            return
        
        # 创建转换参数对话框
        gs_dialog = tk.Toplevel(self.root)
        gs_dialog.title("转换为灰度PDF")
        gs_dialog.geometry("400x350")
        gs_dialog.resizable(False, False)
        gs_dialog.transient(self.root)  # 设置为主窗口的子窗口
        gs_dialog.grab_set()  # 模态对话框
        
        # 参数设置区域
        frame = tk.Frame(gs_dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 输出文件设置
        tk.Label(frame, text="输出文件:").grid(row=0, column=0, sticky="w", pady=(0, 15))
        
        output_path_var = tk.StringVar()
        # 默认输出路径: 在原文件名后添加"_灰度"
        file_name, ext = os.path.splitext(self.pdf_path)
        default_output = f"{file_name}_灰度{ext}"
        output_path_var.set(default_output)
        
        output_entry = ttk.Entry(frame, textvariable=output_path_var, width=30)
        output_entry.grid(row=0, column=1, sticky="ew", pady=(0, 15))
        
        output_btn = ttk.Button(frame, text="浏览...", 
                               command=lambda: self._browse_output_file(output_path_var))
        output_btn.grid(row=0, column=2, padx=(5, 0), pady=(0, 15))
        
        # DPI设置
        tk.Label(frame, text="分辨率(DPI):").grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        dpi_var = tk.IntVar(value=600)
        dpi_combo = ttk.Combobox(frame, textvariable=dpi_var, 
                                values=["150", "300", "600", "1200"],
                                width=8, state="readonly")
        dpi_combo.grid(row=1, column=1, sticky="w", pady=(0, 10))
        tk.Label(frame, text="(较高的DPI会导致文件更大)").grid(row=1, column=1, padx=(80, 0), sticky="w", pady=(0, 10))
        
        # 批次大小设置
        tk.Label(frame, text="批次大小:").grid(row=2, column=0, sticky="w", pady=(0, 10))
        
        batch_var = tk.IntVar(value=2)
        batch_spin = ttk.Spinbox(frame, from_=1, to=20, textvariable=batch_var, width=8)
        batch_spin.grid(row=2, column=1, sticky="w", pady=(0, 10))
        tk.Label(frame, text="(每批处理的页数)").grid(row=2, column=1, padx=(80, 0), sticky="w", pady=(0, 10))
        
        # 进程数设置
        tk.Label(frame, text="进程数:").grid(row=3, column=0, sticky="w", pady=(0, 10))
        
        # 默认使用CPU核心数-1
        workers_var = tk.IntVar(value=max(1, cpu_count() - 1))
        workers_spin = ttk.Spinbox(frame, from_=1, to=cpu_count(), textvariable=workers_var, width=8)
        workers_spin.grid(row=3, column=1, sticky="w", pady=(0, 10))
        tk.Label(frame, text=f"(建议：{max(1, cpu_count() - 1)})").grid(row=3, column=1, padx=(80, 0), sticky="w", pady=(0, 10))
        
        # 内存使用提示
        memory_frame = ttk.LabelFrame(frame, text="内存使用提示")
        memory_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 20))
        
        memory_text = "高DPI设置会消耗更多内存。如果内存不足，请降低DPI或批次大小。\n" \
                     "处理1200DPI的PDF可能需要大量内存，请确保系统有足够的资源。"
        tk.Label(memory_frame, text=memory_text, justify="left", wraplength=350).pack(padx=10, pady=10)
        
        # 按钮区域
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, sticky="e")
        
        cancel_btn = ttk.Button(btn_frame, text="取消", command=gs_dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)
        
        start_btn = ttk.Button(btn_frame, text="开始转换", 
                              command=lambda: self._start_grayscale_conversion(
                                  output_path_var.get(), 
                                  dpi_var.get(),
                                  batch_var.get(),
                                  workers_var.get(),
                                  gs_dialog))
        start_btn.pack(side=tk.RIGHT, padx=5)

    def _browse_output_file(self, output_path_var):
        """浏览并选择输出文件路径"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=os.path.basename(output_path_var.get())
        )
        if file_path:
            output_path_var.set(file_path)

    def _process_grayscale_batch(self, args):
        """处理一批页面(灰度转换)"""
        input_path, start_page, end_page, dpi, batch_output = args
        
        # 打开输入PDF
        doc_input = fitz.open(input_path)
        
        # 创建输出PDF
        doc_output = fitz.open()
        
        # 处理每一页
        for page_num in range(start_page, min(end_page, len(doc_input))):
            page = doc_input[page_num]
            
            # 计算用于渲染的矩阵（基于DPI）
            zoom = dpi / 72  # 72是PDF的基本DPI
            matrix = fitz.Matrix(zoom, zoom)
            
            # 将页面渲染为灰度图像
            pix = page.get_pixmap(matrix=matrix, colorspace="gray")
            
            # 创建新页面
            new_page = doc_output.new_page(width=page.rect.width, height=page.rect.height)
            
            # 将灰度图像插入新页面
            new_page.insert_image(new_page.rect, pixmap=pix)
            
            # 手动释放pixmap内存
            pix = None
            gc.collect()
        
        # 保存输出PDF
        doc_output.save(batch_output)
        
        # 关闭文档
        doc_input.close()
        doc_output.close()
        
        # 手动回收内存
        gc.collect()
        
        return batch_output

    def _start_grayscale_conversion(self, output_path, dpi, batch_size, max_workers, dialog):
        """开始灰度转换过程"""
        dialog.destroy()
        
        # 显示进度对话框
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("转换为灰度PDF")
        progress_dialog.geometry("450x200")
        progress_dialog.resizable(False, False)
        progress_dialog.transient(self.root)
        progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁止关闭窗口
        
        # 进度信息区域
        info_frame = tk.Frame(progress_dialog, padx=20, pady=20)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        status_var = tk.StringVar(value="正在初始化转换...")
        status_label = ttk.Label(info_frame, textvariable=status_var, wraplength=400)
        status_label.pack(fill=tk.X, pady=(0, 10))
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(info_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=(0, 20))
        
        # 取消按钮（由于多进程处理，实际取消功能复杂，这里简化处理）
        cancel_btn = ttk.Button(info_frame, text="隐藏窗口", 
                               command=lambda: progress_dialog.withdraw())
        cancel_btn.pack()
        
        # 在单独的线程中开始转换
        threading.Thread(
            target=self._convert_grayscale_thread,
            args=(self.pdf_path, output_path, dpi, batch_size, max_workers, status_var, progress_var, progress_dialog),
            daemon=True
        ).start()

    def _convert_grayscale_thread(self, input_path, output_path, dpi, batch_size, max_workers, 
                                 status_var, progress_var, dialog):
        """在单独的线程中进行灰度转换"""
        try:
            # 创建临时目录
            temp_dir = os.path.join(os.path.dirname(output_path), f"temp_grayscale_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 更新状态
            self.root.after(0, lambda: status_var.set("正在分析PDF文件..."))
            
            # 打开输入PDF获取页数和基本信息
            doc_input = fitz.open(input_path)
            total_pages = len(doc_input)
            file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
            doc_input.close()
            
            self.root.after(0, lambda: status_var.set(
                f"开始处理: 总页数: {total_pages}, 文件大小: {file_size_mb:.2f} MB\n"
                f"使用 {max_workers} 个进程处理，每批 {batch_size} 页"
            ))
            
            # 准备批次参数
            batches = []
            for i in range(0, total_pages, batch_size):
                batch_output = os.path.join(temp_dir, f"batch_{i}.pdf")
                batches.append((input_path, i, min(i + batch_size, total_pages), dpi, batch_output))
            
            # 处理进度变量
            processed_batches = [0]  # 使用列表作为可变对象
            batch_pdfs = []
            
            # 进度回调函数
            def update_progress(batch_output):
                batch_pdfs.append(batch_output)
                processed_batches[0] += 1
                progress = (processed_batches[0] / len(batches)) * 50  # 转换占50%进度
                self.root.after(0, lambda: progress_var.set(progress))
                self.root.after(0, lambda: status_var.set(f"处理批次 {processed_batches[0]}/{len(batches)}..."))
                return batch_output
            
            # 使用单进程按顺序处理批次（避免多进程问题）
            for args in batches:
                batch_pdf = self._process_grayscale_batch(args)
                update_progress(batch_pdf)
            
            # 合并所有批次PDF
            self.root.after(0, lambda: status_var.set("正在合并批次..."))
            
            merged_count = 0
            doc_output = fitz.open()
            
            for batch_pdf in batch_pdfs:
                doc_batch = fitz.open(batch_pdf)
                doc_output.insert_pdf(doc_batch)
                doc_batch.close()
                
                # 更新合并进度
                merged_count += 1
                progress = 50 + (merged_count / len(batch_pdfs)) * 40  # 合并占40%进度
                self.root.after(0, lambda p=progress: progress_var.set(p))
                self.root.after(0, lambda c=merged_count, t=len(batch_pdfs): 
                               status_var.set(f"正在合并批次 {c}/{t}..."))
                
                # 定期进行垃圾回收
                gc.collect()
            
            # 保存最终输出PDF
            self.root.after(0, lambda: status_var.set(f"正在保存输出PDF: {output_path}"))
            self.root.after(0, lambda: progress_var.set(90))
            
            doc_output.save(output_path, garbage=4, deflate=True)  # 优化PDF大小
            doc_output.close()
            
            # 清理临时文件
            self.root.after(0, lambda: status_var.set("正在清理临时文件..."))
            
            for batch_pdf in batch_pdfs:
                try:
                    os.remove(batch_pdf)
                except Exception:
                    pass
            
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
            
            # 完成转换
            output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            
            self.root.after(0, lambda: progress_var.set(100))
            self.root.after(0, lambda: status_var.set(
                f"转换完成! 灰度PDF已保存至: {output_path}\n"
                f"输出文件大小: {output_size_mb:.2f} MB"
            ))
            
            # 更改取消按钮为关闭按钮
            for widget in dialog.winfo_children():
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        child.config(text="关闭", command=dialog.destroy)
            
            # 询问是否打开转换后的文件
            if messagebox.askyesno("转换完成", f"灰度PDF已保存至:\n{output_path}\n\n是否打开文件?"):
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(output_path)
                    else:  # macOS 和 Linux
                        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                        subprocess.call([opener, output_path])
                except:
                    messagebox.showinfo("提示", "无法自动打开文件，请手动打开。")
        
        except Exception as e:
            # 处理错误
            self.root.after(0, lambda: messagebox.showerror(
                "转换错误", 
                f"灰度转换过程中发生错误:\n{str(e)}"
            ))
            dialog.destroy()

def main():
    # 创建主窗口
    root = tk.Tk()
    root.title("PDF水印去除工具")
    root.geometry("1200x800")
    
    # 创建应用
    app = PDFViewer(root)
    
    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    main()