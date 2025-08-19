import shutil
import matplotlib.pyplot as plt
import re # 导入正则表达式模块
from PIL import Image, ImageChops, ImageColor # 导入 Pillow 库用于图像处理
import os # 导入 os 模块用于文件路径操作和临时文件管理
import uuid # 导入 uuid 模块生成唯一文件名，避免冲突

# Matplotlib 全局配置 (可选)
plt.rcParams['font.family'] = ['NotoSansCJK-Regular']  # 例如：设置为黑体，以支持中文显示
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示为方块的问题
plt.rcParams['mathtext.fontset'] = 'cm'

def split_latex_into_lines(latex_input, delimiter=','):
    """
    将输入的 LaTeX 字符串按指定的分隔符分割成多个独立的 LaTeX 行。
    分隔符 (如逗号) 会被保留在前一行的末尾。
    """
    if not latex_input.strip():
        return [] # 如果输入为空，返回空列表
    
    lines_final = []
    # 使用正则表达式分割，保留分隔符。f'({re.escape(delimiter)})' 会捕获分隔符。
    raw_parts = re.split(f'({re.escape(delimiter)})', latex_input)
    
    current_segment = ""
    for part_idx, p in enumerate(raw_parts):
        if not p: # re.split 可能会产生空字符串，跳过它们
            continue

        if p == delimiter: # 如果当前部分是分隔符
            current_segment += p # 将分隔符添加到当前段的末尾
            stripped_segment = current_segment.strip()
            if stripped_segment: # 确保 strip 后有内容
                 lines_final.append(stripped_segment)
            current_segment = "" # 开始新的段
        else: # 如果当前部分不是分隔符
            current_segment += p
        
        # 处理最后一部分
        if part_idx == len(raw_parts) - 1 and current_segment.strip():
            lines_final.append(current_segment.strip())
            
    # 如果 lines_final 为空但原始输入不为空（例如输入就是 ",")
    if not lines_final and latex_input.strip() == delimiter:
        return [delimiter]
    if not lines_final and latex_input.strip(): # 对于其他非空但未产生行的输入
        return [latex_input.strip()]

    return lines_final

def get_precise_ink_bbox(img, background_color_str):
    """
    通过像素扫描精确计算非背景像素的边界框。
    返回 (min_x, min_y, max_x_exclusive, max_y_exclusive) 或 None。
    """
    is_transparent_bg = (background_color_str.lower() == 'none')
    
    img_to_scan = img.convert('RGBA') # 始终使用RGBA进行扫描以便统一处理alpha和颜色
    pixels = img_to_scan.load()
    width, height = img_to_scan.size

    min_x, min_y, max_x, max_y = width, height, -1, -1 # 初始化边界
    found_ink = False

    if is_transparent_bg:
        # 对于透明背景，如果alpha > 0 则视为"ink"
        for y_ax in range(height):
            for x_ax in range(width):
                if pixels[x_ax, y_ax][3] > 0: # Alpha > 0
                    if x_ax < min_x: min_x = x_ax
                    if y_ax < min_y: min_y = y_ax
                    if x_ax > max_x: max_x = x_ax
                    if y_ax > max_y: max_y = y_ax
                    found_ink = True
    else:
        # 对于纯色背景
        try:
            background_rgba_for_scan = ImageColor.getcolor(background_color_str, 'RGBA')
        except ValueError: # 如果颜色字符串无效，默认为白色不透明
            background_rgba_for_scan = (255, 255, 255, 255)
            
        for y_ax in range(height):
            for x_ax in range(width):
                if pixels[x_ax, y_ax] != background_rgba_for_scan:
                    if x_ax < min_x: min_x = x_ax
                    if y_ax < min_y: min_y = y_ax
                    if x_ax > max_x: max_x = x_ax
                    if y_ax > max_y: max_y = y_ax
                    found_ink = True
    
    if not found_ink: 
        return None # 如果没有找到墨迹，返回None
    
    # 返回的bbox是 (left, upper, right, lower)，其中right和lower是超出墨迹1像素的位置
    return (min_x, min_y, max_x + 1, max_y + 1)


