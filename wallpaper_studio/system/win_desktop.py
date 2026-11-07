"""Integration du bureau Windows : recherche et utilisation de la couche WorkerW.

Contexte technique
------------------
Sous Windows, l'arriere-plan du bureau est dessine par l'Explorateur. Pour
afficher un contenu anime *derriere les icones*, la technique etablie consiste a
reparenter une fenetre dans une fenetre de classe ``WorkerW`` appartenant a
l'Explorateur. Il n'existe aucune API publique pour cela : le declencheur est un
message non documente (``0x052C``) envoye a ``Progman``, qui demande a
l'Explorateur de creer la couche ``WorkerW``.

Deux agencements existent selon la version de Windows, et ce module gere les
deux :

``LAYOUT_SIBLING`` (Windows 10 et Windows 11 anciens)
    ``SHELLDLL_DefView`` (le conteneur des icones) est l'enfant d'une fenetre
    ``WorkerW`` de premier niveau. Une *seconde* ``WorkerW``, soeur de la
    premiere dans l'ordre Z, sert de support au fond d'ecran.

``LAYOUT_PROGMAN_CHILD`` (Windows 11 24H2 et suivants)
    ``SHELLDLL_DefView`` est directement enfant de ``Progman``, et une fenetre
    ``WorkerW`` enfant de ``Progman`` se place *sous* les icones dans l'ordre Z.
    C'est l'agencement observe sur Windows 11 25H2.

``LAYOUT_PROGMAN_FALLBACK``
    Aucune ``WorkerW`` exploitable : on se rabat sur ``Progman`` lui-meme. Le
    rendu fonctionne mais les icones peuvent scintiller lors d'un rafraichissement.

Limites connues et documentees
------------------------------
* Le message ``0x052C`` n'est pas documente par Microsoft et peut cesser de
  fonctionner lors d'une mise a jour de Windows. Le repli sur ``Progman``
  garantit alors un affichage degrade mais fonctionnel.
* Un redemarrage de ``explorer.exe`` detruit la couche ``WorkerW`` : il faut
  rattacher les fenetres. :func:`host_is_alive` permet de le detecter.
* Un seul logiciel peut occuper confortablement la couche : si Wallpaper Engine
  (ou un equivalent) tourne, les deux rendus se superposent.
* Les fenetres reparentees dans ``WorkerW`` ne recoivent pas les clics souris du
  bureau ; l'interactivite a la souris passe par un suivi global du curseur.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- Constantes Win32 -------------------------------------------------------
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000

WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000

SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

#: Affiche la fenetre sans lui donner le focus.
SW_SHOWNA = 8

#: Opacite uniforme pour une fenetre en couche.
LWA_ALPHA = 0x00000002

HWND_BOTTOM = 1
HWND_TOP = 0

SMTO_NORMAL = 0x0000
SMTO_ABORTIFHUNG = 0x0002

#: Message non documente demandant a Progman de creer la couche WorkerW.
WM_SPAWN_WORKER = 0x052C

GW_CHILD = 5
GW_HWNDNEXT = 2

#: Style etendu signalant qu'une fenetre n'a pas de surface de redirection DWM.
#: Depuis Windows 11 24H2, ``Progman`` le porte : il dessine via
#: DirectComposition, et les fenetres enfants GDI placees dans sa ``WorkerW``
#: ne sont alors **jamais** composees a l'ecran. C'est le critere qui permet de
#: savoir, sans tatonner, que la technique historique est inoperante.
WS_EX_NOREDIRECTIONBITMAP = 0x00200000

LAYOUT_SIBLING = "sibling_workerw"
LAYOUT_PROGMAN_CHILD = "progman_child_workerw"
#: Rendu dans ``SHELLDLL_DefView`` (fenetre en couche, donc composee par DWM).
#: Seule solution sur les Windows 11 recents, mais le contenu passe *devant*
#: les icones du bureau.
LAYOUT_DEFVIEW_OVERLAY = "defview_overlay"
LAYOUT_PROGMAN_FALLBACK = "progman_fallback"

# --- Prototypes -------------------------------------------------------------
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
]
user32.FindWindowExW.restype = wintypes.HWND
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD),
]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.COLORREF, ctypes.c_byte, wintypes.DWORD,
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _GetWindowLong = user32.GetWindowLongPtrW
    _SetWindowLong = user32.SetWindowLongPtrW
else:  # pragma: no cover - Python 32 bits
    _GetWindowLong = user32.GetWindowLongW
    _SetWindowLong = user32.SetWindowLongW
_GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLong.restype = ctypes.c_ssize_t
_SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_SetWindowLong.restype = ctypes.c_ssize_t


# --- Conscience du facteur d'echelle (DPI) ---------------------------------
_DPI_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def enable_dpi_awareness() -> str:
    """Rend le processus conscient du DPI par moniteur.

    Indispensable : sans cela Windows renvoie des coordonnees mises a l'echelle
    et les fenetres de fond d'ecran ne couvrent pas exactement les moniteurs.
    Doit etre appele avant toute creation de fenetre Qt.

    Retourne le mode effectivement obtenu, pour la journalisation.
    """
    try:
        if user32.SetProcessDpiAwarenessContext(_DPI_PER_MONITOR_AWARE_V2):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:  # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:  # Vista+
        user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        return "none"


# --- Utilitaires fenetres ---------------------------------------------------
def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """Rectangle ecran de la fenetre : (gauche, haut, droite, bas)."""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def enum_top_level(predicate: Optional[Callable[[int], bool]] = None) -> List[int]:
    """Enumere les fenetres de premier niveau dans l'ordre Z (avant-plan d'abord)."""
    out: List[int] = []

    def cb(hwnd, _lparam):
        if predicate is None or predicate(hwnd):
            out.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def iter_children(parent: int, limit: int = 64) -> List[int]:
    """Enfants directs de ``parent`` dans l'ordre Z (le plus haut d'abord)."""
    out: List[int] = []
    child = user32.GetWindow(parent, GW_CHILD)
    while child and len(out) < limit:
        out.append(child)
        child = user32.GetWindow(child, GW_HWNDNEXT)
    return out


def virtual_desktop_rect() -> Tuple[int, int, int, int]:
    """Rectangle englobant tous les moniteurs : (x, y, largeur, hauteur).

    L'origine peut etre negative lorsqu'un moniteur est place a gauche ou
    au-dessus du moniteur principal.
    """
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


# --- Recherche de la couche de fond d'ecran --------------------------------
@dataclass(frozen=True)
class WallpaperHost:
    """Fenetre de l'Explorateur servant de support aux fonds d'ecran."""

    hwnd: int
    layout: str
    #: Origine du systeme de coordonnees du support, en pixels ecran.
    origin: Tuple[int, int]

    @property
    def is_fallback(self) -> bool:
        return self.layout == LAYOUT_PROGMAN_FALLBACK

    @property
    def hides_desktop_icons(self) -> bool:
        """Vrai si le contenu recouvre les icones du bureau.

        C'est le cas du rendu dans ``SHELLDLL_DefView`` : la liste d'icones est
        une fenetre unique et opaque, il n'existe aucune place entre le fond et
        les icones ou s'inserer.
        """
        return self.layout == LAYOUT_DEFVIEW_OVERLAY

    def to_local(self, x: int, y: int) -> Tuple[int, int]:
        """Convertit des coordonnees ecran en coordonnees relatives au support."""
        return (x - self.origin[0], y - self.origin[1])


def _poke_progman(progman: int) -> None:
    """Demande a l'Explorateur de materialiser la couche WorkerW.

    Les parametres attendus varient selon les builds de Windows ; on envoie les
    variantes connues, l'Explorateur ignore celles qu'il ne comprend pas.
    """
    result = wintypes.DWORD()
    for wparam, lparam in ((0, 0), (0x0D, 0x01), (0x0D, 0x00)):
        user32.SendMessageTimeoutW(
            progman, WM_SPAWN_WORKER, wparam, lparam,
            SMTO_NORMAL | SMTO_ABORTIFHUNG, 1000, ctypes.byref(result),
        )


def _find_sibling_layout() -> Optional[int]:
    """Agencement Windows 10 : WorkerW soeur de celle qui porte les icones."""
    target: Optional[int] = None

    def cb(hwnd, _lparam):
        nonlocal target
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            if window_class(hwnd) == "WorkerW":
                nxt = user32.FindWindowExW(None, hwnd, "WorkerW", None)
                if nxt:
                    target = nxt
                    return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return target


def _find_progman_child_layout(progman: int) -> Optional[int]:
    """Agencement Windows 11 : WorkerW enfant de Progman, sous les icones.

    On verifie que la ``WorkerW`` se situe bien *apres* ``SHELLDLL_DefView``
    dans l'ordre Z, sinon le contenu masquerait les icones.
    """
    children = iter_children(progman)
    defview_index = next(
        (i for i, h in enumerate(children) if window_class(h) == "SHELLDLL_DefView"),
        None,
    )
    for i, hwnd in enumerate(children):
        if window_class(hwnd) != "WorkerW":
            continue
        if defview_index is None or i > defview_index:
            return hwnd
        log.debug("WorkerW %s ignoree : au-dessus des icones (z=%s)", hwnd, i)
    return None


def workerw_layer_usable() -> bool:
    """Vrai si une fenetre enfant de ``WorkerW`` peut reellement s'afficher.

    Windows 11 24H2 a fait passer ``Progman`` a DirectComposition, ce que
    trahit le style ``WS_EX_NOREDIRECTIONBITMAP``. Dans ce cas, DWM ne compose
    plus les fenetres GDI enfants : elles sont creees, visibles au sens de
    ``IsWindowVisible``, correctement placees dans l'ordre Z... et pourtant
    jamais dessinees. Verifier ce style evite de produire un fond d'ecran
    silencieusement invisible.
    """
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return False
    ex = _GetWindowLong(progman, GWL_EXSTYLE)
    return not bool(ex & WS_EX_NOREDIRECTIONBITMAP)


def find_defview_layer() -> Optional[int]:
    """Fenetre ``SHELLDLL_DefView``, utilisable comme couche de repli.

    Contrairement a ``Progman``, elle porte ``WS_EX_LAYERED`` : DWM la compose,
    et une fenetre enfant placee au sommet de son ordre Z s'affiche donc bien.
    """
    progman = user32.FindWindowW("Progman", None)
    if progman:
        hwnd = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if hwnd:
            return hwnd

    # Agencement Windows 10 : SHELLDLL_DefView vit dans une WorkerW.
    found: Optional[int] = None

    def cb(handle, _lparam):
        nonlocal found
        child = user32.FindWindowExW(handle, None, "SHELLDLL_DefView", None)
        if child:
            found = child
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def find_wallpaper_host(poke: bool = True) -> Optional[WallpaperHost]:
    """Trouve (et cree si besoin) la fenetre support des fonds d'ecran."""
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        log.error("Progman introuvable : l'Explorateur Windows ne tourne pas ?")
        return None

    if poke:
        _poke_progman(progman)

    vx, vy, _, _ = virtual_desktop_rect()

    # La couche WorkerW reste la bonne cible sur toutes les versions de
    # Windows : meme quand Progman passe par DirectComposition (24H2+), une
    # fenetre en couche y est composee correctement et se place sous les
    # icones du bureau. Voir :func:`prepare_wallpaper_window`.
    hwnd = _find_sibling_layout()
    if hwnd:
        log.info("Couche de fond d'ecran : WorkerW soeur hwnd=%s", hwnd)
        # Une WorkerW de premier niveau couvre le bureau virtuel : son origine
        # ecran est celle du bureau virtuel.
        return WallpaperHost(hwnd, LAYOUT_SIBLING, (vx, vy))

    hwnd = _find_progman_child_layout(progman)
    if hwnd:
        log.info("Couche de fond d'ecran : WorkerW enfant de Progman hwnd=%s", hwnd)
        left, top, _, _ = window_rect(hwnd)
        return WallpaperHost(hwnd, LAYOUT_PROGMAN_CHILD, (left, top))

    hwnd = find_defview_layer()
    if hwnd:
        log.warning("Aucune WorkerW exploitable ; rendu via SHELLDLL_DefView")
        left, top, _, _ = window_rect(hwnd)
        return WallpaperHost(hwnd, LAYOUT_DEFVIEW_OVERLAY, (left, top))

    log.warning(
        "Aucune WorkerW exploitable ; repli sur Progman (rendu possiblement degrade)"
    )
    left, top, _, _ = window_rect(progman)
    return WallpaperHost(progman, LAYOUT_PROGMAN_FALLBACK, (left, top))


