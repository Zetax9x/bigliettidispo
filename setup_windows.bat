@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

echo === Setup Monitor Biglietti TicketOne ===
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Installalo da https://www.python.org/downloads/
    echo        Durante l'installazione spunta "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/4] Python trovato.

:: Installa dipendenze Python
echo [2/4] Installo dipendenze Python...
python -m pip install -r "%SCRIPT_DIR%requirements.txt" --quiet
if errorlevel 1 (
    echo ERRORE durante pip install
    pause
    exit /b 1
)

:: Installa browser Playwright
echo [3/4] Installo browser Chromium per Playwright...
python -m playwright install chromium
if errorlevel 1 (
    echo ERRORE durante playwright install
    pause
    exit /b 1
)

:: Crea il file .env se non esiste
if not exist "%SCRIPT_DIR%.env" (
    echo.
    echo [4/4] Configurazione credenziali Telegram
    echo      Inserisci i tuoi dati (li trovi seguendo le istruzioni nel README)
    echo.
    set /p "BOT_TOKEN=Token del bot Telegram: "
    set /p "CHAT_ID=Chat ID Telegram: "
    (
        echo TELEGRAM_BOT_TOKEN=!BOT_TOKEN!
        echo TELEGRAM_CHAT_ID=!CHAT_ID!
    ) > "%SCRIPT_DIR%.env"
    echo File .env creato.
) else (
    echo [4/4] File .env gia' presente, skippo.
)

:: Registra il Task Scheduler (ogni 5 minuti, anche senza finestra)
echo.
echo Registro il task nel Windows Task Scheduler...
schtasks /delete /tn "MonitorBigliettiTicketOne" /f >nul 2>&1
schtasks /create ^
    /tn "MonitorBigliettiTicketOne" ^
    /tr "\"%SCRIPT_DIR%run.bat\"" ^
    /sc minute /mo 5 ^
    /rl HIGHEST ^
    /f ^
    /ru "%USERNAME%"
if errorlevel 1 (
    echo ATTENZIONE: impossibile registrare il task automaticamente.
    echo Apri Task Scheduler manualmente e crea un task che esegue:
    echo   %SCRIPT_DIR%run.bat
    echo ogni 5 minuti.
) else (
    echo Task registrato con successo!
)

echo.
echo === Setup completato ===
echo Il monitor e' attivo. Verra' eseguito ogni 5 minuti.
echo Log: %SCRIPT_DIR%monitor.log
echo.
echo Per fermarlo: apri Task Scheduler ^> MonitorBigliettiTicketOne ^> Disabilita
echo.
pause
