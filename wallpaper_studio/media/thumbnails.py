"""Generation et cache des vignettes de la bibliotheque.

Le nom du fichier de vignette derive du chemin source et de sa date de
modification : une image modifiee produit donc une nouvelle vignette, sans
qu'il faille invalider le cache manuellement.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

from ..app_paths import thumbnail_dir
from .probe import ffmpeg_path
from .types import MediaKind

log = logging.getLogger(__name__)

THUMB_SIZE = (480, 270)
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def thumbnail_key(path: str | Path) -> str:
    """Identifiant stable d'une vignette, sensible au contenu du fichier."""
    p = Path(path)
    try:
        stamp = f"{p.stat().st_mtime_ns}:{p.stat().st_size}"
    except OSError:
        stamp = "0"
    digest = hashlib.sha1(f"{p.resolve()}|{stamp}".encode("utf-8", "replace"))
    return digest.hexdigest()[:20]


def thumbnail_file(path: str | Path) -> Path:
    return thumbnail_dir() / f"{thumbnail_key(path)}.jpg"


def _save(img: Image.Image, destination: Path) -> Path:
    img = img.convert("RGB")
    img.thumbnail(THUMB_SIZE, Image.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    img.save(destination, "JPEG", quality=82, optimize=True)
    return destination


def _thumbnail_from_image(path: Path, destination: Path) -> Optional[Path]:
    try:
        with Image.open(path) as im:
            im.seek(0)  # premiere image d'une animation
            return _save(im.copy(), destination)
    except Exception as exc:  # noqa: BLE001
        log.debug("Vignette impossible pour %s : %s", path, exc)
        return None


def _thumbnail_from_video(path: Path, destination: Path) -> Optional[Path]:
    """Extrait une image representative avec ffmpeg.

    On vise une seconde de lecture plutot que l'instant zero : beaucoup de
    videos commencent par un fondu au noir, qui donnerait une vignette noire.
    """
    exe = ffmpeg_path()
    if not exe:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-v", "error", "-y",
        "-ss", "1",
        "-i", str(path),
        "-frames:v", "1",
        "-vf", f"scale={THUMB_SIZE[0]}:-2",
        str(destination),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=30,
            creationflags=_NO_WINDOW, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("ffmpeg (vignette) a echoue sur %s : %s", path, exc)
        return None

    if result.returncode != 0 or not destination.exists():
        # Video plus courte qu'une seconde : nouvelle tentative a l'instant 0.
        cmd[cmd.index("-ss") + 1] = "0"
        try:
            subprocess.run(
                cmd, capture_output=True, timeout=30,
                creationflags=_NO_WINDOW, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
    return destination if destination.exists() else None


def generate_thumbnail(
    path: str | Path, kind: MediaKind, force: bool = False
) -> Optional[Path]:
    """Cree (ou retrouve) la vignette d'un media. ``None`` si impossible."""
    source = Path(path)
    destination = thumbnail_file(source)
    if destination.exists() and not force:
        return destination

    if kind is MediaKind.VIDEO:
        return _thumbnail_from_video(source, destination)
    if kind in (MediaKind.IMAGE, MediaKind.ANIMATED_IMAGE):
        return _thumbnail_from_image(source, destination)
    if kind is MediaKind.WEB:
        # Un fond web peut fournir sa propre vignette.
        for name in ("preview.png", "preview.jpg", "thumbnail.png"):
            candidate = source / name if source.is_dir() else source.parent / name
            if candidate.exists():
                return _thumbnail_from_image(candidate, destination)
    return None


def purge_orphan_thumbnails(known: set[str]) -> int:
    """Supprime les vignettes qui ne correspondent plus a aucune entree."""
    removed = 0
    for item in thumbnail_dir().glob("*.jpg"):
        if item.name not in known:
            try:
                item.unlink()
                removed += 1
            except OSError:
                continue
    if removed:
        log.info("%s vignette(s) orpheline(s) supprimee(s)", removed)
    return removed
