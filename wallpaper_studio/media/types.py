"""Types de medias et capacites reelles de l'application.

Ce module est la source unique de verite sur *ce que le logiciel sait afficher*.
Les listes d'extensions ne sont pas declaratives : chaque entree correspond a un
moteur de rendu reellement implemente (voir :mod:`wallpaper_studio.engine.backends`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import FrozenSet, Optional


class MediaKind(str, Enum):
    """Nature d'un fond d'ecran, qui determine le moteur de rendu utilise."""

    IMAGE = "image"
    #: Image animee rendue image par image par Qt (GIF, APNG, WEBP anime).
    ANIMATED_IMAGE = "animated_image"
    VIDEO = "video"
    #: Dossier contenant un ``index.html`` rendu par QtWebEngine.
    WEB = "web"
    #: Scene generee par l'application (particules, degrades animes).
    SCENE = "scene"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            MediaKind.IMAGE: "Image",
            MediaKind.ANIMATED_IMAGE: "Image animee",
            MediaKind.VIDEO: "Video",
            MediaKind.WEB: "Fond web",
            MediaKind.SCENE: "Scene",
            MediaKind.UNKNOWN: "Inconnu",
        }[self]

    @property
    def is_animated(self) -> bool:
        """Vrai si le rendu consomme du CPU/GPU en continu."""
        return self in (
            MediaKind.ANIMATED_IMAGE,
            MediaKind.VIDEO,
            MediaKind.WEB,
            MediaKind.SCENE,
        )


#: Images fixes decodees par Qt (QImageReader) et Pillow.
IMAGE_EXTENSIONS: FrozenSet[str] = frozenset(
    {".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".jfif"}
)

#: Conteneurs susceptibles de contenir une animation. La distinction entre image
#: fixe et image animee est faite a l'ouverture : un PNG peut etre un APNG, un
#: WEBP peut etre anime. Voir :func:`wallpaper_studio.media.probe.probe_media`.
MAYBE_ANIMATED_EXTENSIONS: FrozenSet[str] = frozenset({".gif", ".png", ".webp", ".apng"})

#: Formats video lus par libVLC. libVLC embarque ses propres demultiplexeurs et
#: decodeurs, d'ou une couverture large et verifiable a l'execution.
VIDEO_EXTENSIONS: FrozenSet[str] = frozenset(
    {
        ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv",
        ".flv", ".mpg", ".mpeg", ".m2ts", ".ts", ".ogv", ".3gp", ".asf",
    }
)

#: Extension conventionnelle d'un paquet de fond d'ecran web de l'application.
WEB_MANIFEST_NAME = "wallpaper.json"
WEB_INDEX_NAME = "index.html"


def all_supported_extensions() -> FrozenSet[str]:
    return IMAGE_EXTENSIONS | MAYBE_ANIMATED_EXTENSIONS | VIDEO_EXTENSIONS


def file_dialog_filter() -> str:
    """Filtre pour les boites de dialogue Qt, en francais."""

    def joined(exts) -> str:
        return " ".join(f"*{e}" for e in sorted(exts))

    return (
        f"Tous les fonds pris en charge ({joined(all_supported_extensions())});;"
        f"Images ({joined(IMAGE_EXTENSIONS | MAYBE_ANIMATED_EXTENSIONS)});;"
        f"Videos ({joined(VIDEO_EXTENSIONS)});;"
        "Tous les fichiers (*)"
    )


def kind_from_extension(path: str | Path) -> MediaKind:
    """Devine la nature d'un media d'apres son chemin, sans ouvrir le fichier.

    Un GIF/PNG/WEBP est annonce comme image fixe : seule une analyse du contenu
    peut dire s'il est anime. :func:`wallpaper_studio.media.probe.probe_media` tranche.
    """
    p = Path(path)
    if p.is_dir():
        return MediaKind.WEB if (p / WEB_INDEX_NAME).exists() else MediaKind.UNKNOWN
    ext = p.suffix.lower()
    if ext == ".html":
        return MediaKind.WEB
    if ext == ".gif":
        return MediaKind.ANIMATED_IMAGE
    if ext in VIDEO_EXTENSIONS:
        return MediaKind.VIDEO
    if ext in IMAGE_EXTENSIONS:
        return MediaKind.IMAGE
    return MediaKind.UNKNOWN


class FillMode(str, Enum):
    """Maniere d'adapter un media au rectangle de l'ecran."""

    #: Remplit l'ecran en conservant les proportions, en rognant le surplus.
    COVER = "cover"
    #: Media entierement visible, bandes eventuelles sur les cotes.
    CONTAIN = "contain"
    #: Etire sans conserver les proportions.
    STRETCH = "stretch"
    #: Taille d'origine, centree.
    CENTER = "center"
    #: Repete le motif.
    TILE = "tile"

    @property
    def label(self) -> str:
        return {
            FillMode.COVER: "Remplir (rogne)",
            FillMode.CONTAIN: "Ajuster (entier)",
            FillMode.STRETCH: "Etirer",
            FillMode.CENTER: "Centrer",
            FillMode.TILE: "Mosaique",
        }[self]


@dataclass(frozen=True)
class MediaInfo:
    """Metadonnees d'un media, telles que mesurees et non supposees.

    Les champs optionnels valent ``None`` quand l'information n'a pas pu etre
    obtenue : l'interface affiche alors un tiret plutot qu'une valeur inventee.
    """

    path: str
    kind: MediaKind
    width: Optional[int] = None
    height: Optional[int] = None
    #: Duree en secondes pour les videos et images animees.
    duration: Optional[float] = None
    frame_count: Optional[int] = None
    fps: Optional[float] = None
    has_audio: bool = False
    size_bytes: Optional[int] = None
    codec: Optional[str] = None
    #: Message explicatif lorsque l'analyse a echoue.
    error: Optional[str] = None

    @property
    def is_readable(self) -> bool:
        return self.error is None and self.kind is not MediaKind.UNKNOWN

    @property
    def resolution_text(self) -> str:
        if self.width and self.height:
            return f"{self.width} x {self.height}"
        return "-"

    @property
    def duration_text(self) -> str:
        if not self.duration:
            return "-"
        total = int(self.duration)
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

    @property
    def size_text(self) -> str:
        if self.size_bytes is None:
            return "-"
        size = float(self.size_bytes)
        for unit in ("o", "Ko", "Mo", "Go"):
            if size < 1024 or unit == "Go":
                return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
            size /= 1024
        return "-"
