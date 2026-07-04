; Inno Setup 6 script for KoeKichi (SPEC §18.5).
;
; Compile after packaging\build_win.bat has produced dist\KoeKichi\KoeKichi.exe:
;   iscc packaging\koekichi.iss
; (or open in the Inno Setup Compiler GUI and press Compile).
;
; Produces dist\KoeKichi-Setup-<ver>.exe.

#define MyAppName "KoeKichi"
#define MyAppVersion "1.3.1"
#define MyAppPublisher "KoeKichi Contributors"
#define MyAppExeName "KoeKichi.exe"

[Setup]
AppId={{6C4B0B8A-6B0F-4E8B-9C1D-3E1B7C6C9F4A}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=KoeKichi-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "startup"; Description: "Windows起動時にKoeKichiを自動的に開始する"; GroupDescription: "追加のタスク:"; Flags: unchecked
; Shown only when an NVIDIA GPU driver is detected (see HasNvidiaGpu below).
; Downloads the CUDA runtime DLLs from PyPI into %LOCALAPPDATA%\KoeKichi\cuda\bin,
; where the app auto-discovers them (no CUDA Toolkit / no command line needed).
Name: "gpudlls"; Description: "NVIDIA GPU 用の高速化ファイルをダウンロードする(約1.4GB・推奨。認識が数倍速くなります)"; GroupDescription: "追加のタスク:"; Check: HasNvidiaGpu

[Files]
; PyInstaller onedir output: dist\KoeKichi\* (KoeKichi.exe + supporting files/DLLs)
Source: "..\dist\KoeKichi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install_gpu_dlls.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\KoeKichi GPU セットアップ"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_gpu_dlls.ps1"""; Comment: "NVIDIA GPU 用の高速化ファイルをダウンロードします"; Check: HasNvidiaGpu
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_gpu_dlls.ps1"""; StatusMsg: "GPU 用の高速化ファイルをダウンロードしています(約1.4GB)..."; Tasks: gpudlls; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; Downloaded GPU DLLs (re-downloadable; keep config/dictionary in %APPDATA%)
Type: filesandordirs; Name: "{localappdata}\KoeKichi\cuda"

[Code]
function HasNvidiaGpu: Boolean;
begin
  { NVIDIA driver ships nvml.dll / nvapi64.dll into System32 }
  Result := FileExists(ExpandConstant('{sys}\nvml.dll')) or
            FileExists(ExpandConstant('{sys}\nvapi64.dll'));
end;