def auto_crop_image(image_path, background_color_str='white', padding=0):
    """
    自动裁剪图片的空白边缘，使用精确的像素扫描。
    """
    try:
        img = Image.open(image_path)
        
        bbox = get_precise_ink_bbox(img, background_color_str)

        if bbox: 
            # print(f"  精确bbox找到: {bbox} for {image_path}") # 调试信息
            img_cropped = img.crop(bbox)

            if padding > 0:
                current_mode = img_cropped.mode if img_cropped.mode in ['RGB', 'RGBA', 'L'] else 'RGBA'
                if background_color_str.lower() == 'none' and current_mode == 'RGBA':
                    padded_bg_color = (0,0,0,0)
                else:
                    try: padded_bg_color = ImageColor.getcolor(background_color_str, current_mode)
                    except ValueError: 
                        rgb_color_pad = ImageColor.getrgb(background_color_str)
                        if current_mode == 'RGBA':
                            padded_bg_color = (*rgb_color_pad, 255) if background_color_str.lower() != 'none' else (*rgb_color_pad, 0)
                        else:
                            padded_bg_color = rgb_color_pad
                
                new_width = max(1, img_cropped.width + 2 * padding)
                new_height = max(1, img_cropped.height + 2 * padding)
                padded_img = Image.new(current_mode, (new_width, new_height), padded_bg_color)
                padded_img.paste(img_cropped, (padding, padding))
                img_to_save = padded_img
            else: # 无填充
                img_to_save = img_cropped
            
            # 确保保存的图像至少有1x1像素
            if img_to_save.width == 0 or img_to_save.height == 0:
                # print(f"  警告: 裁剪后图像尺寸为零 {image_path}。调整为1x1。")
                _1x1_mode_save = img_to_save.mode if img_to_save.mode in ['RGB', 'RGBA', 'L'] else 'RGBA'
                _1x1_fill_save = (0,0,0,0) if _1x1_mode_save == 'RGBA' and background_color_str.lower() == 'none' else ImageColor.getcolor(background_color_str, _1x1_mode_save)
                img_to_save = Image.new(_1x1_mode_save, (1,1), _1x1_fill_save)

            img_to_save.save(image_path)
        else: # bbox is None, 图像被视为空白
            # print(f"  图像 {image_path} 被视为空白。裁剪为1x1。")
            _1x1_mode = img.mode if img.mode in ['RGB', 'RGBA', 'L'] else 'RGBA'
            if background_color_str.lower() == 'none':
                _1x1_fill = (0,0,0,0) 
                _1x1_mode = 'RGBA' 
            else:
                try: _1x1_fill = ImageColor.getcolor(background_color_str, _1x1_mode)
                except ValueError: 
                     _1x1_mode = 'RGB' 
                     _1x1_fill = ImageColor.getrgb(background_color_str)
            img_1x1 = Image.new(_1x1_mode, (1, 1), _1x1_fill)
            img_1x1.save(image_path)
        
        return True
    except FileNotFoundError:
        print(f"  自动裁剪错误: 文件 {image_path} 未找到。")
        return False
    except Exception as e:
        print(f"  自动裁剪图片 {image_path} 时发生错误 ({type(e).__name__}: {e})")
        return False


