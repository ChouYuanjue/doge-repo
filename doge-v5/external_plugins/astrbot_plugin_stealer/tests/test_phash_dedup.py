import hashlib
import os
import tempfile
import unittest

try:
    from PIL import Image as PILImage
    from PIL import ImageDraw

    HAS_PIL = True
except ImportError:
    PILImage = None
    ImageDraw = None
    HAS_PIL = False


PHASH_SIZE = 16
PHASH_HAMMING_THRESHOLD = 20


def compute_phash(file_path: str, size: int = PHASH_SIZE) -> str:
    """Compute a dHash-style perceptual hash for a local image file."""
    if PILImage is None:
        return ""
    try:
        with PILImage.open(file_path) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)
            gray = im.convert("L").resize((size + 1, size), PILImage.BILINEAR)
            pixels = list(gray.getdata())

            bits = []
            for row in range(size):
                for col in range(size):
                    idx = row * (size + 1) + col
                    bits.append(1 if pixels[idx] > pixels[idx + 1] else 0)

            hash_int = 0
            for bit in bits:
                hash_int = (hash_int << 1) | bit

            hex_len = (size * size + 3) // 4
            return format(hash_int, f"0{hex_len}x")
    except Exception:
        return ""


def hamming_distance(hash1: str, hash2: str) -> int:
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    try:
        xor = int(hash1, 16) ^ int(hash2, 16)
        return bin(xor).count("1")
    except (ValueError, TypeError):
        return 999


class TestHammingDistance(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(hamming_distance("abcd1234", "abcd1234"), 0)

    def test_different(self):
        self.assertEqual(hamming_distance("0", "f"), 4)

    def test_one_bit(self):
        self.assertEqual(hamming_distance("0", "1"), 1)

    def test_empty(self):
        self.assertEqual(hamming_distance("", "abcd"), 999)
        self.assertEqual(hamming_distance("abcd", ""), 999)

    def test_length_mismatch(self):
        self.assertEqual(hamming_distance("abc", "abcd"), 999)

    def test_all_different_16bit(self):
        self.assertEqual(hamming_distance("0000", "ffff"), 16)


@unittest.skipUnless(HAS_PIL, "PIL not available")
class TestPerceptualHash(unittest.TestCase):
    def test_identical_images(self):
        img = PILImage.new("RGB", (100, 100), color=(255, 0, 0))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
            img.save(f1, format="PNG")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            img.save(f2, format="PNG")
            path2 = f2.name

        try:
            h1 = compute_phash(path1)
            h2 = compute_phash(path2)
            self.assertTrue(h1)
            self.assertEqual(h1, h2)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_similar_images_low_distance(self):
        img1 = PILImage.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = PILImage.new("RGB", (100, 100), color=(250, 5, 5))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
            img1.save(f1, format="PNG")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            img2.save(f2, format="PNG")
            path2 = f2.name

        try:
            d = hamming_distance(compute_phash(path1), compute_phash(path2))
            self.assertLessEqual(d, PHASH_HAMMING_THRESHOLD)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_different_images_high_distance(self):
        img1 = PILImage.new("RGB", (100, 100), color=(0, 0, 0))
        img2 = PILImage.new("RGB", (100, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img2)
        for i in range(0, 100, 10):
            draw.line([(i, 0), (100 - i, 100)], fill=(0, 0, 0), width=3)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
            img1.save(f1, format="PNG")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            img2.save(f2, format="PNG")
            path2 = f2.name

        try:
            d = hamming_distance(compute_phash(path1), compute_phash(path2))
            self.assertGreater(d, PHASH_HAMMING_THRESHOLD)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_reencoded_image_sha256_differs_but_phash_matches(self):
        img = PILImage.new("RGB", (200, 200))
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 80, 80], fill=(255, 0, 0))
        draw.ellipse([100, 50, 180, 150], fill=(0, 255, 0))
        draw.polygon([(50, 120), (90, 180), (10, 180)], fill=(0, 0, 255))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_png:
            img.save(f_png, format="PNG")
            png_path = f_png.name
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_jpg:
            img.save(f_jpg, format="JPEG", quality=92)
            jpg_path = f_jpg.name

        try:
            sha_png = hashlib.sha256(open(png_path, "rb").read()).hexdigest()
            sha_jpg = hashlib.sha256(open(jpg_path, "rb").read()).hexdigest()
            self.assertNotEqual(sha_png, sha_jpg)

            d = hamming_distance(compute_phash(png_path), compute_phash(jpg_path))
            self.assertLessEqual(d, PHASH_HAMMING_THRESHOLD)
        finally:
            os.unlink(png_path)
            os.unlink(jpg_path)

    def test_resized_image_still_matches(self):
        img = PILImage.new("RGB", (400, 400))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 160, 160], fill=(255, 100, 0))
        draw.ellipse([200, 100, 360, 300], fill=(0, 100, 255))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
            img.save(f1, format="PNG")
            original_path = f1.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            resized = img.resize((120, 120), PILImage.BILINEAR)
            resized.save(f2, format="PNG")
            resized_path = f2.name

        try:
            d = hamming_distance(
                compute_phash(original_path),
                compute_phash(resized_path),
            )
            self.assertLessEqual(d, PHASH_HAMMING_THRESHOLD)
        finally:
            os.unlink(original_path)
            os.unlink(resized_path)

    def test_phash_not_empty(self):
        img = PILImage.new("RGB", (50, 50), color=(128, 128, 128))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f, format="PNG")
            path = f.name
        try:
            h = compute_phash(path)
            self.assertTrue(h)
            self.assertEqual(len(h), 64)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
