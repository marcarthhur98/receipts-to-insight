@echo off
REM ===========================================================
REM  setup.bat - one-time environment setup for this project
REM  Creates a virtual environment, installs requirements,
REM  and runs the Stage 1 analyzer to confirm it works.
REM  Run it by typing:   .\setup.bat
REM ===========================================================

echo.
echo [1/4] Creating virtual environment "venv" ...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Could not create the virtual environment.
    echo Make sure Python 3.12 is installed and on your PATH.
    exit /b 1
)

echo.
echo [2/4] Activating the virtual environment ...
call venv\Scripts\activate.bat

echo.
echo [3/4] Installing packages from requirements.txt ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Package installation failed.
    exit /b 1
)

echo.
echo [4/4] Running the Stage 1 analyzer ...
python src\analyzer.py

echo.
echo ===========================================================
echo  Setup complete. The virtual environment is ready.
echo  Next time, just run:   venv\Scripts\activate
echo  then:                  python src\analyzer.py
echo ===========================================================
