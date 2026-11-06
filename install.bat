@echo off
setlocal enabledelayedexpansion
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')"`) do set DOCS=%%D
set FOUND=0
for %%V in (9.0 10.0) do (
  if exist "%DOCS%\KiCad\%%V" (
    set "TARGET=%DOCS%\KiCad\%%V\plugins\kicad-command-palette"
    mkdir "%DOCS%\KiCad\%%V\plugins" 2>nul
    xcopy /E /I /Y "%~dp0kicad-command-palette" "!TARGET!" >nul
    echo Installiert nach !TARGET!
    set FOUND=1
  )
)
if "%FOUND%"=="0" echo Kein KiCad 9.0/10.0 Ordner in "%DOCS%\KiCad" gefunden.
echo.
echo Fertig. In KiCad: Einstellungen ^> Plugins ^> "KiCad-API aktivieren", dann KiCad neu starten.
pause
