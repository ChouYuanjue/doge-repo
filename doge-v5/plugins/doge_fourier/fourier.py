from __future__ import annotations

import io
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


class FourierError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FourierStats:
    contours: int
    samples: int
    vectors: int
    frames: int
    mode: str


class FourierRenderer:
    """Contour -> complex path -> DFT -> epicycle GIF.

    This preserves the v4 product semantics while fixing separate-mode contour
    positioning and adding direct raster-image input. Photos use edge contours;
    text/SVG use filled binary contours so inner holes remain meaningful.
    """

    MAX_SIDE = 900
    CANVAS = 800
    DEFAULT_SAMPLES = 2048
    DEFAULT_VECTORS = 80
    DEFAULT_FRAMES = 220
    MAX_CONTOURS = 72

    @staticmethod
    def _fit_image(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", rgba.size, "white")
            white.alpha_composite(rgba)
            image = white.convert("RGB")
        else:
            image = image.convert("RGB")
        if max(image.size) > max_side:
            scale = max_side / max(image.size)
            image = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
        return image

    @classmethod
    def from_image_path(cls, path: str | Path, *, mode: str="merge", vectors: int=80, frames: int=220, samples: int=2048) -> tuple[Path, FourierStats]:
        with Image.open(path) as im:
            image=cls._fit_image(im)
        return cls._render(image, binary_hint=False, mode=mode, vectors=vectors, frames=frames, samples=samples)

    @classmethod
    def from_svg(cls, svg: str, *, mode: str="merge", vectors: int=80, frames: int=220, samples: int=2048) -> tuple[Path, FourierStats]:
        if "<svg" not in svg.lower() or len(svg) > 200_000:
            raise FourierError("需要有效的 SVG 源码（最多 200k 字符）")
        try:
            import cairosvg
        except ImportError as exc:
            raise FourierError("CairoSVG 未安装") from exc
        try:
            raw=cairosvg.svg2png(bytestring=svg.encode('utf-8'), output_width=cls.MAX_SIDE, output_height=cls.MAX_SIDE)
            image=Image.open(io.BytesIO(raw)).convert('RGB')
        except Exception as exc:
            raise FourierError(f"SVG 渲染失败：{exc}") from exc
        return cls._render(image, binary_hint=True, mode=mode, vectors=vectors, frames=frames, samples=samples)

    @classmethod
    def from_text(cls, text: str, *, mode: str="merge", vectors: int=80, frames: int=220, samples: int=2048) -> tuple[Path, FourierStats]:
        text=str(text or '').strip()
        if not text:
            raise FourierError("缺少文本")
        if len(text)>10:
            raise FourierError("text 模式沿用 v4 限制：最多 10 个字符")
        size=cls.MAX_SIDE
        image=Image.new('L',(size,size),255)
        draw=ImageDraw.Draw(image)
        fonts=[
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        font_path=next((p for p in fonts if Path(p).exists()),None)
        if not font_path:
            font=ImageFont.load_default()
        else:
            font=None
            for fs in range(260,23,-6):
                candidate=ImageFont.truetype(font_path,fs)
                box=draw.textbbox((0,0),text,font=candidate)
                if box[2]-box[0] <= size*.86 and box[3]-box[1] <= size*.80:
                    font=candidate; break
            font=font or ImageFont.truetype(font_path,24)
        box=draw.textbbox((0,0),text,font=font)
        x=(size-(box[2]-box[0]))/2-box[0]; y=(size-(box[3]-box[1]))/2-box[1]
        draw.text((x,y),text,font=font,fill=0)
        return cls._render(image.convert('RGB'), binary_hint=True, mode=mode, vectors=vectors, frames=frames, samples=samples)

    @classmethod
    def _contours(cls, image: Image.Image, *, binary_hint: bool) -> list[np.ndarray]:
        try:
            import cv2
        except ImportError as exc:
            raise FourierError("OpenCV 未安装") from exc
        gray=np.asarray(image.convert('L'))
        if binary_hint:
            blur=cv2.GaussianBlur(gray,(3,3),0)
            _,mask=cv2.threshold(blur,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
            mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8),iterations=1)
        else:
            blur=cv2.bilateralFilter(gray,7,45,45)
            med=float(np.median(blur))
            low=int(max(20,0.66*med)); high=int(min(245,max(low+25,1.33*med)))
            mask=cv2.Canny(blur,low,high,L2gradient=True)
            mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8),iterations=1)
        found=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        contours=found[-2]
        if not contours:
            raise FourierError("没有从素材中提取到可用轮廓")
        h,w=gray.shape; diag=math.hypot(w,h)
        ranked=[]
        for contour in contours:
            pts=contour[:,0,:].astype(np.float64)
            if len(pts)<12: continue
            perimeter=float(cv2.arcLength(contour,True)); area=abs(float(cv2.contourArea(contour)))
            if perimeter < max(18.0,diag*.018): continue
            # Prefer long/meaningful contours; area helps filled shapes but is
            # not required because Canny contours can be nearly zero-area.
            score=perimeter + math.sqrt(area+1.0)*2.0
            ranked.append((score,pts))
        ranked.sort(key=lambda x:x[0],reverse=True)
        pieces=[p for _,p in ranked[:cls.MAX_CONTOURS]]
        if not pieces:
            raise FourierError("轮廓都过小；请换更清晰或主体更大的图片")
        return pieces

    @staticmethod
    def _closed(pts: np.ndarray) -> np.ndarray:
        if len(pts)<2: return pts
        return pts if np.allclose(pts[0],pts[-1]) else np.vstack([pts,pts[0]])

    @classmethod
    def _order_merge(cls, contours: list[np.ndarray]) -> np.ndarray:
        """Endpoint-nearest path stitching with cyclic start-point rotation."""
        remaining=[cls._closed(c)[:-1] for c in contours]
        start_idx=min(range(len(remaining)),key=lambda i:(remaining[i][:,0].min(),remaining[i][:,1].min()))
        current=remaining.pop(start_idx)
        merged=[current]
        tip=current[-1]
        while remaining:
            best=None
            for i,pts in enumerate(remaining):
                d2=np.sum((pts-tip)**2,axis=1)
                j=int(np.argmin(d2)); dist=float(d2[j])
                if best is None or dist<best[0]: best=(dist,i,j)
            _,i,j=best
            pts=remaining.pop(i)
            pts=np.vstack([pts[j:],pts[:j]])
            gap=float(np.linalg.norm(pts[0]-tip))
            if gap>1:
                n=min(16,max(2,int(gap/35)))
                merged.append(np.linspace(tip,pts[0],n+2,endpoint=True)[1:-1])
            merged.append(pts); tip=pts[-1]
        return np.vstack(merged)

    @staticmethod
    def _resample(pts: np.ndarray, n: int) -> np.ndarray:
        pts=np.asarray(pts,dtype=np.float64)
        if len(pts)<2: raise FourierError("轮廓点不足")
        closed=np.vstack([pts,pts[0]]) if not np.allclose(pts[0],pts[-1]) else pts
        delta=np.diff(closed,axis=0); lengths=np.linalg.norm(delta,axis=1)
        total=float(lengths.sum())
        if total<=1e-9: raise FourierError("轮廓长度为零")
        cum=np.concatenate([[0.0],np.cumsum(lengths)])
        target=np.linspace(0,total,n,endpoint=False)
        x=np.interp(target,cum,closed[:,0]); y=np.interp(target,cum,closed[:,1])
        return x+1j*y

    @staticmethod
    def _coeffs(z: np.ndarray, vectors: int) -> list[tuple[int,complex]]:
        n=len(z); c=np.fft.fft(z)/n
        ks=np.arange(n); signed=np.where(ks<=n//2,ks,ks-n)
        pairs=[(int(k),complex(v)) for k,v in zip(signed,c)]
        dc=[x for x in pairs if x[0]==0]
        other=sorted((x for x in pairs if x[0]!=0),key=lambda x:abs(x[1]),reverse=True)
        return dc+other[:max(1,vectors-1)]

    @classmethod
    def _render(cls, image: Image.Image, *, binary_hint: bool, mode: str, vectors: int, frames: int, samples: int) -> tuple[Path, FourierStats]:
        mode=str(mode or 'merge').lower()
        if mode not in {'merge','separate'}: raise FourierError("mode 只支持 merge / separate")
        vectors=max(8,min(int(vectors),180)); frames=max(40,min(int(frames),260)); samples=max(256,min(int(samples),4096))
        image=cls._fit_image(image)
        contours=cls._contours(image,binary_hint=binary_hint)
        # Preserve original spatial layout. Unlike v4 separate mode, every
        # component is normalized against the same global image center.
        scale=.76*cls.CANVAS/max(image.width,image.height)
        cx0=image.width/2; cy0=image.height/2
        def normalize(z): return ((z.real-cx0)*scale) + 1j*(-(z.imag-cy0)*scale)
        if mode=='merge':
            paths=[normalize(cls._resample(cls._order_merge(contours),samples))]
        else:
            perimeters=[]
            for c in contours:
                cc=cls._closed(c); perimeters.append(float(np.linalg.norm(np.diff(cc,axis=0),axis=1).sum()))
            total=sum(perimeters) or 1.0
            paths=[]
            for c,L in zip(contours,perimeters):
                n=max(96,int(round(samples*L/total)))
                paths.append(normalize(cls._resample(c,n)))
        # In separate mode divide vector budget proportionally, but guarantee
        # enough harmonics per contour. This is intentionally faithful to the
        # multi-component drawing rather than collapsing into one spectrum.
        if mode=='merge':
            coeff_sets=[cls._coeffs(paths[0],vectors)]
        else:
            total_n=sum(len(z) for z in paths)
            coeff_sets=[cls._coeffs(z,max(8,round(vectors*len(z)/total_n))) for z in paths]
        traces=[[] for _ in coeff_sets]
        out_frames=[]; center=cls.CANVAS/2
        for fi in range(frames):
            t=fi/frames
            canvas=Image.new('RGB',(cls.CANVAS,cls.CANVAS),'white'); draw=ImageDraw.Draw(canvas)
            for coeffs,trace in zip(coeff_sets,traces):
                dc=next((v for k,v in coeffs if k==0),0j); pos=dc
                for k,coef in coeffs:
                    if k==0: continue
                    start=pos; pos += coef*np.exp(2j*math.pi*k*t)
                    x=center+start.real; y=center-start.imag; r=abs(coef)
                    if r>=1.2: draw.ellipse((x-r,y-r,x+r,y+r),outline=(210,214,226),width=1)
                    draw.line((center+start.real,center-start.imag,center+pos.real,center-pos.imag),fill=(82,91,132),width=1)
                trace.append(pos)
                if len(trace)>1:
                    draw.line([(center+p.real,center-p.imag) for p in trace],fill=(18,20,28),width=2)
                draw.ellipse((center+pos.real-2.5,center-pos.imag-2.5,center+pos.real+2.5,center-pos.imag+2.5),fill=(170,40,52))
            # Adaptive palette keeps GIF substantially smaller without changing
            # geometry; no image-generation model is involved.
            out_frames.append(canvas.convert('P',palette=Image.Palette.ADAPTIVE,colors=48))
        tmp=tempfile.NamedTemporaryFile(delete=False,suffix='.gif'); tmp.close(); path=Path(tmp.name)
        out_frames[0].save(path,save_all=True,append_images=out_frames[1:],duration=24,loop=0,disposal=2,optimize=False)
        return path, FourierStats(len(contours),samples,vectors,frames,mode)
