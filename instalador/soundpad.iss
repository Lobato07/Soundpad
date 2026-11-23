; Instalador do Soundpad (Inno Setup 6).
; Não precisa abrir este arquivo: rode instalador\construir.bat.

#define Produto "Soundpad"
#define Versao "2.0"
#define Exe "Soundpad.exe"

[Setup]
AppId={{6C1E4F7B-3A2D-4B8E-9F21-5D7A0C9B1E42}
AppName={#Produto}
AppVersion={#Versao}
AppVerName={#Produto} {#Versao}
DefaultDirName={autopf}\{#Produto}
DefaultGroupName={#Produto}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=saida
OutputBaseFilename=SoundpadSetup-{#Versao}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\{#Exe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"
Name: "iniciar"; Description: "Ligar o Soundpad junto com o Windows (recomendado)"

[Files]
Source: "..\dist\Soundpad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Produto}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Produto}"; Filename: "{app}\{#Exe}"; Tasks: desktopicon
Name: "{commonstartup}\{#Produto}"; Filename: "{app}\{#Exe}"; Parameters: "--segundo-plano"; Tasks: iniciar

[Run]
; Libera o Soundpad no firewall para os outros computadores da rede conseguirem acessar.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#Produto}"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#Produto}"" dir=in action=allow program=""{app}\{#Exe}"" enable=yes profile=any"; Flags: runhidden
Filename: "{app}\{#Exe}"; Description: "Abrir o Soundpad agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#Exe}"; Flags: runhidden; RunOnceId: "Fechar"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#Produto}"""; Flags: runhidden; RunOnceId: "Firewall"
