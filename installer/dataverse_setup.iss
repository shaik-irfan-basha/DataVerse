
; =============================================================================
; DataVerse - Inno Setup Installer Script
; Produces DataVerse_Setup_v1.0.exe
; =============================================================================

#define MyAppName "DataVerse"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Shaik Irfan Basha"
#define MyAppURL "https://github.com/shaik-irfan-basha/DataVerse"
#define MyAppExeName "DataVerse.exe"

[Setup]
; Unique GUID identifying DataVerse across version updates
AppId={{D47A9E82-3A2B-4F1C-9E6D-5B8F7C0D2E1A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=output
OutputBaseFilename=DataVerse_Setup_v1.0
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline dialog
CloseApplications=yes
CloseApplicationsFilter=DataVerse.exe
RestartIfNeededByRun=no

; Visual Branding
SetupIconFile=dataverse.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Distributable application binaries from PyInstaller onedir output
Source: "..\dist\DataVerse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Explicitly install the MIT license in the application directory
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#StringChange(MyAppName, '&', '&&')}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// =============================================================================
// WebView2 Runtime Detection & Prerequisite Verification
// =============================================================================

function IsWebView2Installed(): Boolean;
var
  VersionStr: String;
  Clients: array of String;
  I: Integer;
begin
  Result := False;
  SetArrayLength(Clients, 4);
  Clients[0] := '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Clients[1] := '{F3017226-F501-47EC-A024-60F42E0E4887}';
  Clients[2] := '{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}';
  Clients[3] := '{2CD8A072-E409-4E61-A76D-2F5A0693E2B5}';

  for I := 0 to 3 do
  begin
    // 1. Check 64-bit WOW6432Node
    if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + Clients[I], 'pv', VersionStr) then
    begin
      if (Length(VersionStr) > 0) and (VersionStr <> '0.0.0.0') then
      begin
        Result := True;
        Exit;
      end;
    end;

    // 2. Check 32-bit / Native HKLM
    if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + Clients[I], 'pv', VersionStr) then
    begin
      if (Length(VersionStr) > 0) and (VersionStr <> '0.0.0.0') then
      begin
        Result := True;
        Exit;
      end;
    end;

    // 3. Check HKCU (Per-user WebView2 installs)
    if RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + Clients[I], 'pv', VersionStr) then
    begin
      if (Length(VersionStr) > 0) and (VersionStr <> '0.0.0.0') then
      begin
        Result := True;
        Exit;
      end;
    end;
  end;
end;

function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;

  // Verify WebView2 Runtime presence (interactive mode only)
  if not WizardSilent() then
  begin
    if not IsWebView2Installed() then
    begin
      if SuppressibleMsgBox(
        'DataVerse requires the Microsoft Edge WebView2 Runtime to display its desktop studio interface.' + #13#10 + #13#10 +
        'WebView2 was not detected on this system. Would you like to open the official Microsoft download page now to install it?',
        mbConfirmation, MB_YESNO, IDNO
      ) = IDYES then
      begin
        ShellExec('open', 'https://go.microsoft.com/fwlink/p/?LinkId=2124703', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
      end;
      // Allow installation to continue; user can install WebView2 before first launch
    end;
  end;
end;

// =============================================================================
// Upgrade & Uninstall Policy
// =============================================================================
// User databases and query history are stored in %LOCALAPPDATA%\DataVerse.
// They are preserved during upgrades so users do not lose their data.
// On complete uninstallation, optionally offer to clean user data.

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Only prompt in interactive uninstall mode; never delete user data during silent uninstall
    if not UninstallSilent() then
    begin
      UserDataPath := ExpandConstant('{localappdata}\DataVerse');
      if DirExists(UserDataPath) then
      begin
        if SuppressibleMsgBox(
          'Would you also like to delete all saved DataVerse query histories and metadata in: ' + #13#10 +
          UserDataPath + '?' + #13#10 + #13#10 +
          'Choose No if you plan to reinstall DataVerse in the future.',
          mbConfirmation, MB_YESNO, IDNO
        ) = IDYES then
        begin
          DelTree(UserDataPath, True, True, True);
        end;
      end;
    end;
  end;
end;