def render_single_latex_line(latex_line_string,
                             output_filename, 
                             delimiter_char, 
                             dpi=300,
                             fontsize=15,
                             bgcolor='white',
                             fgcolor='black',
                             autocrop_padding=0,
                             max_delimiter_line_height=2):
    """
    将单行 LaTeX 字符串渲染为图片，并进行自动裁剪。
    如果行内容仅仅是分隔符，则使用更小的字体和figsize渲染，并强制其高度。
    """
    stripped_line = latex_line_string.strip()
    
    current_figsize = (1, 1) # 默认figsize用于普通内容
    effective_fontsize = fontsize
    is_delimiter_line = (stripped_line == delimiter_char)

    if not stripped_line: 
        current_figsize = (0.01, 0.01) # 空行使用极小figsize
        final_latex_string = r"$" # 一个空的数学表达式，避免渲染错误
    elif is_delimiter_line:
        current_figsize = (0.05, 0.05) # 分隔符行使用极小figsize
        effective_fontsize = 1         # 分隔符字体设为最小
        final_latex_string = rf"${stripped_line}$"
    else: # 普通内容行
        final_latex_string = rf"${stripped_line}$"

    fig, ax = plt.subplots(figsize=current_figsize, facecolor=bgcolor) 
    ax.axis('off')

    try:
        if stripped_line: # 只对非空行渲染文本
            ax.text(0, 0, final_latex_string, fontsize=effective_fontsize, color=fgcolor, va='baseline', ha='left')
        
        # pad_inches=0 使得Matplotlib进行最紧密的裁剪
        plt.savefig(output_filename, dpi=dpi, bbox_inches='tight', pad_inches=0, facecolor=fig.get_facecolor(), transparent=(bgcolor.lower()=='none'))
        plt.close(fig) # 在Pillow操作前关闭Matplotlib的figure

        # 使用Pillow进行二次精细裁剪
        if not auto_crop_image(output_filename, bgcolor, padding=autocrop_padding):
            print(f"  警告: 自动裁剪图片 {output_filename} 失败，但仍继续。")
        
        # 如果是分隔符行，并且其高度在裁剪后仍然过大，则强制调整高度
        if is_delimiter_line and os.path.exists(output_filename):
            try:
                img_check = Image.open(output_filename)
                if img_check.height > max_delimiter_line_height:
                    # print(f"    分隔符行 '{stripped_line}' 高度 {img_check.height} > {max_delimiter_line_height}。强制调整高度。")
                    new_height = max(1, max_delimiter_line_height)
                    new_width = max(1, img_check.width) # 确保宽度也至少为1
                    # 使用 Image.Resampling.LANCZOS for Pillow >= 9.0.0
                    resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                    img_resized = img_check.resize((new_width, new_height), resample_filter)
                    img_resized.save(output_filename)
            except Exception as e_resize:
                print(f"    调整分隔符行图片高度时出错 {output_filename}: {e_resize}")
        return True 
    except RuntimeError as e: # Matplotlib 渲染错误
        if 'fig' in locals() and fig.canvas.manager is not None : plt.close(fig) 
        print(f"  渲染单行 LaTeX 时发生运行时错误: {e} (内容: {final_latex_string})")
        fig_err, ax_err = plt.subplots(figsize=(5, 1), facecolor='lightyellow')
        error_text = f"渲染错误: {str(e)[:50]}..."
        ax_err.text(0.05, 0.5, error_text, ha='left', va='center', fontsize=8, color='red', wrap=True)
        ax_err.axis('off')
        plt.savefig(output_filename, dpi=100, facecolor=fig_err.get_facecolor())
        plt.close(fig_err)
        return False
    except Exception as e: # 其他一般错误
        if 'fig' in locals() and fig.canvas.manager is not None : plt.close(fig)
        print(f"  渲染或保存单行图片时发生未知错误: {e} (内容: {final_latex_string})")
        return False


