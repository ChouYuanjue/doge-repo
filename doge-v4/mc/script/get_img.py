from PIL import Image, ImageDraw, ImageFont
import asyncio
import io
from pathlib import Path
import base64
from typing import Optional

async def load_font(font_size):
    # 尝试多路径加载
    font_paths = [
        Path(__file__).resolve().parent.parent/'resource'/'msyh.ttf',
        'msyh.ttf',  # 当前目录
        '/usr/share/fonts/zh_CN/msyh.ttf',  # Linux常见路径
        'C:/Windows/Fonts/msyh.ttc',  # Windows路径
        '/System/Library/Fonts/Supplemental/Songti.ttc'  # macOS路径
    ]
    
    for path in font_paths:
        try:
            return ImageFont.truetype(path, font_size)
        except OSError:
            continue
    
    # 全部失败时使用默认字体（添加中文支持）
    try:
        # 尝试加载PIL的默认中文字体
        return ImageFont.load_default().font_variant(size=font_size)
    except:
        return ImageFont.load_default()

# 在代码中替换字体加载部分
title_font = load_font(30)
text_font = load_font(20)
small_font = load_font(18)

async def fetch_icon(icon_base64: Optional[str] = None) -> Optional[Image.Image]:
    """处理Base64编码的服务器图标"""
    if not icon_base64:
        return None
    
    try:
        # 去除可能的Base64前缀
        if "," in icon_base64:
            icon_base64 = icon_base64.split(",", 1)[1]
        icon_data = base64.b64decode(icon_base64)
        return Image.open(io.BytesIO(icon_data)).convert("RGBA")
    except Exception as e:
        print(f"Base64图标解码失败: {str(e)}")
        return None

async def generate_server_info_image(
    players_list: list,
    latency: int,
    server_name: str,
    plays_max: int,
    plays_online: int,
    server_version: str,
    icon_base64: Optional[str] = None
) -> str:
    """生成服务器信息图片并返回base64编码"""
    
    # 异步获取图标
    server_icon = await fetch_icon(icon_base64)
    
    # 配置参数
    BG_COLOR = (34, 34, 34)
    TEXT_COLOR = (255, 255, 255)
    ACCENT_COLOR = (85, 255, 85)
    WARNING_COLOR = (255, 170, 0)
    ERROR_COLOR = (255, 85, 85)
    
    # 字体配置
    try:
        title_font = await load_font(30)
        text_font = await load_font(20)
        small_font = await load_font(18)
    except IOError:
        title_font = ImageFont.load_default(30)
        text_font = ImageFont.load_default(20)
        small_font = ImageFont.load_default(18)
    
    # 计算布局参数
    icon_size = 64 if server_icon else 0
    base_y = 20
    text_x = 20 + icon_size + 20
    
    # 自动计算图片高度
    line_height = 30
    player_lines = (len(players_list) // 4) + 1
    img_height = 180 + (player_lines * line_height) + (20 if server_icon else 0)
    
    # 创建画布
    img = Image.new("RGB", (600, img_height), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 绘制服务器图标
    if server_icon:
        icon_mask = Image.new("L", (64, 64), 0)
        mask_draw = ImageDraw.Draw(icon_mask)
        mask_draw.rounded_rectangle((0, 0, 64, 64), radius=10, fill=255)
        server_icon.thumbnail((64, 64))
        img.paste(server_icon, (20, base_y), icon_mask)
    
    # 服务器信息绘制（保持原有绘制逻辑不变）
    draw.text((text_x, base_y), server_name, font=title_font, fill=ACCENT_COLOR)
    base_y += 40
    
    version_text = f"版本: {server_version}"
    latency_color = ACCENT_COLOR if latency < 100 else WARNING_COLOR if latency < 200 else ERROR_COLOR
    latency_text = f"延迟: {latency}ms"
    
    draw.text((text_x, base_y), version_text, font=text_font, fill=TEXT_COLOR)
    draw.text((400, base_y), latency_text, font=text_font, fill=latency_color)
    base_y += 40
    
    online_text = f"在线玩家 ({plays_online}/{plays_max})"
    draw.text((text_x, base_y), online_text, font=text_font, fill=ACCENT_COLOR)
    base_y += 40
    
    if players_list:
        chunks = [players_list[i:i+4] for i in range(0, len(players_list), 4)]
        for chunk in chunks:
            players_line = " • ".join(chunk)
            draw.text((text_x + 20, base_y), players_line, font=small_font, fill=TEXT_COLOR)
            base_y += line_height
    else:
        draw.text((text_x + 20, base_y), "暂无玩家在线", font=small_font, fill=TEXT_COLOR)
        base_y += line_height
    
    draw.rounded_rectangle([10, 10, img.width-10, img.height-10], radius=10, outline=ACCENT_COLOR, width=2)
    
    # 转换为base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # 返回base64 bytes
    return img_base64
