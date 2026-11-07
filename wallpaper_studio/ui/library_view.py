"""Bibliotheque : import, recherche, filtres, collections et application."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..data.models import MediaItem
from ..data.settings import IMPORT_COPIER, IMPORT_DEMANDER, IMPORT_REFERENCER
from ..media.probe import probe_media, scan_folder
from ..media.thumbnails import generate_thumbnail
from ..media.types import MediaKind, file_dialog_filter
from .theme import icon
from .widgets.common import FlowLayout, MediaCard

log = logging.getLogger(__name__)


class ImportWorker(QThread):
    """Analyse et enregistre les fichiers importes sans figer l'interface."""

    progress = Signal(int, int, str)
    finished_import = Signal(int, list)

    def __init__(self, paths: List[Path], repos, copy_into_library: bool,
                 library_dir: Path, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._repos = repos
        self._copy = copy_into_library
        self._library = Path(library_dir)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        added = 0
        errors: List[str] = []
        total = len(self._paths)

        for index, source in enumerate(self._paths, start=1):
            if self._cancelled:
                break
            self.progress.emit(index, total, source.name)
            try:
                info = probe_media(source)
                if not info.is_readable:
                    errors.append(f"{source.name} : {info.error or 'format inconnu'}")
                    continue

                final = source
                original: Optional[str] = None
                if self._copy:
                    self._library.mkdir(parents=True, exist_ok=True)
                    target = self._library / source.name
                    counter = 1
                    while target.exists() and target != source:
                        target = self._library / f"{source.stem}_{counter}{source.suffix}"
                        counter += 1
                    if target != source:
                        import shutil

                        shutil.copy2(source, target)
                        original = str(source)
                        final = target

                thumb = generate_thumbnail(final, info.kind)
                self._repos.media.add(
                    MediaItem(
                        path=str(final),
                        title=final.stem,
                        kind=info.kind,
                        width=info.width,
                        height=info.height,
                        duration=info.duration,
                        fps=info.fps,
                        has_audio=info.has_audio,
                        size_bytes=info.size_bytes,
                        codec=info.codec,
                        thumbnail=str(thumb) if thumb else None,
                        source_path=original,
                    )
                )
                added += 1
            except Exception as exc:  # noqa: BLE001 - import tolerant aux erreurs
                log.exception("Import impossible : %s", source)
                errors.append(f"{source.name} : {exc}")

        self.finished_import.emit(added, errors)


class LibraryView(QWidget):
    """Page Bibliotheque."""

    apply_requested = Signal(object)          # MediaItem
    preview_requested = Signal(object)        # MediaItem
    edit_requested = Signal(object)           # MediaItem
    schedule_requested = Signal(object)       # MediaItem
    notify = Signal(str, str)                 # message, type

    SORTS = [
        ("Date d'ajout", "added_at", True),
        ("Nom (A-Z)", "title", False),
        ("Derniere utilisation", "last_used_at", True),
        ("Le plus utilise", "use_count", True),
        ("Duree", "duration", True),
        ("Resolution", "width", True),
        ("Taille du fichier", "size_bytes", True),
    ]

    KIND_FILTERS = [
        ("Tous les types", None),
        ("Images", [MediaKind.IMAGE]),
        ("Images animees", [MediaKind.ANIMATED_IMAGE]),
        ("Videos", [MediaKind.VIDEO]),
        ("Fonds web", [MediaKind.WEB]),
    ]

    def __init__(self, repos, settings, parent=None):
        super().__init__(parent)
        self._repos = repos
        self._settings = settings
        self._cards: Dict[int, MediaCard] = {}
        self._selected: Optional[MediaItem] = None
        self._worker: Optional[ImportWorker] = None
        self._build()
        self.refresh()

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Bibliotheque")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._btn_files = QPushButton("  Importer des fichiers")
        self._btn_files.setIcon(icon("importer"))
        self._btn_files.clicked.connect(self.import_files)
        header.addWidget(self._btn_files)

        self._btn_folder = QPushButton("  Importer un dossier")
        self._btn_folder.setIcon(icon("dossier"))
        self._btn_folder.clicked.connect(self.import_folder)
        header.addWidget(self._btn_folder)
        root.addLayout(header)

        # --- Barre de filtres ---
        filters = QHBoxLayout()
        filters.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher par nom ou chemin...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self.refresh)
        self._search.setMinimumWidth(240)
        filters.addWidget(self._search, 2)

        self._kind = QComboBox()
        for label, _ in self.KIND_FILTERS:
            self._kind.addItem(label)
        self._kind.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._kind)

        self._collection = QComboBox()
        self._collection.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._collection)

        self._tag = QComboBox()
        self._tag.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._tag)

        self._sort = QComboBox()
        for label, _, _ in self.SORTS:
            self._sort.addItem(label)
        self._sort.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._sort)

        self._fav_only = QPushButton("  Favoris")
        self._fav_only.setIcon(icon("etoile"))
        self._fav_only.setCheckable(True)
        self._fav_only.toggled.connect(self.refresh)
        filters.addWidget(self._fav_only)
        root.addLayout(filters)

        # --- Grille ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        container = QWidget()
        self._flow = FlowLayout(container, margin=2, spacing=12)
        self._scroll.setWidget(container)
        root.addWidget(self._scroll, 1)

        # --- Pied de page ---
        footer = QHBoxLayout()
        self._status = QLabel()
        self._status.setObjectName("hint")
        footer.addWidget(self._status)
        footer.addStretch(1)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(240)
        self._progress.hide()
        footer.addWidget(self._progress)

        self._btn_collection = QPushButton("Nouvelle collection")
        self._btn_collection.setObjectName("ghost")
        self._btn_collection.clicked.connect(self._create_collection)
        footer.addWidget(self._btn_collection)

        self._btn_check = QPushButton("Verifier les fichiers")
        self._btn_check.setObjectName("ghost")
        self._btn_check.clicked.connect(self._check_missing)
        footer.addWidget(self._btn_check)
        root.addLayout(footer)

        self.setAcceptDrops(True)

    # --- Glisser-deposer ---------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - API Qt
        paths: List[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            p = Path(local)
            if p.is_dir():
                paths.extend(scan_folder(p))
            else:
                paths.append(p)
        if paths:
            self._start_import(paths)
        event.acceptProposedAction()

    # --- Import ------------------------------------------------------------
    def import_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des fonds d'ecran", "", file_dialog_filter()
        )
        if files:
            self._start_import([Path(f) for f in files])

    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if not folder:
            return
        found = scan_folder(folder)
        if not found:
            self.notify.emit("Aucun media compatible dans ce dossier.", "alerte")
            return
        self._start_import(found)

    def _ask_copy_mode(self, count: int) -> Optional[bool]:
        """Demande si les fichiers doivent etre copies. ``None`` = annule."""
        mode = self._settings.get("mode_import", IMPORT_DEMANDER)
        if mode == IMPORT_COPIER:
            return True
        if mode == IMPORT_REFERENCER:
            return False

        box = QMessageBox(self)
        box.setWindowTitle("Mode d'importation")
        box.setText(f"Comment importer ces {count} fichier(s) ?")
        box.setInformativeText(
            "« Referencer » laisse vos fichiers ou ils sont : rien n'est duplique, "
            "mais deplacer un fichier le rendra introuvable.\n\n"
            "« Copier » place une copie dans le dossier de la bibliotheque : "
            "cela occupe davantage d'espace disque."
        )
        reference = box.addButton("Referencer (recommande)", QMessageBox.AcceptRole)
        copy = box.addButton("Copier dans la bibliotheque", QMessageBox.AcceptRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is reference:
            return False
        if clicked is copy:
            return True
        return None

    def _start_import(self, paths: List[Path]) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.notify.emit("Une importation est deja en cours.", "alerte")
            return

        copy = self._ask_copy_mode(len(paths))
        if copy is None:
            return

        self._progress.setRange(0, len(paths))
        self._progress.setValue(0)
        self._progress.show()
        self._btn_files.setEnabled(False)
        self._btn_folder.setEnabled(False)

        self._worker = ImportWorker(
            paths, self._repos, copy, Path(self._settings.get("dossier_bibliotheque"))
        )
        self._worker.progress.connect(self._on_import_progress)
        self._worker.finished_import.connect(self._on_import_done)
        self._worker.start()

    def _on_import_progress(self, done: int, total: int, name: str) -> None:
        self._progress.setValue(done)
        self._status.setText(f"Importation {done}/{total} : {name}")

    def _on_import_done(self, added: int, errors: List[str]) -> None:
        self._progress.hide()
        self._btn_files.setEnabled(True)
        self._btn_folder.setEnabled(True)
        self.refresh()

        if errors:
            message = f"{added} fond(s) importe(s), {len(errors)} echec(s)."
            self.notify.emit(message, "alerte")
            QMessageBox.warning(
                self, "Importation partielle",
                message + "\n\n" + "\n".join(errors[:12])
                + ("\n..." if len(errors) > 12 else ""),
            )
        elif added:
            self.notify.emit(f"{added} fond(s) ajoute(s) a la bibliotheque.", "succes")
        else:
            self.notify.emit("Aucun fond importe.", "alerte")

    # --- Affichage ---------------------------------------------------------
    def _reload_filters(self) -> None:
        """Recharge collections et tags en conservant la selection."""
        for combo, items, first in (
            (self._collection, self._repos.collections.list(), "Toutes les collections"),
            (self._tag, self._repos.media.all_tags(), "Tous les tags"),
        ):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, None)
            for item in items:
                if hasattr(item, "name"):
                    combo.addItem(f"{item.name} ({item.count})", item.id)
                else:
                    combo.addItem(item, item)
            index = combo.findData(previous)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)

    def refresh(self) -> None:
        """Recharge la grille selon les filtres courants."""
        self._reload_filters()

        label, order, desc = self.SORTS[max(0, self._sort.currentIndex())]
        kinds = self.KIND_FILTERS[max(0, self._kind.currentIndex())][1]

        items = self._repos.media.list(
            search=self._search.text().strip(),
            kinds=kinds,
            favorites_only=self._fav_only.isChecked(),
            collection_id=self._collection.currentData(),
            tag=self._tag.currentData(),
            order_by=order,
            descending=desc,
        )

        while self._flow.count():
            item = self._flow.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        for media in items:
            media.tags = self._repos.media.tags_for(media.id)
            card = MediaCard(media, self._settings.get("theme", "sombre"))
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(self.apply_requested.emit)
            card.favorite_toggled.connect(self._toggle_favorite)
            card.context_requested.connect(self._show_menu)
            self._flow.addWidget(card)
            self._cards[media.id] = card

        total = self._repos.media.count()
        missing = self._repos.media.count_missing()
        text = f"{len(items)} fond(s) affiche(s) sur {total} dans la bibliotheque"
        if missing:
            text += f"  -  {missing} fichier(s) introuvable(s)"
        self._status.setText(text)

    def _on_card_clicked(self, item: MediaItem) -> None:
        self._selected = item
        for media_id, card in self._cards.items():
            card.set_selected(media_id == item.id)
        self.preview_requested.emit(item)

    def _toggle_favorite(self, item: MediaItem) -> None:
        self._repos.media.set_favorite(item.id, not item.favorite)
        item.favorite = not item.favorite
        card = self._cards.get(item.id)
        if card:
            card.update_item(item)

    # --- Menu contextuel ---------------------------------------------------
    def _show_menu(self, item: MediaItem, position: QPoint) -> None:
        menu = QMenu(self)

        menu.addAction("Appliquer maintenant", lambda: self.apply_requested.emit(item))
        menu.addAction("Previsualiser", lambda: self.preview_requested.emit(item))
        menu.addAction("Modifier dans l'editeur", lambda: self.edit_requested.emit(item))
        menu.addAction("Programmer un horaire", lambda: self.schedule_requested.emit(item))
        menu.addSeparator()

        menu.addAction(
            "Retirer des favoris" if item.favorite else "Ajouter aux favoris",
            lambda: self._toggle_favorite(item),
        )
        menu.addAction("Renommer...", lambda: self._rename(item))
        menu.addAction("Modifier les tags...", lambda: self._edit_tags(item))

        collections = self._repos.collections.list()
        if collections:
            submenu = menu.addMenu("Ajouter a une collection")
            for collection in collections:
                submenu.addAction(
                    collection.name,
                    lambda _=False, c=collection.id: self._add_to_collection(item, c),
                )

        menu.addAction("Convertir...", lambda: self._convert(item))

        menu.addSeparator()
        menu.addAction("Ouvrir l'emplacement du fichier", lambda: self._reveal(item))
        menu.addAction("Copier le chemin", lambda: self._copy_path(item))
        menu.addSeparator()

        remove = QAction("Retirer de la bibliotheque", menu)
        remove.triggered.connect(lambda: self._remove(item, delete_file=False))
        menu.addAction(remove)

        delete = QAction("Supprimer le fichier du disque...", menu)
        delete.triggered.connect(lambda: self._remove(item, delete_file=True))
        menu.addAction(delete)

        menu.exec(position)

    def _rename(self, item: MediaItem) -> None:
        name, ok = QInputDialog.getText(
            self, "Renommer", "Nouveau nom :", text=item.title
        )
        if ok and name.strip():
            self._repos.media.rename(item.id, name.strip())
            self.refresh()

    def _edit_tags(self, item: MediaItem) -> None:
        current = ", ".join(self._repos.media.tags_for(item.id))
        text, ok = QInputDialog.getText(
            self, "Tags", "Tags separes par des virgules :", text=current
        )
        if ok:
            self._repos.media.set_tags(item.id, [t.strip() for t in text.split(",")])
            self.refresh()

    def _add_to_collection(self, item: MediaItem, collection_id: int) -> None:
        self._repos.collections.add_media(collection_id, item.id)
        self.notify.emit(f"« {item.title} » ajoute a la collection.", "succes")
        self.refresh()

    def _create_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvelle collection", "Nom :")
        if ok and name.strip():
            self._repos.collections.create(name.strip())
            self.refresh()

    def _convert(self, item: MediaItem) -> None:
        """Ouvre la boite de conversion et importe le resultat si l'utilisateur le veut."""
        from .convert_dialog import ConvertDialog

        if item.missing:
            self.notify.emit("Le fichier source est introuvable.", "erreur")
            return

        dialog = ConvertDialog(Path(item.path), item.kind, parent=self)
        dialog.converted.connect(self._import_converted)
        dialog.exec()

    def _import_converted(self, produced) -> None:
        """Propose d'ajouter a la bibliotheque le fichier qui vient d'etre cree."""
        produced = Path(produced)
        if not produced.is_file():
            # Une extraction d'images produit un dossier : rien a importer tel quel.
            self.notify.emit(f"Resultat enregistre dans {produced}", "succes")
            return
        answer = QMessageBox.question(
            self, "Ajouter a la bibliotheque",
            f"Ajouter « {produced.name} » a votre bibliotheque ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._start_import([produced])

    def _reveal(self, item: MediaItem) -> None:
        import subprocess

        path = Path(item.path)
        if not path.exists():
            self.notify.emit("Le fichier n'existe plus.", "erreur")
            return
        # /select, met le fichier en surbrillance dans l'Explorateur.
        subprocess.Popen(["explorer", "/select,", str(path)])

    def _copy_path(self, item: MediaItem) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(item.path)
        self.notify.emit("Chemin copie dans le presse-papiers.", "succes")

    def _remove(self, item: MediaItem, delete_file: bool) -> None:
        if delete_file:
            answer = QMessageBox.question(
                self, "Supprimer le fichier",
                f"Supprimer definitivement « {item.title} » du disque ?\n\n"
                f"{item.path}\n\nCette action est irreversible.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        elif self._settings.get("confirmer_suppression", True):
            answer = QMessageBox.question(
                self, "Retirer de la bibliotheque",
                f"Retirer « {item.title} » de la bibliotheque ?\n\n"
                "Le fichier d'origine ne sera pas supprime.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        self._repos.media.remove(item.id, delete_file=delete_file)
        self.refresh()
        self.notify.emit(
            "Fichier supprime." if delete_file else "Entree retiree de la bibliotheque.",
            "succes",
        )

    def _check_missing(self) -> None:
        missing = self._repos.media.refresh_missing_flags()
        self.refresh()
        if missing:
            self.notify.emit(
                f"{len(missing)} fichier(s) introuvable(s) signale(s).", "alerte"
            )
        else:
            self.notify.emit("Tous les fichiers de la bibliotheque sont presents.", "succes")

    def selected_item(self) -> Optional[MediaItem]:
        return self._selected
