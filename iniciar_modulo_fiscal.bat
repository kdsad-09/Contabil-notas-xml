@echo off
chcp 65001 > nul
title Catraca Fiscal - Triagem Hikari

echo ========================================================
echo   Iniciando Catraca Fiscal v2 - Hikari Construcoes
echo ========================================================
echo.

cd /d "%~dp0modulo_fiscal_v1-20260929T104928Z-1-001\modulo_fiscal_v1"

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERRO] Ambiente virtual nao encontrado!
    echo Execute a instalacao de dependencias antes de iniciar.
    pause
    exit /b 1
)

echo Abrindo aplicacao no navegador...
.venv\Scripts\streamlit.exe run app.py
pause
