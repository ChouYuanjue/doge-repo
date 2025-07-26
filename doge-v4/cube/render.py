from PIL import Image, ImageDraw, ImageColor
import io


class DrawCube:
    def __init__(self, colors=None, bg_color=None):
        """
        初始化魔方渲染器，允许传入自定义的6面颜色。
        :param colors: 一个包含6个元素的颜色列表，对应魔方6个面 [前, 后, 左, 右, 上, 下]
        """
        self.face_id = [[0, 1], [1, 0], [1, 1], [1, 2], [1, 3], [2, 1]]
        self.default_colors = ["green", "blue", "red", "orange", "yellow", "white"]
        self.colors = self.initialize_colors(colors)
        self.bg_color = bg_color if self._valid_color(bg_color) else "black"

    def initialize_colors(self, colors=None):
        """初始化颜色列表，检查是否有效并返回正确的颜色映射"""
        if not colors or len(colors) != 6:
            colors = self.default_colors

        color_mapping = {}
        used_colors = set(colors)
        for i, color in enumerate(colors):
            valid_color = (
                colors[i]
                if self._valid_color(color)
                else self._get_unused_color(used_colors)
            )
            used_colors |= {valid_color}
            color_mapping.update(
                dict.fromkeys(range(i * 9 + 1, (i + 1) * 9 + 1), valid_color)
            )

        return color_mapping

    def _valid_color(self, color) -> bool:
        """检查颜色有效性"""
        try:
            ImageColor.getrgb(color)
            return True
        except ValueError:
            return False

    def _get_unused_color(self, used_colors:set):
        """获取未使用的默认颜色, 若无则返回第一个默认颜色"""
        for color in self.default_colors:
            if color not in used_colors:
                return color
        return self.default_colors[0]

    def _clear_image(self):
        self.img = Image.new("RGB", (525, 275), color=self.bg_color)

    def _draw(self, dx, dy, arr):
        drawer = ImageDraw.Draw(self.img)
        dx *= 100
        dy *= 100
        cons = 25
        for conty, row in enumerate(arr):
            for contx, j in enumerate(row):
                posx = contx * cons + dx
                posy = conty * cons + dy
                drawer.rectangle((posx, posy, posx + 20, posy + 20), fill=self.colors[j])

    def _draw_all_cube(self, lst):
        for i in range(len(lst)):
            self._draw(self.face_id[i][1], self.face_id[i][0], lst[i])

    def _prjctn(self, lst):
        draw = ImageDraw.Draw(self.img)
        dx, dy, cons = 400, 100, 25
        for conty, row in enumerate(lst[2]):
            for contx, j in enumerate(row):
                posx = contx * cons + dx
                posy = conty * cons + dy
                draw.rectangle((posx, posy, posx + 20, posy + 20), fill=self.colors[j])

        dx, dy = 470, 84
        for row in lst[0][::-1]:
            for j in row[::-1]:
                draw.polygon(
                    [
                        (11 + dx, 0 + dy),
                        (-9 + dx, 0 + dy),
                        (-20 + dx, 11 + dy),
                        (0 + dx, 11 + dy),
                    ],
                    fill=self.colors[j],
                )
                dx -= 25
            dy -= 14
            dx += 91

        dx, dy = 474, 87
        for row in lst[3]:
            for j in row:
                draw.polygon(
                    [
                        (11 + dx, 0 + dy),
                        (0 + dx, 11 + dy),
                        (0 + dx, 31 + dy),
                        (11 + dx, 20 + dy),
                    ],
                    fill=self.colors[j],
                )
                dx += 16
                dy -= 13
            dx = 474
            dy += 64.5

    def draw(self, newmf) -> bytes:
        """
        渲染图像并返回字节内容
        :param newmf: 魔方六面数据列表，格式为 [U, R, F, D, L, B]
        :return: PNG 格式图像字节
        """
        self._clear_image()
        lst = [newmf[4], newmf[2], newmf[0], newmf[3], newmf[1], newmf[5]]  # 按需重排面
        self._draw_all_cube(lst)
        self._prjctn(lst)
        buf = io.BytesIO()
        self.img.save(buf, format="PNG")
        return buf.getvalue()
