; Loom 织流 · Inno Setup 安装包脚本
; 产物：release/Loom-{version}-setup.exe
; 设计要点：
;   1. 装到 %LOCALAPPDATA%\Programs\Loom —— 不需要管理员、不弹 UAC
;   2. 数据在 {app}\data（SQLite + 工作区 + 自建 skill），升级覆盖安装不动它，
;      卸载**默认也不删**——卸载前会问一句，用户明确点头才连数据一起删
;      （删除不可恢复，所以默认路径永远安全，DelTree 只在确认分支里）
;   3. 安装/卸载前都温和关闭正在运行的 Loom（先不带 /F，等不动再强杀）
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
; 别让 Inno 请 RestartManager 去关"占着文件的程序"：那会弹系统级的"正在关闭应用/
; 结束任务"框（2026-09-27 装机实测，一次会话跑了 13 秒）。退出是程序自己的事，
; 见 app/updater.py 的退出钩子与 update.bat 里按 PID 等待那一段。
CloseApplications=no

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
; 装完把程序拉起来 —— 不带 skipifsilent：我们的更新就是 /SILENT 跑的，
; 带上它等于"更新完窗口不会回来"，用户得自己去开始菜单再点一次。
Filename: "{app}\{#MyAppExe}"; Description: "立即启动 {#MyAppName}"; \
  Flags: nowait postinstall runasoriginaluser

[UninstallDelete]
; 只清运行期临时件；data\ 整个目录刻意留着（用户的流程、产物、自建 skill 都在里面）
Type: files; Name: "{app}\data\boot-error.log"

[Code]
var
  RemoveData: Boolean;   /* 卸载时是否连数据一起删；默认 False，只有用户在
                            确认框里点了"是"才为 True —— 见 CurUninstallStepChanged */

/* 安装与卸载共用：温和关闭正在运行的 Loom（先不带 /F，等不动再强杀）。
   数据文件（SQLite/WAL）被进程占着时 DelTree 会留下残骸，所以删除数据前必须先关。 */
procedure KillApp();
var
  ResultCode: Integer;
  I: Integer;
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

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    KillApp();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    KillApp();
    /* 先关程序再问：问的时候用户还能改主意，但程序已经停了 —— 数据文件没被
       占用，两条路（删/留）后面都走得通。措辞必须把"不可恢复"说在前面。 */
    if MsgBox('是否同时删除数据目录？' #13#10 #13#10 +
              '里面是你的流程、运行产物与自建技能，删除后不可恢复。',
              mbConfirmation, MB_YESNO) = IDYES then
      RemoveData := True;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    if RemoveData then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      MsgBox('已卸载，数据目录已一并删除。', mbInformation, MB_OK);
    end
    else
      MsgBox('已卸载。你的流程、产物与自建技能仍保留在 data 文件夹里，' +
             '重装后会自动继续读取。', mbInformation, MB_OK);
  end;
end;
