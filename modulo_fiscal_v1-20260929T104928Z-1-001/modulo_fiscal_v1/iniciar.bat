@echo off
chcp 65001 > nul
title Catraca Fiscal - Triagem Hikari

echo ========================================================
echo   Iniciando Catraca Fiscal v2 - Hikari Construcoes
echo ========================================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERRO] Ambiente virtual nao encontrado!
    pause
    exit /b 1
)

echo Abrindo aplicacao no navegador...
.venv\Scripts\streamlit.exe run app.py
pause
