# main.py
import io
import os
import re
import math
import tempfile
import asyncio
from typing import List, Tuple, Dict

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cairosvg
import imageio
import cv2

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

@register("fourier", "runnel", "将 SVG / 文本 转为傅里叶级数动图（显示旋转向量）", "1.1.0", "repo")
class FourierPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_mode: Dict[str, str] = {}

    @filter.command_group("fourier")
    def fourier_group(self):
        """fourier 指令组: svg / text / mode"""
        pass

    # 配置
    MAX_CHARS = 10           # text 模式最大字符数
    CANVAS_SIZE = 800       # 输出帧大小（px）
    SAMPLE_POINTS = 2048    # 重采样点数（总体或分配）
    NUM_VECTORS = 80        # 每条路径使用的向量数（merge 模式是总数；separate 可按路径分配）
    FRAMES = 220            # 动图帧数
    DURATION_MS = 20        # GIF 每帧 ms
    MIN_CONTOUR_AREA_RATIO = 0.003  # 轮廓面积阈（占图像面积的比例）
    MERGE_TRANSITION_POINTS = 12     # 不同轮廓间插入的过渡点数量（merge 模式）
   
    @fourier_group.command("mode")
    async def fourier_mode(self, event: AstrMessageEvent):
        """
        /fourier mode <merge|separate>
        设置处理模式（分用户保存）
        """
        msg = (event.message_str or "").strip()
        parts = msg.split(" ", 2)
        user_key = self._get_user_key(event)
        if len(parts) < 3:
            # show current
            mode = self.user_mode.get(user_key, "merge")
            yield event.plain_result(f"当前模式: {mode}（可用: merge, separate）。使用 /fourier mode <merge|separate> 切换。")
            return

        arg = parts[2].strip().lower()
        if arg not in ("merge", "separate"):
            yield event.plain_result("无效模式。可用: merge, separate。示例: /fourier mode merge")
            return

        self.user_mode[user_key] = arg
        yield event.plain_result(f"已设置模式为: {arg}")

   
    @fourier_group.command("svg")
    async def fourier_svg(self, event: AstrMessageEvent):
        """
        /fourier svg <svg源码>
        """
        msg = (event.message_str or "").strip()
        parts = msg.split(" ", 2)
        if len(parts) < 3 or not parts[2].strip():
            yield event.plain_result("用法: /fourier svg <SVG源码>（请在命令后粘贴完整 <svg>...</svg>）")
            return

        svg_src = parts[2].strip()
        user_key = self._get_user_key(event)
        mode = self.user_mode.get(user_key, "merge")

        loop = asyncio.get_running_loop()
        try:
            gif_path = await loop.run_in_executor(None, self._process_svg_workflow, svg_src, mode)
        except Exception as e:
            logger.error("fourier svg 处理失败", exc_info=True)
            yield event.plain_result(f"处理失败: {e}")
            return

        try:
            img_comp = Comp.Image.fromFileSystem(path=gif_path)
            yield event.chain_result([img_comp])
        finally:
            try:
                os.remove(gif_path)
            except Exception:
                pass

    @fourier_group.command("text")
    async def fourier_text(self, event: AstrMessageEvent):
        """
        /fourier text <文本>
        """
        msg = (event.message_str or "").strip()
        parts = msg.split(" ", 2)
        if len(parts) < 3 or not parts[2].strip():
            yield event.plain_result(f"用法: /fourier text <文本>（最多 {self.MAX_CHARS} 个字符）")
            return

        text = parts[2].strip()
        if len(text) > self.MAX_CHARS:
            yield event.plain_result(f"字符过多（最多 {self.MAX_CHARS} 个字符），请缩短后重试。")
            return

        user_key = self._get_user_key(event)
        mode = self.user_mode.get(user_key, "merge")

        loop = asyncio.get_running_loop()
        try:
            gif_path = await loop.run_in_executor(None, self._process_text_workflow, text, mode)
        except Exception as e:
            logger.error("fourier text 处理失败", exc_info=True)
            yield event.plain_result(f"处理失败: {e}")
            return

        try:
            img_comp = Comp.Image.fromFileSystem(path=gif_path)
            yield event.chain_result([img_comp])
        finally:
            try:
                os.remove(gif_path)
            except Exception:
                pass


    def _process_svg_workflow(self, svg_src: str, mode: str) -> str:
        #把 svg 渲染为 PNG，提取轮廓
        svg_src = self._ensure_svg_has_white_bg(svg_src)
        png_bytes = cairosvg.svg2png(bytestring=svg_src.encode("utf-8"),
                                     output_width=self.CANVAS_SIZE, output_height=self.CANVAS_SIZE)
        img = Image.open(io.BytesIO(png_bytes)).convert("L")
        contours = self._extract_contours_from_image(img)
        return self._generate_gif_from_contours(contours, mode)

    def _process_text_workflow(self, text: str, mode: str) -> str:
        #把文本渲染为图像，提取轮廓
        img = self._render_text_to_image(text, size=self.CANVAS_SIZE)
        contours = self._extract_contours_from_image(img)
        return self._generate_gif_from_contours(contours, mode)

    def _ensure_svg_has_white_bg(self, svg_src: str) -> str:
        m = re.search(r"<svg\b[^>]*>", svg_src, flags=re.IGNORECASE)
        if not m:
            return svg_src
        insert_at = m.end()
        rect = '<rect width="100%" height="100%" fill="white"/>'
        return svg_src[:insert_at] + rect + svg_src[insert_at:]

    def _render_text_to_image(self, text: str, size: int = 800) -> Image.Image:
        img = Image.new("L", (size, size), 255)
        draw = ImageDraw.Draw(img)

        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
        font = None
        for p in font_paths:
            try:
                font = ImageFont.truetype(p, size=200)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        fontsize = 240
        while fontsize >= 8:
            try:
                ftest = ImageFont.truetype(font.path, fontsize) if hasattr(font, "path") else font
            except Exception:
                ftest = font
            bbox = draw.textbbox((0, 0), text, font=ftest)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w < 0.9 * size and h < 0.9 * size:
                break
            fontsize -= 6
        try:
            used_font = ImageFont.truetype(font.path, fontsize) if hasattr(font, "path") else font
        except Exception:
            used_font = font

        bbox = draw.textbbox((0, 0), text, font=used_font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size - w) // 2 - bbox[0]
        y = (size - h) // 2 - bbox[1]
        draw.text((x, y), text, font=used_font, fill=0)
        return img

    def _extract_contours_from_image(self, img: Image.Image) -> List[np.ndarray]:
        """
        提取所有轮廓（包含内孔）：返回 list，每项为 (n,2) 的 ndarray (x,y)。
        过滤掉过小噪声并确保每个轮廓闭合。
        """
        arr = np.array(img.convert("L"))
        _, thresh = cv2.threshold(arr, 220, 255, cv2.THRESH_BINARY_INV)

        res = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        if len(res) == 3:
            _, contours, hierarchy = res
        else:
            contours, hierarchy = res

        if not contours:
            raise RuntimeError("未能从图像中提取轮廓（请确保输入含可见的路径/文字）")

        H, W = thresh.shape
        min_area = max(10.0, self.MIN_CONTOUR_AREA_RATIO * W * H)

        pieces: List[np.ndarray] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            pts = c[:, 0, :].astype(np.float64)
            
            if not (pts[0] == pts[-1]).all():
                pts = np.vstack([pts, pts[0]])
            pieces.append(pts)

        if not pieces:
            raise RuntimeError("轮廓均被判定为噪声，请放大字体或降低 MIN_CONTOUR_AREA_RATIO 阈值")

        # 按质心排序（左->右，上->下）
        centroids = [ (p[:,0].mean(), p[:,1].mean()) for p in pieces ]
        order = sorted(range(len(pieces)), key=lambda i: (centroids[i][0], centroids[i][1]))
        pieces = [pieces[i] for i in order]
        return pieces

    # 傅里叶绘制（感谢ChatGPT）
    def _merge_contours_to_path(self, contours: List[np.ndarray], transition_points: int = 12) -> np.ndarray:
        """
        最近邻拼接所有轮廓为一条连续路径，并在轮廓间插入若干线性过渡点以减少跳跃
        返回 (M,2) ndarray
        """
        # 先求每个轮廓的起点（左上最靠前点）或质心作为代表
        reps = []
        for pts in contours:
            cx = pts[:,0].mean()
            cy = pts[:,1].mean()
            reps.append((cx, cy))
        used = [False]*len(contours)
        # 从最左边的轮廓开始
        cur_idx = min(range(len(reps)), key=lambda i: reps[i][0])
        order = []
        while len(order) < len(contours):
            order.append(cur_idx)
            used[cur_idx] = True
            # 进到下一个最近的未用轮廓（按质心距离）
            dists = [ math.hypot(reps[i][0]-reps[cur_idx][0], reps[i][1]-reps[cur_idx][1]) if not used[i] else float('inf') for i in range(len(reps)) ]
            cur_idx = int(np.argmin(dists))

        # 拼接路径并插入过渡点
        merged = []
        for idx_i, idx in enumerate(order):
            pts = contours[idx]
            # 保持原始轮廓点顺序
            merged.append(pts)
            # 如果不是最后一个轮廓，插入从当前轮廓末尾到下轮廓起点的线性过渡点
            if idx_i+1 < len(order):
                a = pts[-1]
                b = contours[order[idx_i+1]][0]
                # 插入 transition_points 的线性点（不含端点）
                if transition_points > 0:
                    steps = np.linspace(0, 1, transition_points+2)[1:-1]
                    interp = np.vstack([ a + (b-a)*s for s in steps ])
                    merged.append(interp)
        all_pts = np.vstack(merged)
        return all_pts

    def _resample_path(self, pts: np.ndarray, N: int) -> np.ndarray:
        # 返回采样点复数序列
        xs = pts[:,0]
        ys = pts[:,1]
        # 计算段长
        dx = np.diff(xs, append=xs[0])
        dy = np.diff(ys, append=ys[0])
        seglen = np.sqrt(dx*dx + dy*dy)
        cum = np.concatenate(([0.0], np.cumsum(seglen[:-1])))
        total = cum[-1] + seglen[-1] if len(seglen)>0 else 0.0
        if total <= 0:
            return np.zeros(N, dtype=complex)
        ts = np.linspace(0, total, N, endpoint=False)
        
        xs_ext = np.concatenate((xs, [xs[0]]))
        ys_ext = np.concatenate((ys, [ys[0]]))
        seg_cum = np.concatenate(([0.0], np.cumsum(np.sqrt(np.diff(xs_ext)**2 + np.diff(ys_ext)**2))))[:-1]
        
        x_samp = np.interp(ts, seg_cum, xs_ext[:-1])
        y_samp = np.interp(ts, seg_cum, ys_ext[:-1])
        
        cx = np.mean(x_samp)
        cy = np.mean(y_samp)
        x_samp = x_samp - cx
        y_samp = -(y_samp - cy)
        z = x_samp + 1j*y_samp
        return z

    def _generate_gif_from_contours(self, contours: List[np.ndarray], mode: str) -> str:
        # merge
        if mode == "merge":
            merged_pts = self._merge_contours_to_path(contours, transition_points=self.MERGE_TRANSITION_POINTS)
            z = self._resample_path(merged_pts, self.SAMPLE_POINTS)
            z_list = [z]
        else:
            # separate（待修改，尚未进行向量定位）
            lengths = [ np.sum(np.sqrt(np.sum(np.diff(np.vstack([c, c[0]]), axis=0)**2, axis=1))) for c in contours ]
            total_len = sum(lengths)
            z_list = []
            for c, L in zip(contours, lengths):
                # allocate proportional number of samples (至少 32)
                n = max(32, int(round(self.SAMPLE_POINTS * (L/total_len) if total_len>0 else self.SAMPLE_POINTS/len(contours))))
                zc = self._resample_path(c, n)
                z_list.append(zc)

        # 对每条 z 计算傅里叶系数
        coeffs_list = []
        for z in z_list:
            N = len(z)
            c = np.fft.fft(z) / N
            ks = np.arange(N)
            ks_signed = np.where(ks <= N//2, ks, ks - N)
            coeffs = [(int(k), complex(c_val)) for k, c_val in zip(ks_signed, c)]
            coeffs_sorted = sorted(coeffs, key=lambda kv: abs(kv[1]), reverse=True)
            coeffs_sorted = [kv for kv in coeffs_sorted if kv[0]==0] + [kv for kv in coeffs_sorted if kv[0]!=0]
          
            if mode == "merge":
                used = coeffs_sorted[: self.NUM_VECTORS]
            else:
                used_cnt = max(6, int(round(self.NUM_VECTORS * (len(z)/max(1,sum(len(zz) for zz in z_list))))))
                used = coeffs_sorted[:used_cnt]
                if not used:
                    used = coeffs_sorted[:1]
            coeffs_list.append(used)

        # 计算每路径振幅之和并缩放
        R = 0.42 * self.CANVAS_SIZE
        scales = []
        for used in coeffs_list:
            s = sum(abs(kv[1]) for kv in used)
            scales.append(R / s if s>0 else 1.0)
        used_ks_list = [ np.array([kv[0] for kv in used], dtype=int) for used in coeffs_list ]
        used_cs_list = [ np.array([kv[1] for kv in used], dtype=complex) * scale for used, scale in zip(coeffs_list, scales) ]

        # 生成帧
        W = H = self.CANVAS_SIZE
        cx = W//2
        cy = H//2
        frames = []
        path_so_far_list = [ [] for _ in used_cs_list ]  
        t_values = np.linspace(0, 1, self.FRAMES, endpoint=False)
        for t in t_values:
            im = Image.new("RGB", (W,H), "white")
            draw = ImageDraw.Draw(im)
            for pi, (ks, cs, path_so_far) in enumerate(zip(used_ks_list, used_cs_list, path_so_far_list)):
                pos = 0+0j
                circles = []
                lines = []
                for k, ck in zip(ks, cs):
                    start = pos
                    pos = pos + ck * np.exp(2j * math.pi * k * t)
                    circles.append((start, abs(ck)))
                    lines.append((start, pos))
                path_so_far.append(pos)
                for center, rad in circles:
                    x = cx + center.real
                    y = cy - center.imag
                    r = rad
                    bbox = [x-r, y-r, x+r, y+r]
                    draw.ellipse(bbox, outline=(200,200,240), width=1)
                for s, e in lines:
                    sx = cx + s.real
                    sy = cy - s.imag
                    ex = cx + e.real
                    ey = cy - e.imag
                    draw.line([(sx,sy),(ex,ey)], fill=(90,90,160), width=1)
                
                if len(path_so_far) > 1:
                    pts = [(cx + p.real, cy - p.imag) for p in path_so_far]
                    draw.line(pts, fill=(0,0,0), width=2)
                tip = path_so_far[-1]
                tx = cx + tip.real
                ty = cy - tip.imag
                draw.ellipse([tx-3,ty-3,tx+3,ty+3], fill=(255,0,0))
            frames.append(im)

        # 保存 GIF
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gif")
        tmp_path = tmp.name
        tmp.close()
        frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=self.DURATION_MS, loop=0, disposal=2)
        return tmp_path

    def _get_user_key(self, event: AstrMessageEvent) -> str:
        # 分用户识别
        try:
            uid = event.get_sender_id()
        except Exception:
            try:
                uid = event.get_sender_name()
            except Exception:
                uid = "default"
        return str(uid)