def host_is_alive(host: Optional[WallpaperHost]) -> bool:
    """Vrai si le support existe toujours (faux apres un redemarrage d'explorer)."""
    return bool(host and user32.IsWindow(host.hwnd))


# --- Rattachement d'une fenetre --------------------------------------------
def prepare_wallpaper_window(hwnd: int) -> None:
    """Applique les styles adaptes a une fenetre de fond d'ecran.

    La fenetre ne doit jamais prendre le focus, ne pas apparaitre dans la barre
    des taches ni dans Alt+Tab, et doit decouper proprement ses enfants (le
    rendu video de VLC est une fenetre enfant).

    ``WS_EX_LAYERED`` est **indispensable** sur Windows 11 24H2 et suivants.
    Depuis ces versions, ``Progman`` dessine via DirectComposition et n'a plus
    de surface de redirection : une fenetre enfant ordinaire placee dans sa
    couche ``WorkerW`` est creee, se declare visible, occupe la bonne position
    dans l'ordre Z... et n'est jamais dessinee. Les fenetres en couche suivent
    un autre chemin de composition dans DWM et s'affichent, elles. C'est
    d'ailleurs ainsi que l'Explorateur affiche ``SHELLDLL_DefView``, lui aussi
    en couche. Le fond apparait alors bien **sous les icones du bureau**.
    """
    style = _GetWindowLong(hwnd, GWL_STYLE)
    style &= ~WS_POPUP
    style |= WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
    _SetWindowLong(hwnd, GWL_STYLE, style)

    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_LAYERED
    ex &= ~WS_EX_APPWINDOW
    _SetWindowLong(hwnd, GWL_EXSTYLE, ex)

    # Alpha 255 : la fenetre reste parfaitement opaque, mais passe par le
    # chemin de composition des fenetres en couche, celui qui fonctionne.
    user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)


