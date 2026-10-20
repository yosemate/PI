@echo off
echo ====================================================================
echo   SPECTRUM-LAB v3.0 Fluent Pro - Script de Compilacao PyInstaller
echo ====================================================================
echo.
echo Compilando aplicativo Python PyQt5 para Executavel Standalone Windows (.exe)...
echo.

pyinstaller --noconfirm --windowed --onefile --name "SpectrumLabPro" --add-data "banco_materiais.json;." --add-data "calibracao.json;." main.py

echo.
echo ====================================================================
echo   COMPILACAO CONCLUIDA COM SUCESSO!
echo   O arquivo executavel foi gerado na pasta: dist/SpectrumLabPro.exe
echo ====================================================================
pause
