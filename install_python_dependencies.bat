@echo off

echo Installing pyfirmata package via pip...
pip install pyfirmata
if %errorlevel% neq 0 (
    echo An error occurred during installation.
) else (
    echo Installation completed successfully.
)

echo Installing tkdial package via pip...
pip install tkdial
if %errorlevel% neq 0 (
    echo An error occurred during installation.
) else (
    echo Installation completed successfully.
)

echo Installing python-benedict package via pip...
pip install python-benedict
if %errorlevel% neq 0 (
    echo An error occurred during installation.
) else (
    echo Installation completed successfully. 
)

echo Installing appdirs package via pip...
pip install appdirs
if %errorlevel% neq 0 (
    echo An error occurred during installation.
) else (
    echo Installation completed successfully. 
)

echo Installing websockets package via pip...
pip install websockets
if %errorlevel% neq 0 (
    echo An error occurred during installation.
) else (
    echo Installation completed successfully. 
)

pause
