import fitz  # PyMuPDF
import numpy as np
from PIL import Image
import io
import os

# ===========================================
# 直接在这里设置参数
# ===========================================
# 输入PDF文件路径
input_path = r"C:\Users\gutia\OneDrive\03_考研Anki卡包\03 【Anki Studio】 26考研\02 考研政治\02 时政\02_徐涛每月时政\processed\徐涛三月时政【灰色】.pdf"

# 输出PDF文件路径 (设置为None则自动添加"_nowatermark"后缀)
output_path = None

# 水印的颜色值 (RGB格式)
# 例如:
# - 浅灰色: [200, 200, 200]
# - 浅蓝色: [173, 216, 230]
# - 浅红色: [255, 182, 193]
watermark_color = [226, 223, 223]

# 颜色匹配敏感度 - 值越高，匹配的颜色范围越广
# 建议范围: 10-50，根据水印颜色的独特性调整
sensitivity = 20

# ===========================================
# 高质量设置
# ===========================================
# 渲染分辨率因子 (值越高质量越好，但处理越慢)
# 值范围建议：2-6，一般情况下3-4就能获得很好的效果
resolution_factor = 4

# 图像质量 (1-100，仅对JPG格式有效，值越高质量越好但文件越大)
image_quality = 95

# 图像格式 ("png" 或 "jpg"，png无损但文件大，jpg有损但文件小)
image_format = "png"

# 是否应用锐化以提高清晰度（True/False）
apply_sharpening = True

# 锐化强度 (0.0-2.0)
sharpening_strength = 1.0


# ===========================================

def remove_watermark_from_pdf(input_path, output_path, color_lower, color_upper, sensitivity=20):
    """
    从PDF中去除基于颜色阈值的水印，保持高清晰度

    参数:
        input_path: 输入PDF文件路径
        output_path: 输出PDF文件路径
        color_lower: 水印颜色的下阈值 (RGB元组)
        color_upper: 水印颜色的上阈值 (RGB元组)
        sensitivity: 颜色匹配的敏感度 (值越低越精确)
    """
    print(f"正在处理文件: {input_path}")

    # 打开PDF文件
    pdf_document = fitz.open(input_path)
    output_document = fitz.open()

    total_pages = len(pdf_document)

    for page_num in range(total_pages):
        print(f"处理第 {page_num + 1}/{total_pages} 页...")

        # 获取当前页面
        page = pdf_document[page_num]

        # 将页面渲染为高分辨率图像
        matrix = fitz.Matrix(resolution_factor, resolution_factor)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # 确定图像格式
        format_ext = image_format.lower()
        img_bytes = pix.tobytes(format_ext)

        # 将图像转换为PIL Image对象
        img = Image.open(io.BytesIO(img_bytes))
        img_array = np.array(img)

        # 创建水印掩码 - 检测在颜色阈值范围内的像素
        mask = np.zeros(img_array.shape[:2], dtype=bool)

        for i in range(3):  # 对RGB三个通道分别处理
            mask = mask | ((img_array[:, :, i] >= color_lower[i] - sensitivity) &
                           (img_array[:, :, i] <= color_upper[i] + sensitivity))

        # 识别并替换水印像素
        # 对掩码区域使用背景色填充（这里使用白色）
        for i in range(3):
            img_array[:, :, i][mask] = 255

        # 将处理后的图像转换回PIL图像
        processed_img = Image.fromarray(img_array)

        # 可选：应用锐化以提高清晰度
        if apply_sharpening:
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Sharpness(processed_img)
            processed_img = enhancer.enhance(sharpening_strength)

        # 将处理后的图像转回PDF页面，使用高质量设置
        img_bytes = io.BytesIO()
        if image_format.lower() == "jpg":
            processed_img.save(img_bytes, format="JPEG", quality=image_quality, optimize=True)
        else:  # PNG
            processed_img.save(img_bytes, format="PNG", optimize=True)
        img_bytes.seek(0)

        # 创建新页面并插入处理后的图像
        new_page = output_document.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img_bytes)

    # 保存处理后的PDF，使用无损压缩
    output_document.save(output_path, garbage=4, deflate=True, clean=True)
    output_document.close()
    pdf_document.close()

    print(f"处理完成! 已保存到: {output_path}")
    print(f"使用了 {resolution_factor}x 分辨率因子和 {image_format.upper()} 格式")


def main():
    global input_path, output_path, watermark_color, sensitivity

    # 验证输入路径
    if not os.path.exists(input_path):
        print(f"错误: 找不到输入文件 '{input_path}'")
        return

    # 处理输出路径
    if output_path is None:
        filename, ext = os.path.splitext(input_path)
        output_path = f"{filename}_nowatermark{ext}"

    # 创建颜色阈值范围
    color_lower = [max(0, c - sensitivity) for c in watermark_color]
    color_upper = [min(255, c + sensitivity) for c in watermark_color]

    # 开始处理
    remove_watermark_from_pdf(input_path, output_path, color_lower, color_upper, sensitivity)


if __name__ == "__main__":
    main()