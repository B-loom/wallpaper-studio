; Script d'installation de Wallpaper Studio (Inno Setup 6)
;
; Construit par scripts/build_installer.py, qui renseigne MyAppVersion et
; MySourceDir. Peut aussi etre compile a la main :
;   ISCC.exe /DMyAppVersion=1.0.0 /DMySourceDir=..\dist\WallpaperStudio installer.iss
;
; Choix retenus :
;  * installation par utilisateur par defaut, donc sans droits administrateur ;
;    l'utilisateur peut tout de meme choisir une installation pour tous ;
;  * le fichier portable.txt n'est pas installe : les donnees vont alors dans
;    %LOCALAPPDATA%\WallpaperStudio, comme pour toute application installee ;
;  * l'application en cours d'execution est fermee avant mise a jour, sinon le
;    remplacement des fichiers echouerait ;
;  * la desinstallation propose d'effacer la bibliotheque et les reglages,
;    mais ne le fait jamais sans accord explicite.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\dist\WallpaperStudio"
#endif

#define MyAppName "Wallpaper Studio"
#define MyAppExeName "WallpaperStudio.exe"
#define MyAppPublisher "B-loom"
#define MyAppURL "https://b-loom.github.io/wallpaper-studio/"
#define MyAppRepo "https://github.com/B-loom/wallpaper-studio"

[Setup]
AppId={{8F3A6C21-5D47-4E9B-9C14-7B2E0A6D3F58}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppRepo}/issues
AppUpdatesURL={#MyAppRepo}/releases

DefaultDirName={autopf}\WallpaperStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; Installation par utilisateur par defaut : aucune elevation demandee.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=..\dist
OutputBaseFilename=WallpaperStudio-Setup-{#MyAppVersion}
SetupIconFile=..\resources\icons\wallpaper-studio.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

; Ferme l'application avant de remplacer ses fichiers.
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

LicenseFile=..\LICENSE

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
french.CreateDesktopIcon=Creer un raccourci sur le Bureau
french.StartWithWindows=Lancer {#MyAppName} au demarrage de Windows
french.LaunchApp=Lancer {#MyAppName}
french.RemoveData=Supprimer aussi la bibliotheque, les reglages et les regles horaires ?
french.OptionalTasks=Taches supplementaires :
english.CreateDesktopIcon=Create a desktop shortcut
english.StartWithWindows=Start {#MyAppName} when Windows starts
english.LaunchApp=Launch {#MyAppName}
english.RemoveData=Also delete the library, settings and schedule rules?
english.OptionalTasks=Additional tasks:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:OptionalTasks}"
Name: "startup"; Description: "{cm:StartWithWindows}"; \
  GroupDescription: "{cm:OptionalTasks}"; Flags: unchecked

[Files]
; Tout le dossier produit par PyInstaller, sauf le marqueur portable et les
; donnees d'essai eventuelles.
Source: "{#MySourceDir}\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "portable.txt,data\*,data"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

[Registry]
; Demarrage automatique, uniquement si la tache est cochee. La cle est celle
; que l'application gere elle-meme depuis ses parametres.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "WallpaperStudio"; \
  ValueData: """{app}\{#MyAppExeName}"" --minimise"; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Journaux et cache regeneres a chaque lancement : rien a conserver.
Type: filesandordirs; Name: "{localappdata}\WallpaperStudio\logs"
Type: filesandordirs; Name: "{localappdata}\WallpaperStudio\cache"
Type: filesandordirs; Name: "{localappdata}\WallpaperStudio\thumbnails"

[Code]
// La desinstallation propose d'effacer les donnees personnelles, sans jamais
// le faire d'office : la bibliotheque et les horaires representent du travail.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DossierDonnees: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DossierDonnees := ExpandConstant('{localappdata}\WallpaperStudio');
    if DirExists(DossierDonnees) then
    begin
      if MsgBox(ExpandConstant('{cm:RemoveData}'),
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DossierDonnees, True, True, True);
    end;
  end;
end;