def stitch_images_vertically(image_paths, output_filename="stitched_latex.png", bgcolor_fill='white', line_spacing=0):
    """
    将多张图片垂直拼接成一张，并在图片间添加指定的行间距。
    """
    if not image_paths:
        print("没有图片路径可供拼接。")
        return

    images = []
    for path in image_paths:
        try:
            img = Image.open(path)
            w, h = img.size
            if w == 0 or h == 0: # 如果图像尺寸为0，尝试创建一个最小的占位符
                # print(f"  警告: 图片 {path} 尺寸为零 ({w}x{h})。调整为1x1。")
                _mode = img.mode if img.mode in ['RGB', 'RGBA', 'L'] else 'RGB'
                try:
                    _fill = (0,0,0,0) if _mode == 'RGBA' and bgcolor_fill.lower() == 'none' else ImageColor.getcolor(bgcolor_fill, _mode)
                except: # Fallback fill color if getcolor fails (e.g. for 'L' mode with complex color string)
                    _fill = 0 if _mode == 'L' else ( (0,0,0) if _mode == 'RGB' else (0,0,0,0) )

                img = Image.new(_mode, (max(1,w),max(1,h)), _fill) # 确保至少1x1
            images.append(img)
        except FileNotFoundError: print(f"  警告: 图片文件未找到 {path}, 跳过。")
        except Exception as e: print(f"  警告: 打开图片 {path} 时出错 ({type(e).__name__}: {e}), 跳过。")
    
    if not images:
        print("没有成功加载任何图片进行拼接。")
        try: 
            temp_fig, temp_ax = plt.subplots(figsize=(3,1))
            temp_ax.text(0.5, 0.5, "无内容可拼接", ha='center', va='center', fontsize=12)
            temp_ax.axis('off')
            temp_fig.savefig(output_filename, dpi=100)
            plt.close(temp_fig)
            print(f"已生成提示图片: {output_filename}")
        except Exception as e_save_empty: print(f"创建空拼接提示图失败: {e_save_empty}")
        return

    max_width = max((img.width for img in images if img), default=1)
    
    if len(images) > 1:
        total_height = sum(img.height for img in images if img) + (len(images) - 1) * line_spacing
    else:
        total_height = sum(img.height for img in images if img)

    max_width = max(1, max_width) 
    total_height = max(1, total_height) 

    is_any_rgba = any(img.mode == 'RGBA' for img in images if img)
    final_mode = 'RGBA' if is_any_rgba or (isinstance(bgcolor_fill, str) and bgcolor_fill.lower() == 'none') else 'RGB'
    
    if isinstance(bgcolor_fill, str) and bgcolor_fill.lower() == 'none':
        effective_bgcolor = (0, 0, 0, 0) 
        if final_mode == 'RGB': effective_bgcolor = (255, 255, 255)
    elif isinstance(bgcolor_fill, str):
        try: effective_bgcolor = ImageColor.getcolor(bgcolor_fill, final_mode)
        except ValueError:
            rgb_color = ImageColor.getrgb(bgcolor_fill)
            if final_mode == 'RGBA': effective_bgcolor = (*rgb_color, 255) if bgcolor_fill.lower() != 'none' else (*rgb_color, 0)
            else: effective_bgcolor = rgb_color
    else: effective_bgcolor = bgcolor_fill

    stitched_image = Image.new(final_mode, (max_width, total_height), effective_bgcolor)
    current_y = 0
    for i, img in enumerate(images): 
        if not img: continue
        img_to_paste = img
        if img.mode != final_mode: 
            if final_mode == 'RGBA': img_to_paste = img.convert('RGBA')
            elif final_mode == 'RGB' and img.mode == 'RGBA':
                fill_rgb = effective_bgcolor[:3] if isinstance(effective_bgcolor, tuple) and len(effective_bgcolor) == 4 else (255,255,255)
                temp_rgb_img = Image.new('RGB', img.size, fill_rgb)
                temp_rgb_img.paste(img, (0,0), mask=img.split()[-1] if len(img.split()) == 4 else None)
                img_to_paste = temp_rgb_img
            else: img_to_paste = img.convert(final_mode)
        
        x_offset = 0 
        stitched_image.paste(img_to_paste, (x_offset, current_y))
        current_y += img_to_paste.height
        if i < len(images) - 1: 
            current_y += line_spacing

    try:
        stitched_image.save(output_filename)
        print(f"所有图片已成功拼接并保存至 {output_filename}")
    except Exception as e:
        print(f"保存拼接图片时出错: {e}")


