@echo off
:: Carica le variabili dal file .env (stesso livello di questo script)
set "SCRIPT_DIR=%~dp0"
for /f "usebackq tokens=1,* delims==" %%A in ("%SCRIPT_DIR%.env") do (
    set "%%A=%%B"
)
:: Esegui lo script Python (nasconde la finestra del terminale)
pythonw "%SCRIPT_DIR%check_tickets.py" >> "%SCRIPT_DIR%monitor.log" 2>&1
