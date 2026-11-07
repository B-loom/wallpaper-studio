"""Conversion de medias par FFmpeg.

Module **facultatif** : l'application fonctionne sans lui, et aucune conversion
n'est imposee quand un fichier peut etre lu directement. Il sert aux cas ou un
media n'est pas exploitable tel quel, ou lorsque l'utilisateur veut produire une
variante (GIF depuis une video, vignette, sequence d'images...).

FFmpeg est distribue sous licence LGPL v2.1 ou GPL v2+ selon la compilation
retenue ; voir ``LICENSES.md``. L'application l'appelle comme un programme
externe, sans l'incorporer.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from .probe import ffmpeg_path, probe_media
from .types import MediaKind

log = logging.getLogger(__name__)

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

#: Motif des lignes de progression de ffmpeg (``time=00:00:12.34``).
_TIME_RE = re.compile(r"time=(\d+):(\d\d):(\d\d)\.(\d\d)")


class ConversionType(str, Enum):
    """Conversions proposees par l'application."""

    VIDEO_TO_GIF = "video_vers_gif"
    GIF_TO_FRAMES = "gif_vers_images"
    FRAMES_TO_VIDEO = "images_vers_video"
    EXTRACT_FRAME = "extraire_une_image"
    CONVERT_IMAGE = "convertir_image"
    REENCODE_VIDEO = "reencoder_video"

    @property
    def label(self) -> str:
        return {
            ConversionType.VIDEO_TO_GIF: "Transformer une video en GIF",
            ConversionType.GIF_TO_FRAMES: "Extraire les images d'un GIF",
            ConversionType.FRAMES_TO_VIDEO: "Creer une video depuis des images",
            ConversionType.EXTRACT_FRAME: "Extraire une image d'une video",
            ConversionType.CONVERT_IMAGE: "Convertir une image",
            ConversionType.REENCODE_VIDEO: "Reencoder une video (MP4 H.264)",
        }[self]


@dataclass
class ConversionResult:
    """Issue d'une conversion."""

    success: bool
    output: Optional[Path] = None
    message: str = ""
    command: str = ""

    @property
    def summary(self) -> str:
        if self.success:
            return f"Conversion reussie : {self.output.name if self.output else ''}"
        return f"Echec de la conversion : {self.message}"


def is_available() -> bool:
    """Vrai si FFmpeg est utilisable sur ce systeme."""
    return ffmpeg_path() is not None


def _duration_seconds(path: Path) -> Optional[float]:
    info = probe_media(path)
    return info.duration


def _run_ffmpeg(
    args: List[str],
    total_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[float], None]] = None,
    timeout: float = 900.0,
) -> ConversionResult:
    """Lance FFmpeg en suivant sa progression.

    ``on_progress`` recoit une fraction entre 0.0 et 1.0 lorsque la duree
    totale est connue.
    """
    exe = ffmpeg_path()
    if not exe:
        return ConversionResult(
            False, message="FFmpeg est introuvable sur ce systeme."
        )

    command = [exe, "-y", "-hide_banner", *args]
    log.info("FFmpeg : %s", " ".join(command[:9]) + (" ..." if len(command) > 9 else ""))

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return ConversionResult(False, message=str(exc))

    tail: List[str] = []
    try:
        for line in process.stdout or []:
            tail.append(line.rstrip())
            # On ne garde que la fin : un echec se lit dans les dernieres lignes.
            if len(tail) > 25:
                tail.pop(0)
            if on_progress and total_seconds:
                match = _TIME_RE.search(line)
                if match:
                    h, m, s, cs = (int(g) for g in match.groups())
                    done = h * 3600 + m * 60 + s + cs / 100.0
                    on_progress(min(1.0, done / total_seconds))
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return ConversionResult(False, message="Delai depasse", command=" ".join(command))

    if process.returncode != 0:
        return ConversionResult(
            False,
            message="\n".join(tail[-6:]) or f"code de sortie {process.returncode}",
            command=" ".join(command),
        )
    if on_progress:
        on_progress(1.0)
    return ConversionResult(True, command=" ".join(command))


