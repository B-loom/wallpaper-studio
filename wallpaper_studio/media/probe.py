"""Analyse des fichiers medias : nature reelle, dimensions, duree, pistes audio.

Les images passent par Pillow, les videos par ``ffprobe`` lorsqu'il est
disponible. Quand aucune information ne peut etre obtenue, les champs restent a
``None`` : l'interface affiche alors un tiret plutot qu'une valeur inventee.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from PIL import Image

from ..app_paths import install_dir
from .types import (
    MAYBE_ANIMATED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    WEB_INDEX_NAME,
    MediaInfo,
    MediaKind,
    kind_from_extension,
)

log = logging.getLogger(__name__)

#: Empeche l'apparition d'une fenetre de console quand on appelle ffprobe
#: depuis une application compilee en mode fenetre.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@lru_cache(maxsize=1)
def ffprobe_path() -> Optional[str]:
    """Chemin de ``ffprobe``, cherche a cote de l'application puis dans le PATH."""
    local = install_dir() / "ffmpeg" / "ffprobe.exe"
    if local.exists():
        return str(local)
    found = shutil.which("ffprobe")
    return found


@lru_cache(maxsize=1)
def ffmpeg_path() -> Optional[str]:
    local = install_dir() / "ffmpeg" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    return shutil.which("ffmpeg")


def has_ffmpeg() -> bool:
    return ffmpeg_path() is not None


def run_ffprobe(path: str, timeout: float = 20.0) -> Optional[dict]:
    """Interroge ffprobe et retourne son rapport JSON, ou ``None`` en cas d'echec."""
    exe = ffprobe_path()
    if not exe:
        return None
    cmd = [
        exe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=_NO_WINDOW, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("ffprobe a echoue sur %s : %s", path, exc)
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None


def _probe_image(path: Path, size_bytes: int) -> MediaInfo:
    """Analyse une image et determine si elle est reellement animee."""
    try:
        with Image.open(path) as im:
            width, height = im.size
            frames = int(getattr(im, "n_frames", 1))
            fmt = im.format
            # La duree d'un GIF est la somme des durees de ses images.
            duration = None
            if frames > 1:
                total = 0.0
                try:
                    for index in range(frames):
                        im.seek(index)
                        total += float(im.info.get("duration", 100))
                    duration = total / 1000.0
                except (EOFError, OSError):
                    duration = None
    except FileNotFoundError:
        return MediaInfo(str(path), MediaKind.UNKNOWN, error="Fichier introuvable")
    except Exception as exc:  # noqa: BLE001 - Pillow leve des erreurs variees
        return MediaInfo(str(path), MediaKind.UNKNOWN, error=f"Image illisible : {exc}")

    animated = frames > 1
    fps = (frames / duration) if (animated and duration) else None
    return MediaInfo(
        path=str(path),
        kind=MediaKind.ANIMATED_IMAGE if animated else MediaKind.IMAGE,
        width=width,
        height=height,
        duration=duration,
        frame_count=frames,
        fps=fps,
        has_audio=False,
        size_bytes=size_bytes,
        codec=fmt,
    )


def _parse_fps(value: Optional[str]) -> Optional[float]:
    """Convertit une cadence ffprobe du type ``30000/1001``."""
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else None
        return float(value)
    except (ValueError, ZeroDivisionError):
        return None


def _probe_video(path: Path, size_bytes: int) -> MediaInfo:
    report = run_ffprobe(str(path))
    if report is None:
        if ffprobe_path() is None:
            # Sans ffprobe on ne peut pas mesurer : on annonce une video dont
            # les caracteristiques sont inconnues plutot que d'inventer des
            # valeurs. libVLC tranchera a la lecture.
            return MediaInfo(
                path=str(path), kind=MediaKind.VIDEO, size_bytes=size_bytes,
            )
        # ffprobe est present et a refuse le fichier : il n'est pas lisible.
        return MediaInfo(
            path=str(path), kind=MediaKind.UNKNOWN, size_bytes=size_bytes,
            error="Fichier video illisible ou corrompu",
        )

    streams = report.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = report.get("format") or {}

    if video is None:
        return MediaInfo(
            path=str(path), kind=MediaKind.UNKNOWN, size_bytes=size_bytes,
            error="Aucun flux video dans ce fichier",
        )

    duration = None
    for source in (video.get("duration"), fmt.get("duration")):
        try:
            if source is not None:
                duration = float(source)
                break
        except (TypeError, ValueError):
            continue

    frames = None
    try:
        frames = int(video.get("nb_frames")) if video.get("nb_frames") else None
    except (TypeError, ValueError):
        frames = None

    return MediaInfo(
        path=str(path),
        kind=MediaKind.VIDEO,
        width=video.get("width"),
        height=video.get("height"),
        duration=duration,
        frame_count=frames,
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        has_audio=audio is not None,
        size_bytes=size_bytes,
        codec=video.get("codec_name"),
    )


def probe_media(path: str | Path) -> MediaInfo:
    """Analyse un fichier (ou un dossier de fond web) et decrit son contenu.

    Cette fonction tranche notamment entre image fixe et image animee : un
    ``.png`` peut etre un APNG, un ``.webp`` peut etre anime.
    """
    p = Path(path)

    if p.is_dir():
        if (p / WEB_INDEX_NAME).exists():
            return MediaInfo(path=str(p), kind=MediaKind.WEB)
        return MediaInfo(
            path=str(p), kind=MediaKind.UNKNOWN,
            error="Dossier sans index.html : ce n'est pas un fond web",
        )

    if not p.exists():
        return MediaInfo(str(p), MediaKind.UNKNOWN, error="Fichier introuvable")

    try:
        size_bytes = p.stat().st_size
    except OSError:
        size_bytes = None
    if size_bytes == 0:
        return MediaInfo(str(p), MediaKind.UNKNOWN, size_bytes=0, error="Fichier vide")

    ext = p.suffix.lower()
    if ext == ".html":
        return MediaInfo(path=str(p), kind=MediaKind.WEB, size_bytes=size_bytes)
    if ext in VIDEO_EXTENSIONS:
        return _probe_video(p, size_bytes)
    if ext in MAYBE_ANIMATED_EXTENSIONS or kind_from_extension(p) is MediaKind.IMAGE:
        return _probe_image(p, size_bytes)

    # Extension inconnue : on tente quand meme une lecture d'image, puis ffprobe.
    info = _probe_image(p, size_bytes)
    if info.is_readable:
        return info
    video = _probe_video(p, size_bytes)
    if video.is_readable:
        return video
    return MediaInfo(
        str(p), MediaKind.UNKNOWN, size_bytes=size_bytes,
        error="Format non reconnu",
    )


def scan_folder(
    folder: str | Path, recursive: bool = True, limit: Optional[int] = None
) -> List[Path]:
    """Liste les fichiers medias d'un dossier, extensions prises en charge."""
    root = Path(folder)
    if not root.is_dir():
        return []
    from .types import all_supported_extensions

    extensions = all_supported_extensions()
    found: List[Path] = []
    iterator = root.rglob("*") if recursive else root.glob("*")
    for item in iterator:
        try:
            if item.is_file() and item.suffix.lower() in extensions:
                found.append(item)
                if limit and len(found) >= limit:
                    break
        except OSError:
            continue
    return sorted(found)
