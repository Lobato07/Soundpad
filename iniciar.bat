@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM O pygame ainda nao tem instalador pronto para o Python 3.14/3.15,
REM entao procuramos uma versao compativel (3.13, 3.12 ou 3.11).
set PY=
py -3.13 --version >nul 2>nul && set PY=py -3.13
if not defined PY py -3.12 --version >nul 2>nul && set PY=py -3.12
if not defined PY py -3.11 --version >nul 2>nul && set PY=py -3.11

if not defined PY (
    echo.
    echo Nao encontrei o Python 3.13 ^(ou 3.12 / 3.11^) neste computador.
    echo Abra o Prompt de Comando e rode:   py install 3.13
    echo Ou baixe em https://www.python.org/downloads/release/python-3139/
    echo Depois feche esta janela e de dois cliques em iniciar.bat de novo.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo Criando ambiente e instalando dependencias, aguarde...
    %PY% -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

python app.py
pause
