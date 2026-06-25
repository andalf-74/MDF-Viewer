; Inno Setup script for MDF-Viewer 2.1
; Compile with Inno Setup 6+ from the project root:
;   iscc installer\mdf_viewer.iss
;
; Prerequisites: PyInstaller bundle must already exist at dist\MDF-Viewer\

#define AppName "MDF-Viewer"
#define AppVersion "2.1"
#define AppPublisher "Andreas Maus"
#define AppExeName "MDF-Viewer.exe"

[Setup]
AppId={{A3F2B1C4-7D8E-4F9A-B2C3-D4E5F6A7B8C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
SetupIconFile=..\src\mdf_viewer\resources\icons\app_icon.ico
OutputDir=dist
OutputBaseFilename=MDF-Viewer-2.1-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Install per-user — no UAC prompt required.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "fileassoc_mf4"; Description: "Associate &.mf4 files with {#AppName}"; GroupDescription: "File associations (optional):"; Flags: unchecked
Name: "fileassoc_mdf"; Description: "Associate .&mdf files with {#AppName}"; GroupDescription: "File associations (optional):"; Flags: unchecked

[Files]
Source: "..\dist\MDF-Viewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; .mf4 association
Root: HKCU; Subkey: "Software\Classes\.mf4"; ValueType: string; ValueName: ""; ValueData: "MDF-Viewer.mf4file"; Flags: uninsdeletevalue; Tasks: fileassoc_mf4
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mf4file"; ValueType: string; ValueName: ""; ValueData: "MDF Measurement File"; Flags: uninsdeletekey; Tasks: fileassoc_mf4
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mf4file\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_mf4
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mf4file\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_mf4
; .mdf association
Root: HKCU; Subkey: "Software\Classes\.mdf"; ValueType: string; ValueName: ""; ValueData: "MDF-Viewer.mdffile"; Flags: uninsdeletevalue; Tasks: fileassoc_mdf
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mdffile"; ValueType: string; ValueName: ""; ValueData: "MDF Measurement File"; Flags: uninsdeletekey; Tasks: fileassoc_mdf
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mdffile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_mdf
Root: HKCU; Subkey: "Software\Classes\MDF-Viewer.mdffile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_mdf

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;

procedure SHChangeNotify(wEventId: Longint; uFlags: Longint; dwItem1, dwItem2: Longint);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('fileassoc_mf4') or WizardIsTaskSelected('fileassoc_mdf') then
      SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0);
  end;
end;