# --- Conversions ------------------------------------------------------------
def video_to_gif(
    source: Path,
    destination: Path,
    fps: int = 15,
    width: int = 640,
    start: float = 0.0,
    duration: Optional[float] = None,
    on_progress: Optional[Callable[[float], None]] = None,
) -> ConversionResult:
    """Convertit une video en GIF avec une palette dediee.

    La generation d'une palette en deux passes evite le tramage grossier du
    GIF 256 couleurs ; c'est ce qui distingue un GIF correct d'un GIF sale.
    """
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    palette = destination.with_suffix(".palette.png")

    trim: List[str] = []
    if start > 0:
        trim += ["-ss", str(start)]
    if duration:
        trim += ["-t", str(duration)]

    chain = f"fps={fps},scale={width}:-1:flags=lanczos"

    first = _run_ffmpeg(
        [*trim, "-i", str(source), "-vf", f"{chain},palettegen=stats_mode=diff",
         str(palette)]
    )
    if not first.success:
        return first

    result = _run_ffmpeg(
        [*trim, "-i", str(source), "-i", str(palette),
         "-lavfi", f"{chain}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
         str(destination)],
        total_seconds=duration or _duration_seconds(source),
        on_progress=on_progress,
    )
    palette.unlink(missing_ok=True)
    result.output = destination if result.success else None
    return result


def gif_to_frames(
    source: Path, destination_dir: Path, prefix: str = "image"
) -> ConversionResult:
    """Extrait chaque image d'un GIF dans un dossier."""
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    pattern = destination_dir / f"{prefix}_%04d.png"
    result = _run_ffmpeg(["-i", str(source), str(pattern)])
    if result.success:
        result.output = destination_dir
        count = len(list(destination_dir.glob(f"{prefix}_*.png")))
        result.message = f"{count} image(s) extraite(s)"
    return result


def frames_to_video(
    pattern: str,
    destination: Path,
    fps: int = 30,
    on_progress: Optional[Callable[[float], None]] = None,
) -> ConversionResult:
    """Assemble une sequence d'images en video MP4.

    ``pattern`` suit la syntaxe FFmpeg, par exemple ``C:/images/img_%04d.png``.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run_ffmpeg(
        ["-framerate", str(fps), "-i", pattern,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         # Dimensions paires obligatoires pour yuv420p.
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         str(destination)],
        on_progress=on_progress,
    )
    result.output = destination if result.success else None
    return result


def extract_frame(
    source: Path, destination: Path, position: float = 1.0
) -> ConversionResult:
    """Extrait une image unique d'une video, a la position donnee (secondes)."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run_ffmpeg(
        ["-ss", str(position), "-i", str(source), "-frames:v", "1", str(destination)]
    )
    result.output = destination if result.success else None
    return result


def convert_image(source: Path, destination: Path, quality: int = 90) -> ConversionResult:
    """Convertit une image d'un format a un autre (via Pillow, sans FFmpeg)."""
    from PIL import Image

    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as im:
            img = im.convert("RGBA")
            if destination.suffix.lower() in (".jpg", ".jpeg"):
                # Le JPEG ne gere pas la transparence : fond noir par defaut.
                background = Image.new("RGB", img.size, (0, 0, 0))
                background.paste(img, mask=img.split()[3])
                img = background
            img.save(destination, quality=quality)
    except Exception as exc:  # noqa: BLE001
        return ConversionResult(False, message=str(exc))
    return ConversionResult(True, output=destination)


def reencode_video(
    source: Path,
    destination: Path,
    width: Optional[int] = None,
    crf: int = 23,
    on_progress: Optional[Callable[[float], None]] = None,
) -> ConversionResult:
    """Reencode une video en MP4 H.264, format le mieux accelere materiellement."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(source)]
    if width:
        args += ["-vf", f"scale={width}:-2"]
    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        str(destination),
    ]
    result = _run_ffmpeg(
        args, total_seconds=_duration_seconds(source), on_progress=on_progress
    )
    result.output = destination if result.success else None
    return result


def suggest_conversion(path: Path) -> Optional[ConversionType]:
    """Propose une conversion lorsqu'un fichier n'est pas directement lisible.

    Retourne ``None`` quand le fichier est deja exploitable : la conversion ne
    doit jamais etre imposee a un media qui fonctionne.
    """
    info = probe_media(path)
    if info.is_readable:
        return None
    if Path(path).suffix.lower() in (".avi", ".wmv", ".flv", ".mpg", ".mpeg"):
        return ConversionType.REENCODE_VIDEO
    if info.kind is MediaKind.UNKNOWN and is_available():
        return ConversionType.REENCODE_VIDEO
    return None
