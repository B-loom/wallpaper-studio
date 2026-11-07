<div align="center">

# Wallpaper Studio

**Animated wallpapers for Windows — video, GIF, images and web, behind your desktop icons.**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c5cff.svg)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-22d3ee.svg)](#requirements)
[![Python](https://img.shields.io/badge/Python-3.11-7c5cff.svg)](#building-from-source)

[Website](https://b-loom.github.io/wallpaper-studio/) ·
[Download](https://github.com/B-loom/wallpaper-studio/releases/latest) ·
[Français](#-français)

</div>

---

## 🇬🇧 English

Wallpaper Studio turns your Windows desktop into something alive: a looping
video, an animated GIF, a still image, or a small web page — and it schedules
them by the hour, so your desktop changes on its own between day and night.

### Why it exists

On **Windows 11 24H2 and later**, most animated-wallpaper tools break. Windows
changed how the desktop is composed (`Progman` now draws through
DirectComposition), and the usual technique silently stops working: the
wallpaper either never shows up, or it covers your desktop icons.

Wallpaper Studio works around this and draws the wallpaper **behind your
icons**, video included. You can verify it on your own machine at any time:

```
WallpaperStudio.exe --diagnostic
```

It shows a test pattern on the desktop, briefly minimises your windows,
captures the screen, restores everything, and tells you whether the wallpaper
is genuinely visible and whether your icons survived.

### Features

**Wallpapers**
- Still images: JPG, PNG, BMP, WEBP, TIFF, ICO
- Animated images: GIF, APNG, animated WEBP
- Video: MP4, MKV, WEBM, MOV, AVI, WMV and more, through libVLC
- Web wallpapers in HTML/CSS/JavaScript, run inside a sandbox
- Five fit modes: fill, fit, stretch, centre, tile

**Scheduling** — the main feature
- As many rules as you like, per display or for every display
- Night ranges that cross midnight are handled correctly (22:00 → 08:00)
- Pick the days of the week, and priorities when ranges overlap
- A change missed while the computer slept is applied on wake-up
- A two-click assistant builds a day / night schedule for you

**Multiple displays**
- Each display keeps its own settings, even after being unplugged
- A different wallpaper per display, the same one everywhere, or one
  panoramic image spread across them

**Library and editing**
- Import files, whole folders, or drag and drop
- Tags, collections, favourites, search and filters
- Editor: brightness, contrast, saturation, hue, blur, rotation, mirrors
- Eight particle effects: rain, snow, stars, fog, glows, waves and more
- Media conversion: video to GIF, frame extraction, re-encoding

**Light on resources** — built for a modest PC
| Situation | RAM | CPU |
|---|---|---|
| Background, no interface | 68 MB | 0 % |
| Window open | 135 MB | ~3 % |
| Window closed, after automatic cleanup | **7 MB** | 0 % |
| Background + still image wallpaper | 26 MB | ~1 % |
| Background + 720p video | 156 MB | ~4.5 % |

The interface is only built when you open it and freed when you close it. The
video player is unloaded as soon as no video is on screen. Wallpapers pause
automatically for fullscreen games, on battery, and when the session is locked.

**Also**
- Interface in English and French, chosen on first launch
- Runs in the background from the notification area
- Starts with Windows, without administrator rights
- Checks GitHub for updates, downloads and installs them on request

### Requirements

- Windows 10 (1809+) or Windows 11, 64-bit
- **VLC 64-bit** installed, for video playback. Images and web wallpapers work
  without it.
- FFmpeg is optional: it improves video thumbnails and enables the converter.

Python is **not** needed to run the released build.

### Installation

Download the latest release from the
[Releases page](https://github.com/B-loom/wallpaper-studio/releases/latest)
and run the installer.

Windows will warn you that the application is not signed by a paid
certificate. Choose **More info** → **Run anyway**.

### Building from source

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --selftest
.venv\Scripts\python.exe main.py
```

Python 3.11 is required: PySide6 6.12 does not yet publish wheels for 3.14.

To build the executable:

```bat
.venv\Scripts\python.exe scripts\build.py --clean
```

Run the test suite (178 tests):

```bat
.venv\Scripts\python.exe -m pytest tests\ -q
```

### Command line

| Command | What it does |
|---|---|
| `WallpaperStudio.exe` | Launches the application |
| `WallpaperStudio.exe --minimise` | Starts in the notification area |
| `WallpaperStudio.exe --selftest` | Checks the environment and exits |
| `WallpaperStudio.exe --diagnostic` | Verifies the wallpaper really shows |
| `WallpaperStudio.exe --debug` | Verbose logging |

### Adding a language

Drop a `resources/lang/<code>.json` file mapping the French source string to
its translation — no code changes needed:

```json
{
  "_meta": {"nom": "Español", "code": "es"},
  "Bibliotheque": "Biblioteca",
  "Horaires": "Horarios"
}
```

Missing strings stay in French rather than leaving gaps in the interface.

### ⚠️ Please read before using

> **This project was written entirely by [Claude](https://claude.com/claude-code), Anthropic's AI assistant.**
> Every line of code, every test and this documentation were produced by it.
> The repository owner published the result but did not write it, and does not
> claim authorship of the engineering behind it.

> **No responsibility is accepted.** The software is provided *as is*, with no
> warranty of any kind. The repository owner is not responsible for anything
> that may happen to your computer, your files, your settings or your desktop:
> crashes, lost wallpapers, display glitches, broken icons, performance
> problems, or anything else. **You use it at your own risk.**

> **It relies on undocumented Windows behaviour.** Drawing behind the desktop
> icons is not something Windows officially supports. A Windows update may
> break it at any time. The application detects this and degrades as gracefully
> as it can, but no fix can be promised.

> **Third-party components keep their own licences.** Qt/PySide6 (LGPL v3),
> libVLC (LGPL v2.1+), Pillow, psutil and FFmpeg. See
> [LICENSES.md](LICENSES.md).

### Licence

[MIT](LICENSE) — do whatever you like with it, keep the copyright notice.

### Documentation

A much more detailed technical document (architecture, Windows internals,
troubleshooting) is available in French:
[DOCUMENTATION.fr.md](DOCUMENTATION.fr.md).

---

## 🇫🇷 Français

Wallpaper Studio transforme votre bureau Windows en quelque chose de vivant :
une vidéo en boucle, un GIF animé, une image fixe ou une petite page web — et
il les programme à l'heure, pour que votre bureau change tout seul entre le
jour et la nuit.

### Pourquoi ce projet existe

Sur **Windows 11 24H2 et suivants**, la plupart des logiciels de fond d'écran
animé ne fonctionnent plus. Windows a changé la façon dont le bureau est
composé (`Progman` dessine désormais via DirectComposition), et la technique
habituelle cesse de marcher sans prévenir : le fond n'apparaît jamais, ou bien
il recouvre les icônes du bureau.

Wallpaper Studio contourne ce problème et affiche le fond **derrière vos
icônes**, vidéo comprise. Vous pouvez le vérifier à tout moment :

```
WallpaperStudio.exe --diagnostic
```

Une mire s'affiche sur le bureau, les fenêtres sont brièvement réduites,
l'écran est capturé, tout est restauré, et le résultat vous dit si le fond est
réellement visible et si vos icônes ont survécu.

### Fonctionnalités

**Fonds d'écran**
- Images fixes : JPG, PNG, BMP, WEBP, TIFF, ICO
- Images animées : GIF, APNG, WEBP animé
- Vidéos : MP4, MKV, WEBM, MOV, AVI, WMV et bien d'autres, via libVLC
- Fonds web en HTML/CSS/JavaScript, exécutés dans un bac à sable
- Cinq modes de cadrage : remplir, ajuster, étirer, centrer, mosaïque

**Programmation horaire** — la fonctionnalité principale
- Autant de règles que vous voulez, par écran ou pour tous
- Les plages de nuit traversant minuit sont gérées correctement (22h00 → 08h00)
- Choix des jours de la semaine et des priorités en cas de chevauchement
- Une transition manquée pendant une mise en veille est rattrapée au réveil
- Un assistant crée un programme jour / nuit en deux clics

**Plusieurs écrans**
- Chaque écran garde ses propres réglages, même après débranchement
- Un fond différent par écran, le même partout, ou une image panoramique
  répartie sur l'ensemble

**Bibliothèque et édition**
- Import par fichier, par dossier ou par glisser-déposer
- Tags, collections, favoris, recherche et filtres
- Éditeur : luminosité, contraste, saturation, teinte, flou, rotation, miroirs
- Huit effets de particules : pluie, neige, étoiles, brouillard, lueurs, ondes
- Conversion de médias : vidéo vers GIF, extraction d'images, réencodage

**Économe en ressources** — pensé pour un PC modeste
| Situation | RAM | CPU |
|---|---|---|
| Arrière-plan, aucune interface | 68 Mo | 0 % |
| Fenêtre ouverte | 135 Mo | ~3 % |
| Fenêtre fermée, après libération automatique | **7 Mo** | 0 % |
| Arrière-plan + fond image fixe | 26 Mo | ~1 % |
| Arrière-plan + vidéo 720p | 156 Mo | ~4,5 % |

L'interface n'est construite qu'à son ouverture et libérée à sa fermeture. Le
lecteur vidéo est déchargé dès qu'aucune vidéo n'est affichée. Les fonds se
mettent en pause automatiquement pour les jeux en plein écran, sur batterie, et
quand la session est verrouillée.

**Également**
- Interface en français et en anglais, choisie au premier lancement
- Fonctionnement en arrière-plan depuis la zone de notification
- Démarrage avec Windows, sans droits administrateur
- Recherche des mises à jour sur GitHub, téléchargement et installation sur demande

### Prérequis

- Windows 10 (1809+) ou Windows 11, 64 bits
- **VLC 64 bits** installé, pour la lecture vidéo. Les images et les fonds web
  fonctionnent sans lui.
- FFmpeg est facultatif : il améliore les vignettes vidéo et active le
  convertisseur.

Python n'est **pas** nécessaire pour utiliser la version publiée.

### Installation

Téléchargez la dernière version depuis la
[page des publications](https://github.com/B-loom/wallpaper-studio/releases/latest)
et lancez l'installateur.

Windows affichera un avertissement, l'application n'étant pas signée par un
certificat payant : choisissez **Informations complémentaires** → **Exécuter
quand même**.

### Compiler depuis les sources

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --selftest
.venv\Scripts\python.exe main.py
```

Python 3.11 est requis : PySide6 6.12 ne publie pas encore de roue pour 3.14.

Pour construire l'exécutable :

```bat
.venv\Scripts\python.exe scripts\build.py --clean
```

Pour lancer les tests (178 tests) :

```bat
.venv\Scripts\python.exe -m pytest tests\ -q
```

### Ligne de commande

| Commande | Effet |
|---|---|
| `WallpaperStudio.exe` | Lance l'application |
| `WallpaperStudio.exe --minimise` | Démarre dans la zone de notification |
| `WallpaperStudio.exe --selftest` | Vérifie l'environnement et quitte |
| `WallpaperStudio.exe --diagnostic` | Vérifie que le fond s'affiche vraiment |
| `WallpaperStudio.exe --debug` | Journalisation détaillée |

### Ajouter une langue

Déposez un fichier `resources/lang/<code>.json` associant la chaîne française à
sa traduction, sans toucher au code :

```json
{
  "_meta": {"nom": "Español", "code": "es"},
  "Bibliotheque": "Biblioteca",
  "Horaires": "Horarios"
}
```

Une chaîne absente reste affichée en français, ce qui évite les trous dans
l'interface.

### ⚠️ À lire avant d'utiliser

> **Ce projet a été entièrement écrit par [Claude](https://claude.com/claude-code), l'assistant IA d'Anthropic.**
> Chaque ligne de code, chaque test et cette documentation ont été produits par
> lui. Le propriétaire du dépôt publie le résultat mais ne l'a pas écrit, et ne
> revendique pas le travail d'ingénierie qu'il y a derrière.

> **Aucune responsabilité n'est assumée.** Le logiciel est fourni *tel quel*,
> sans garantie d'aucune sorte. Le propriétaire du dépôt n'est responsable de
> rien de ce qui pourrait arriver à votre ordinateur, vos fichiers, vos
> réglages ou votre bureau : plantages, fonds perdus, problèmes d'affichage,
> icônes cassées, lenteurs, ou quoi que ce soit d'autre. **Vous l'utilisez à
> vos risques.**

> **Il repose sur un comportement non documenté de Windows.** Dessiner derrière
> les icônes du bureau n'est pas officiellement pris en charge par Windows. Une
> mise à jour de Windows peut casser cela à tout moment. L'application le
> détecte et se dégrade du mieux qu'elle peut, mais aucune correction ne peut
> être promise.

> **Les composants tiers gardent leurs propres licences.** Qt/PySide6 (LGPL v3),
> libVLC (LGPL v2.1+), Pillow, psutil et FFmpeg. Voir
> [LICENSES.md](LICENSES.md).

### Licence

[MIT](LICENSE) — faites-en ce que vous voulez, conservez la mention de
copyright.

### Documentation

Un document technique bien plus détaillé (architecture, rouages de Windows,
résolution des problèmes) est disponible :
[DOCUMENTATION.fr.md](DOCUMENTATION.fr.md).