def attach_to_host(
    hwnd: int, host: WallpaperHost, rect: Tuple[int, int, int, int]
) -> bool:
    """Reparente ``hwnd`` dans le support et le positionne.

    ``rect`` est exprime en coordonnees ecran : (x, y, largeur, hauteur). La
    conversion vers le repere du support est faite ici.
    """
    if not host_is_alive(host):
        log.error("Support de fond d'ecran invalide")
        return False

    # Ordre important : on reparente D'ABORD, puis on ajuste les styles.
    # Poser WS_CHILD sur une fenetre encore de premier niveau laisse Windows
    # dans un etat incoherent : la fenetre existe, se declare visible, mais
    # n'est jamais composee dans la fenetre parente.
    ctypes.set_last_error(0)
    previous = user32.SetParent(hwnd, host.hwnd)
    if not previous:
        err = ctypes.get_last_error()
        if err:
            log.error("SetParent a echoue (hwnd=%s, erreur=%s)", hwnd, err)
            return False

    prepare_wallpaper_window(hwnd)

    x, y, w, h = rect
    lx, ly = host.to_local(x, y)
    # HWND_TOP place la surface au sommet des enfants du support. Les icones du
    # bureau restent visibles : elles vivent dans SHELLDLL_DefView, qui est au
    # niveau superieur dans les deux agencements geres. Etre au sommet *parmi
    # les enfants* permet en revanche de passer devant un autre gestionnaire de
    # fonds d'ecran qui occuperait deja la couche.
    #
    # SWP_FRAMECHANGED est indispensable : sans lui, Windows conserve le cadre
    # calcule avant le changement de styles et la fenetre n'est jamais dessinee.
    ok = user32.SetWindowPos(
        hwnd, HWND_TOP, lx, ly, w, h,
        SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
    )
    user32.ShowWindow(hwnd, SW_SHOWNA)
    user32.UpdateWindow(hwnd)
    log.info(
        "Fenetre %s rattachee au support %s : ecran=(%s,%s %sx%s) local=(%s,%s)",
        hwnd, host.hwnd, x, y, w, h, lx, ly,
    )
    return bool(ok)


