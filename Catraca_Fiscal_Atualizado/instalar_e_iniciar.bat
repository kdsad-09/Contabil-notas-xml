@echo off
chcp 65001 > nul
cd /d "%~dp0modulo_fiscal_v1-20260929T104928Z-1-001\modulo_fiscal_v1"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Nao foi possivel criar o ambiente. Instale o Python 3.11 ou 3.12 e tente novamente.
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Falha na instalacao. Verifique a conexao e execute este arquivo novamente.
    rmdir /s /q .venv
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m streamlit run app.py
pause
