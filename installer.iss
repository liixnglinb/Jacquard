; Loom 织流 · Inno Setup 安装包脚本
; 产物：release/Loom-{version}-setup.exe
; 设计要点：
;   1. 装到 %LOCALAPPDATA%\Programs\Loom —— 不需要管理员、不弹 UAC
;   2. 数据在 {app}\data（SQLite + 工作区 + 自建 skill），升级覆盖安装不动它，
;      卸载也不删它 —— 用户的流程和产物比程序值钱
;   3. 安装前温和关闭正在运行的 Loom（先不带 /F，等不动再强杀）
;   4. 卸载后残留的 data/ 在卸载页给一句明确提示，别让人以为数据没了

#define MyAppName "织流 Jacquard"
#define MyAppExe "Loom.exe"
#define MyAppPublisher "liixnglinb"
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{7C1D4E9A-2B6F-4C38-9A51-LOOMFLOW0100}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Loom
UsePreviousAppDir=yes
DirExistsWarning=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=Loom-{#MyAppVersion}-setup
SetupIconFile=assets\loom.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
RestartApplications=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExe}
CloseApplications=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "startmenuicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce unchecked

[Files]
Source: "dist_app\Loom\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "立即启动 {#MyAppName}"; \
  Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
; 只清运行期临时件；data\ 整个目录刻意留着（用户的流程、产物、自建 skill 都在里面）
Type: files; Name: "{app}\data\boot-error.log"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  I: Integer;
begin
  if CurStep = ssInstall then
  begin
    Exec(ExpandConstant('{cmd}'), '/C taskkill /IM {#MyAppExe} /T',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    for I := 1 to 6 do
    begin
      if Exec(ExpandConstant('{cmd}'),
              '/C tasklist /FI "IMAGENAME eq {#MyAppExe}" | find /I "{#MyAppExe}"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        if ResultCode <> 0 then
          Break;              // find 没匹配到 = 已经退出了
      end;
      Sleep(500);
    end;
    Exec(ExpandConstant('{cmd}'), '/C taskkill /IM {#MyAppExe} /T /F',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('已卸载。你的流程、产物与自建技能仍保留在 data 文件夹里，' +
           '重装后会自动继续读取。', mbInformation, MB_OK);
end;
