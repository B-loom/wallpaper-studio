"""Fixtures partagees par la suite de tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    """Instance unique de QApplication pour les tests qui touchent a Qt.

    Qt n'autorise qu'une seule QApplication par processus : elle est donc
    creee une fois pour toute la session de tests.
    """
    from wallpaper_studio.system import win_desktop as wd

    wd.enable_dpi_awareness()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Redirige les donnees de l'application vers un dossier temporaire."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import wallpaper_studio.app_paths as app_paths

    # Les fonctions lisent LOCALAPPDATA a chaque appel : rien a invalider.
    return Path(app_paths.data_dir())


@pytest.fixture
def repos(tmp_path):
    """Depots branches sur une base de donnees neuve."""
    from wallpaper_studio.data.database import Database
    from wallpaper_studio.data.repositories import Repositories

    return Repositories(Database(tmp_path / "test.db"))


@pytest.fixture
def media_files(tmp_path):
    """Jeu de fichiers medias reels, generes pour les tests.

    Les images sont produites par Pillow ; la video n'est creee que si FFmpeg
    est disponible, et les tests qui en dependent sont sinon ignores.
    """
    import subprocess

    from PIL import Image

    from wallpaper_studio.media.probe import ffmpeg_path

    folder = tmp_path / "medias"
    folder.mkdir()
    files = {}

    image = folder / "image.png"
    Image.new("RGB", (640, 360), (40, 90, 200)).save(image)
    files["image"] = image

    frames = [
        Image.new("RGB", (160, 90), (c, 60, 200 - c)) for c in (0, 80, 160, 240)
    ]
    gif = folder / "anime.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    files["gif"] = gif

    broken = folder / "casse.mp4"
    broken.write_bytes(b"ceci n'est pas une video")
    files["broken"] = broken

    empty = folder / "vide.mp4"
    empty.write_bytes(b"")
    files["empty"] = empty

    files["absent"] = folder / "absent.mp4"

    exe = ffmpeg_path()
    if exe:
        video = folder / "video.mp4"
        subprocess.run(
            [exe, "-y", "-v", "error", "-f", "lavfi",
             "-i", "testsrc2=size=320x180:rate=15:duration=3",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
            capture_output=True, check=False,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if video.exists():
            files["video"] = video
    return files