def process_and_render_latex(full_latex_input,
                             output_filename="final_latex_output.png",
                             delimiter=',',
                             dpi=300,
                             fontsize=15,
                             bgcolor='white', 
                             fgcolor='black',
                             autocrop_padding=0, 
                             max_delimiter_line_height=2, 
                             cleanup_temp_files=True,
                             stitch_line_spacing=0): 
    """
    总处理函数：分割 LaTeX，分别渲染，自动裁剪，然后拼接。
    """
    print(f"开始处理 LaTeX 输入: \"{full_latex_input}\"")
    latex_lines = split_latex_into_lines(full_latex_input, delimiter)

    if not latex_lines:
        print("没有有效的 LaTeX 行可供渲染。")
        try: 
            fig, ax = plt.subplots(figsize=(3,1), facecolor=bgcolor)
            ax.text(0.5, 0.5, "输入内容为空或无法解析", ha='center', va='center', fontsize=12, color=fgcolor)
            ax.axis('off')
            fig.savefig(output_filename, dpi=100, facecolor=fig.get_facecolor())
            plt.close(fig)
            print(f"已生成空内容提示图片: {output_filename}")
        except Exception as e_save_empty: print(f"创建空内容提示图失败: {e_save_empty}")
        return

    temp_image_paths = []
    # 确保临时目录是唯一的，以防并行处理（尽管当前是单线程）
    temp_run_id = uuid.uuid4().hex[:8]
    temp_dir_base = "temp_latex_renders"
    # 确保 temp_dir_base 存在，如果不存在，则创建
    if not os.path.exists(temp_dir_base):
        try:
            os.makedirs(temp_dir_base, exist_ok=True)
        except OSError as e:
            print(f"创建基础临时目录 {temp_dir_base} 失败: {e}. 将在当前目录创建临时文件。")
            temp_dir_base = "." # 退回到当前目录
            
    temp_dir = os.path.join(temp_dir_base, temp_run_id) # 每个渲染过程使用独立的子目录
    if not os.path.exists(temp_dir):
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except OSError as e:
            print(f"创建独立临时目录 {temp_dir} 失败: {e}. 将在基础临时目录创建。")
            temp_dir = temp_dir_base


    print("开始逐行渲染 LaTeX 片段...")
    all_renders_successful = True
    for i, line_latex in enumerate(latex_lines):
        temp_filename_base = f"line_{i}.png" # 简化文件名，因为目录已经是唯一的了
        temp_filename = os.path.join(temp_dir, temp_filename_base)
        
        success = render_single_latex_line(line_latex, temp_filename, delimiter, dpi, fontsize, bgcolor, fgcolor, autocrop_padding, max_delimiter_line_height)
        if success:
            if os.path.exists(temp_filename): 
                temp_image_paths.append(temp_filename)
            else:
                print(f"  警告: 渲染声称成功但文件 {temp_filename} 未找到。")
                all_renders_successful = False 
        else:
            all_renders_successful = False
            print(f"  警告: 行 \"{line_latex}\" 渲染失败或裁剪失败。")
            if os.path.exists(temp_filename): 
                 temp_image_paths.append(temp_filename) 


    if not temp_image_paths:
        print("没有成功渲染或生成任何 LaTeX 行的图片。")
        if cleanup_temp_files and temp_dir != "." and os.path.exists(temp_dir): 
            try:
                shutil.rmtree(temp_dir) # 清理独立的运行子目录
            except OSError as e: print(f"清理独立临时目录 {temp_dir} 失败: {e}")
        return

    print("\n开始拼接渲染好的图片...")
    stitch_images_vertically(temp_image_paths, output_filename, bgcolor_fill=bgcolor, line_spacing=stitch_line_spacing)

    if cleanup_temp_files: 
        print("清理临时渲染文件...")
        # 现在清理整个独立的运行子目录
        if temp_dir != "." and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                # print(f"  独立临时目录 {temp_dir} 已成功删除。")
            except Exception as e: 
                print(f"  删除独立临时目录 {temp_dir} 失败: {e}")
    
    if not all_renders_successful:
        print("\n注意: 部分 LaTeX 行渲染或裁剪失败，最终图片中可能包含错误提示。")
    print(f"处理完成。最终图片保存在: {output_filename}")

