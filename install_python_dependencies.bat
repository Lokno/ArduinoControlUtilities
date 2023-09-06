@echo off
echo Installing pyfirmata and tkdial packages via pip...
pip install pyfirmata tkdial
if %errorlevel% neq 0 (
    echo An error occurred during installation.
    pause
) else (
    echo Installation completed successfully.
    pause
)