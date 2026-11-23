@echo off
chcp 65001 >nul
REM Gera o instalador do Soundpad: instalador\saida\SoundpadSetup-2.0.exe
REM Rode no SEU computador (não no do cliente). Precisa de internet na primeira vez.
cd /d "%~dp0.."

set PY=
py -3.13 --version >nul 2>nul && set PY=py -3.13
if not defined PY py -3.12 --version >nul 2>nul && set PY=py -3.12
if not defined PY py -3.11 --version >nul 2>nul && set PY=py -3.11
if not defined PY (
    echo Instale o Python 3.13 ^(py install 3.13^) e rode de novo.
    pause & exit /b 1
)

echo [1/3] Preparando o ambiente de construcao...
if not exist ".venv-build\Scripts\python.exe" %PY% -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || (echo Falha ao instalar dependencias. & pause & exit /b 1)

echo [2/3] Empacotando o programa (Soundpad.exe)...
REM Fecha um Soundpad que esteja rodando (ele fica em segundo plano, sem janela)
REM e apaga a construcao anterior, senao o Windows bloqueia a pasta dist\Soundpad.
taskkill /f /im Soundpad.exe >nul 2>nul
timeout /t 2 /nobreak >nul
if exist "dist\Soundpad" rmdir /s /q "dist\Soundpad" 2>nul
if exist "dist\Soundpad" (
    echo.
    echo Nao consegui apagar a pasta dist\Soundpad: algum programa esta usando ela.
    echo Feche janelas do Explorador abertas nessa pasta e o Soundpad, se estiver aberto,
    echo ou reinicie o computador. Depois rode este arquivo de novo.
    pause & exit /b 1
)
pyinstaller --noconfirm --clean --windowed --name Soundpad ^
  --icon instalador\icone.ico ^
  --add-data "static;static" ^
  --add-data "CAMPAINHA.wav;." ^
  --collect-all edge_tts ^
  --collect-data certifi ^
  --hidden-import pygame._sdl2.audio ^
  --collect-all winrt ^
  app.py || (echo Falha no PyInstaller. & pause & exit /b 1)

echo [3/3] Gerando o instalador...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo.
    echo O programa ja esta pronto em dist\Soundpad\Soundpad.exe,
    echo mas falta o Inno Setup para gerar o instalador.
    echo Instale com:   winget install JRSoftware.InnoSetup
    echo ou baixe em https://jrsoftware.org/isdl.php e rode este arquivo de novo.
    pause & exit /b 1
)
%ISCC% instalador\soundpad.iss || (echo Falha ao gerar o instalador. & pause & exit /b 1)

echo.
echo Pronto! Instalador gerado em: instalador\saida\
explorer instalador\saida
pause