# --- 主程序和演示 (用于独立测试 latex_renderer.py) ---
if __name__ == "__main__":
    # 创建一个输出目录用于测试
    if not os.path.exists("test_outputs"):
        os.makedirs("test_outputs")

    test_cases = [
        (r"f(x) = \sin x \cos x + 2 = \frac{1}{2} \sin 2x + 2, T = \frac{2\pi}{2} = \pi", "test_outputs/demo_1.png", {"fontsize": 20, "stitch_line_spacing": 5}),
        (r"E = mc^2, F = ma, P = IV, V = IR", "test_outputs/demo_2.png", {"fontsize": 18, "bgcolor": 'lightyellow', "stitch_line_spacing": 0}),
        (r"\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}", "test_outputs/demo_3.png", {"fgcolor": 'darkblue', "bgcolor": 'none', "stitch_line_spacing": 3}),
        (r"", "test_outputs/demo_4_empty.png", {}),
        (r"a+b=c; d-e=f; g \times h = i", "test_outputs/demo_5_semicolon.png", {"delimiter": ';', "fontsize": 22, "stitch_line_spacing": 8}),
        (r"\sum_{k=0}^{n} \binom{n}{k} x^{k} y^{n-k} = (x+y)^n", "test_outputs/demo_6_sum.png", {"fontsize": 20}),
        (r"A=1,,B=2,,C=3", "test_outputs/demo_8_double_comma.png", {"fontsize": 20, "delimiter": ',', "max_delimiter_line_height": 1, "stitch_line_spacing": 0}),
        (r",", "test_outputs/demo_9_only_comma.png", {"fontsize": 20, "delimiter": ',', "max_delimiter_line_height": 1, "stitch_line_spacing": 0}),
        (r"X=Y,", "test_outputs/demo_10_ends_comma.png", {"fontsize": 20, "delimiter": ',', "max_delimiter_line_height": 2, "stitch_line_spacing": 5}),
        (r"\alpha, \beta, \gamma", "test_outputs/demo_11_small_font.png", {"fontsize": 10, "delimiter": ',', "max_delimiter_line_height": 1, "stitch_line_spacing": 0}),
        (r"\text{Line 1 has some text}, \text{Line 2 also}, \text{And Line 3}", "test_outputs/demo_12_text.png", {"fontsize": 18, "delimiter": ',', "max_delimiter_line_height": 2, "stitch_line_spacing": 5}),
        (r"\int_0^\pi \sin(x) dx = [-\cos(x)]_0^\pi, = (-\cos(\pi)) - (-\cos(0)), = (-(-1)) - (-1), = 1+1=2", "test_outputs/demo_13_integral_multiline.png", {"fontsize":18, "stitch_line_spacing": 5})
    ]

    for latex_str, out_file, params in test_cases:
        print(f"\n--- 测试: {latex_str[:50]}... ---")
        # 合并默认参数和测试用例特定参数
        current_params = {
            "delimiter": params.get("delimiter", ","),
            "dpi": params.get("dpi", 300),
            "fontsize": params.get("fontsize", 15),
            "bgcolor": params.get("bgcolor", "white"),
            "fgcolor": params.get("fgcolor", "black"),
            "autocrop_padding": params.get("autocrop_padding", 0),
            "max_delimiter_line_height": params.get("max_delimiter_line_height", 2),
            "cleanup_temp_files": True, # 测试时可以设为False方便查看中间文件
            "stitch_line_spacing": params.get("stitch_line_spacing", 0)
        }
        process_and_render_latex(latex_str, out_file, **current_params)

    print("\n--- 所有独立测试完成 ---")

