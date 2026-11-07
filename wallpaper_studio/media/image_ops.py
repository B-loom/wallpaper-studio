"""Traitements d'image partages par l'editeur et le moteur de rendu.

Les corrections sont appliquees avec Pillow, puis converties en ``QImage``. Les
images fixes sont traitees une seule fois au chargement ; les images animees ont
leurs images pre-calculees (voir
:mod:`wallpaper_studio.engine.backends.image_backend`), ce qui evite tout traitement pendant
la lecture.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageSequence
from PySide6.QtGui import QImage, QPixmap

from .types import FillMode

log = logging.getLogger(__name__)

#: Au-dela de ce nombre de pixels cumules, on renonce a pre-calculer les images
#: d'une animation pour ne pas saturer la memoire (8 Go de RAM cible).
FRAME_CACHE_PIXEL_BUDGET = 220_000_000


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convertit une image Pillow en ``QImage`` RGBA independante du tampon."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    # copy() detache la QImage du tampon Python, qui peut etre libere ensuite.
    return qimg.copy()


def apply_adjustments(img: Image.Image, adj) -> Image.Image:
    """Applique rotation, miroirs, colorimetrie et flou a une image Pillow.

    ``adj`` est un :class:`wallpaper_studio.engine.playback.ImageAdjustments`. L'ordre est
    choisi pour rester previsible : geometrie, puis couleur, puis flou.
    """
    if adj is None or adj.is_neutral:
        return img

    if adj.rotation:
        # expand=True evite de rogner lors des rotations de 90/270 degres.
        img = img.rotate(-adj.rotation, expand=True, resample=Image.BICUBIC)
    if adj.flip_h:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if adj.flip_v:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)

    if adj.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(adj.brightness)
    if adj.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(adj.contrast)
    if adj.saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(adj.saturation)
    if adj.hue:
        img = _shift_hue(img, adj.hue)
    if adj.blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=adj.blur))
    return img


def _shift_hue(img: Image.Image, degrees: float) -> Image.Image:
    """Decale la teinte. Passe par HSV, en preservant le canal alpha."""
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    hsv = img.convert("RGB").convert("HSV")
    h, s, v = hsv.split()
    shift = int(degrees / 360.0 * 255) % 255
    h = h.point(lambda p: (p + shift) % 255)
    out = Image.merge("HSV", (h, s, v)).convert("RGBA")
    if alpha is not None:
        out.putalpha(alpha)
    return out


def source_crop_for_span(
    size: Tuple[int, int], region: Optional[Tuple[float, float, float, float]]
) -> Optional[Tuple[int, int, int, int]]:
    """Rectangle de rognage en pixels pour un rendu panoramique multi-ecrans.

    ``region`` est exprime en fractions (x, y, largeur, hauteur) de l'image.
    """
    if not region:
        return None
    w, h = size
    x0 = int(round(region[0] * w))
    y0 = int(round(region[1] * h))
    x1 = int(round((region[0] + region[2]) * w))
    y1 = int(round((region[1] + region[3]) * h))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, max(x0 + 1, x1)), min(h, max(y0 + 1, y1))
    return (x0, y0, x1, y1)


def compute_fill_rects(
    src: Tuple[int, int], dst: Tuple[int, int], mode: FillMode
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Calcule les rectangles source et destination pour un mode de remplissage.

    Retourne ``(rect_source, rect_destination)``, chacun ``(x, y, l, h)``. Le
    mode mosaique est traite separement par l'appelant (motif repete).
    """
    sw, sh = max(1, src[0]), max(1, src[1])
    dw, dh = max(1, dst[0]), max(1, dst[1])

    if mode is FillMode.STRETCH:
        return (0, 0, sw, sh), (0, 0, dw, dh)

    if mode is FillMode.CENTER:
        # Rogne la source si elle depasse, sinon centre sans agrandir.
        vis_w, vis_h = min(sw, dw), min(sh, dh)
        sx, sy = (sw - vis_w) // 2, (sh - vis_h) // 2
        dx, dy = (dw - vis_w) // 2, (dh - vis_h) // 2
        return (sx, sy, vis_w, vis_h), (dx, dy, vis_w, vis_h)

    if mode is FillMode.CONTAIN:
        scale = min(dw / sw, dh / sh)
        tw, th = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
        return (0, 0, sw, sh), ((dw - tw) // 2, (dh - th) // 2, tw, th)

    # COVER : on remplit la destination et on rogne la source.
    scale = max(dw / sw, dh / sh)
    # Portion de la source reellement visible, centree.
    vis_w = min(sw, max(1, int(round(dw / scale))))
    vis_h = min(sh, max(1, int(round(dh / scale))))
    sx, sy = (sw - vis_w) // 2, (sh - vis_h) // 2
    return (sx, sy, vis_w, vis_h), (0, 0, dw, dh)


def load_static_image(
    path: str,
    adjustments=None,
    span_region: Optional[Tuple[float, float, float, float]] = None,
    max_side: Optional[int] = None,
) -> QImage:
    """Charge une image fixe, corrections appliquees.

    ``max_side`` permet de reduire une image enorme avant traitement : un
    fichier 8000x6000 serait inutilement couteux pour un ecran 1920x1080.
    Leve une exception en cas de fichier illisible ; l'appelant la traduit.
    """
    with Image.open(path) as im:
        im.load()
        img = im.convert("RGBA")

    crop = source_crop_for_span(img.size, span_region)
    if crop:
        img = img.crop(crop)

    if max_side:
        w, h = img.size
        longest = max(w, h)
        if longest > max_side:
            ratio = max_side / longest
            img = img.resize(
                (max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS
            )

    img = apply_adjustments(img, adjustments)
    return pil_to_qimage(img)


def count_frames(path: str) -> int:
    """Nombre d'images d'un fichier potentiellement anime (1 si fixe)."""
    try:
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1)
    except Exception:  # noqa: BLE001 - fichier illisible ou format inconnu
        return 1


def load_animation_frames(
    path: str,
    adjustments=None,
    span_region: Optional[Tuple[float, float, float, float]] = None,
    max_side: Optional[int] = None,
) -> Tuple[List[QPixmap], List[int]]:
    """Pre-calcule toutes les images d'une animation et leurs durees.

    Retourne ``(images, durees_ms)``. Lever le decodage en amont permet une
    lecture quasi gratuite ensuite : pendant l'affichage, le moteur ne fait plus
    que recopier un ``QPixmap`` deja pret.

    Leve :class:`MemoryError` si le budget memoire serait depasse : l'appelant
    se rabat alors sur un decodage a la volee.
    """
    frames: List[QPixmap] = []
    delays: List[int] = []
    budget = 0

    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        base_w, base_h = im.size
        scale = 1.0
        if max_side:
            longest = max(base_w, base_h)
            if longest > max_side:
                scale = max_side / longest
        est = int(base_w * scale) * int(base_h * scale) * max(1, n)
        if est > FRAME_CACHE_PIXEL_BUDGET:
            raise MemoryError(
                f"{n} images de {base_w}x{base_h} depassent le budget memoire"
            )

        for frame in ImageSequence.Iterator(im):
            # GIF : la duree est portee par chaque image ; 100 ms par defaut
            # comme le font les navigateurs pour les valeurs absentes ou nulles.
            delay = int(frame.info.get("duration", 0)) or 100
            img = frame.convert("RGBA")

            crop = source_crop_for_span(img.size, span_region)
            if crop:
                img = img.crop(crop)
            if scale != 1.0:
                img = img.resize(
                    (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                    Image.LANCZOS,
                )
            img = apply_adjustments(img, adjustments)

            budget += img.width * img.height
            if budget > FRAME_CACHE_PIXEL_BUDGET:
                raise MemoryError("budget memoire depasse pendant le decodage")

            frames.append(QPixmap.fromImage(pil_to_qimage(img)))
            delays.append(max(20, delay))

    if not frames:
        raise ValueError("aucune image decodee")
    return frames, delays


def make_thumbnail(path: str, size: Tuple[int, int] = (480, 270)) -> Image.Image:
    """Vignette d'une image (premiere image pour une animation)."""
    with Image.open(path) as im:
        im.seek(0)
        img = im.convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    return img