def move_in_host(
    hwnd: int, host: WallpaperHost, rect: Tuple[int, int, int, int]
) -> bool:
    """Repositionne une fenetre deja rattachee (changement de resolution)."""
    x, y, w, h = rect
    lx, ly = host.to_local(x, y)
    return bool(
        user32.SetWindowPos(
            hwnd, None, lx, ly, w, h,
            SWP_NOACTIVATE | SWP_NOZORDER | SWP_SHOWWINDOW,
        )
    )


def detach_from_host(hwnd: int) -> None:
    """Detache une fenetre du support afin de pouvoir la detruire proprement."""
    if user32.IsWindow(hwnd):
        user32.SetParent(hwnd, None)


def refresh_desktop() -> None:
    """Force l'Explorateur a redessiner le bureau (apres detachement)."""
    progman = user32.FindWindowW("Progman", None)
    if progman:
        result = wintypes.DWORD()
        user32.SendMessageTimeoutW(  # WM_PAINT
            progman, 0x000F, 0, 0, SMTO_NORMAL | SMTO_ABORTIFHUNG, 500,
            ctypes.byref(result),
        )


# --- Detection de logiciels concurrents ------------------------------------
#: Classes de fenetres utilisees par d'autres gestionnaires de fonds d'ecran.
_RIVAL_CLASSES = {
    "WPEVideoWallpaper": "Wallpaper Engine",
    "WPEWebWallpaper": "Wallpaper Engine",
    "LivelyWallpaperPlayer": "Lively Wallpaper",
}


def detect_rival_wallpaper_apps() -> List[str]:
    """Noms des autres gestionnaires de fonds d'ecran actuellement actifs.

    Deux logiciels partageant la couche ``WorkerW`` se superposent : l'interface
    s'en sert pour avertir l'utilisateur plutot que de laisser croire a un bug.
    """
    found: List[str] = []

    def scan(parent: int) -> None:
        for child in iter_children(parent):
            name = _RIVAL_CLASSES.get(window_class(child))
            if name and name not in found:
                found.append(name)

    progman = user32.FindWindowW("Progman", None)
    if progman:
        scan(progman)
        for child in iter_children(progman):
            if window_class(child) == "WorkerW":
                scan(child)
    for hwnd in enum_top_level(lambda h: window_class(h) == "WorkerW"):
        scan(hwnd)
    return found
