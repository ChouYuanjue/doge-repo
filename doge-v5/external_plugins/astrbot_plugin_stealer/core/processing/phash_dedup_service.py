"""感知哈希去重服务：负责计算 pHash 和汉明距离比较。"""

import asyncio
from typing import Any

from astrbot.api import logger

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


class PHashDedupService:
    """基于感知哈希 (pHash) 的图片视觉去重服务。"""

    PHASH_SIZE = 16  # 感知哈希图片缩放尺寸（16x16 = 256 bit hash）
    PHASH_HAMMING_THRESHOLD = 20  # 汉明距离阈值，低于此值视为重复

    def __init__(self, plugin_instance: Any = None) -> None:
        self.plugin = plugin_instance

    async def compute_phash(self, file_path: str) -> str:
        """计算图片的感知哈希 (pHash)，用于视觉去重。

        使用 difference hash (dHash) 算法：
        - 将图片缩放到 (PHASH_SIZE+1) x PHASH_SIZE 的灰度图
        - 比较相邻像素的亮度差异生成哈希位
        - 对 GIF 动图取第一帧

        Args:
            file_path: 图片文件路径

        Returns:
            str: 十六进制感知哈希字符串，失败返回空字符串
        """
        if PILImage is None:
            return ""

        size = self.PHASH_SIZE

        def _sync_phash(fp: str) -> str:
            try:
                with PILImage.open(fp) as im:
                    # GIF 动图取第一帧
                    if getattr(im, "is_animated", False):
                        im.seek(0)
                    # 转灰度并缩放到 (size+1) x size
                    gray = im.convert("L").resize((size + 1, size), PILImage.BILINEAR)
                    pixels = list(gray.getdata())

                    # dHash: 比较每行相邻像素
                    bits = []
                    for row in range(size):
                        for col in range(size):
                            idx = row * (size + 1) + col
                            bits.append(1 if pixels[idx] > pixels[idx + 1] else 0)

                    # 转换为十六进制字符串
                    hash_int = 0
                    for bit in bits:
                        hash_int = (hash_int << 1) | bit
                    hex_len = (size * size + 3) // 4  # 向上取整
                    return format(hash_int, f"0{hex_len}x")
            except Exception as e:
                logger.warning(f"计算感知哈希失败: {e}")
                return ""

        try:
            return await asyncio.to_thread(_sync_phash, file_path)
        except Exception as e:
            logger.warning(f"计算感知哈希失败: {e}")
            return ""

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """计算两个十六进制哈希字符串的汉明距离。

        Args:
            hash1: 第一个十六进制哈希
            hash2: 第二个十六进制哈希

        Returns:
            int: 汉明距离（不同位的数量），如果无法计算返回极大值
        """
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return 999
        try:
            xor = int(hash1, 16) ^ int(hash2, 16)
            return bin(xor).count("1")
        except (ValueError, TypeError):
            return 999
