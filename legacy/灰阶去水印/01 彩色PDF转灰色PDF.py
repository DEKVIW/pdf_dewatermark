"""
将彩色PDF转换为灰度PDF (优化版)

安装所需的库:
pip install PyMuPDF tqdm

注意事项:
1. 此脚本通过渲染页面实现颜色转换，可能会使PDF文件变大
2. 如果原始PDF包含文本，转换后的PDF可能不支持文本搜索
3. 可以调整DPI参数控制输出质量和文件大小
4. 使用多进程处理提高转换速度，同时显示进度条
"""

import fitz  # PyMuPDF
import time
import os
import gc
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


def process_batch(args):
    """处理一批页面"""
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


def convert_pdf_to_grayscale(input_path, output_path, dpi=1200, batch_size=2, max_workers=None):
    """
    将彩色PDF转换为灰度PDF (优化版)

    参数:
    input_path: 输入的彩色PDF文件路径
    output_path: 输出的灰度PDF文件路径
    dpi: 图像分辨率(默认1200)
    batch_size: 每批处理的页面数
    max_workers: 最大工作进程数（默认为CPU核心数）
    """
    start_time = time.time()

    # 创建临时目录
    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_grayscale_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)

    # 打开输入PDF获取页数和基本信息
    doc_input = fitz.open(input_path)
    total_pages = len(doc_input)
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    doc_input.close()

    print(f"开始处理 {input_path}")
    print(f"总页数: {total_pages}, 文件大小: {file_size_mb:.2f} MB")

    # 确定工作进程数
    if max_workers is None:
        max_workers = max(1, cpu_count() - 1)  # 留一个核心给系统用

    # 对于高DPI，调整批次大小以减少内存使用
    if dpi > 600 and batch_size > 3:
        suggested_batch_size = max(1, int(3 * 600 / dpi))
        batch_size = suggested_batch_size
        print(f"对于 {dpi} DPI，自动调整批次大小为 {batch_size} 页以优化内存使用")

    print(f"使用 {max_workers} 个进程处理，每批 {batch_size} 页")

    # 准备批次参数
    batches = []
    for i in range(0, total_pages, batch_size):
        batch_output = os.path.join(temp_dir, f"batch_{i}.pdf")
        batches.append((input_path, i, min(i + batch_size, total_pages), dpi, batch_output))

    # 并行处理批次
    batch_pdfs = []
    with Pool(processes=max_workers) as pool:
        # 使用tqdm显示处理进度
        for batch_pdf in tqdm(pool.imap(process_batch, batches),
                             total=len(batches),
                             desc="处理页面",
                             unit="批"):
            batch_pdfs.append(batch_pdf)

    # 合并所有批次PDF
    print("正在合并批次...")
    doc_output = fitz.open()
    for batch_pdf in tqdm(batch_pdfs, desc="合并PDF"):
        doc_batch = fitz.open(batch_pdf)
        doc_output.insert_pdf(doc_batch)
        doc_batch.close()
        # 定期进行垃圾回收
        gc.collect()

    # 保存最终输出PDF
    print(f"正在保存输出PDF: {output_path}")
    doc_output.save(output_path, garbage=4, deflate=True)  # 优化PDF大小
    doc_output.close()

    # 清理临时文件
    print("清理临时文件...")
    for batch_pdf in batch_pdfs:
        try:
            os.remove(batch_pdf)
        except Exception as e:
            print(f"无法删除临时文件 {batch_pdf}: {e}")
    try:
        os.rmdir(temp_dir)
    except Exception as e:
        print(f"无法删除临时目录 {temp_dir}: {e}")

    # 计算总耗时和输出文件大小
    elapsed_time = time.time() - start_time
    minutes, seconds = divmod(elapsed_time, 60)
    output_size_mb = os.path.getsize(output_path) / (1024 * 1024)

    print(f"转换完成! 灰度PDF已保存至: {output_path}")
    print(f"输出文件大小: {output_size_mb:.2f} MB")
    print(f"总耗时: {int(minutes)}分{int(seconds)}秒")


# 使用示例
if __name__ == "__main__":
    input_pdf = r"C:\Users\PDF.pdf"
    output_pdf = r"C:\Users\PDF【灰色】.pdf"

    convert_pdf_to_grayscale(
        input_path=input_pdf,
        output_path=output_pdf,
        dpi=1200,         # 高质量
        batch_size=10,     # 每批2页，高DPI时减少批次大小以控制内存使用
        max_workers=8     # 使用4个进程
    )