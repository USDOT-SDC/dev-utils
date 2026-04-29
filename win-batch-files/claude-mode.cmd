@echo off
setlocal enabledelayedexpansion

:: Colors (ANSI - works in Windows Terminal and modern conhost on Win10/11)
for /f "delims=" %%a in ('powershell -NoProfile -Command "[char]27+[char]88"') do set "ESC=%%a"
set "ESC=%ESC:~0,1%"
set "RST=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "DIM=%ESC%[2m"
set "CYAN=%ESC%[96m"
set "GREEN=%ESC%[92m"
set "RED=%ESC%[91m"

:: Config
set "CFGFILE=%~dp0claude-mode.config.cmd"
if not exist "%CFGFILE%" (
    echo.
    echo   %RED%[ERR]%RST%  Config not found.
    echo.
    echo   Expected:  %CFGFILE%
    echo   Template:  %~dp0claude-mode.config.example.cmd
    echo.
    echo   Copy the template, fill in your profiles, and re-run.
    echo.
    pause
    exit /b 1
)
call "%CFGFILE%"

:: Main menu
:MAIN_MENU
set "SEL_PIDX="
cls
echo.
echo   %CYAN%+==========================================+%RST%
echo   %CYAN%^|%RST%  %BOLD%Claude Code -- Mode Switcher%RST%             %CYAN%^|%RST%
echo   %CYAN%+==========================================+%RST%
echo.
if "%CLAUDE_CODE_USE_BEDROCK%"=="1" (
    echo   %DIM%Active :%RST%  %GREEN%Bedrock%RST%  ^(%AWS_PROFILE%  ^|  %AWS_REGION%^)
) else (
    echo   %DIM%Active :%RST%  %GREEN%Anthropic%RST%  ^(claude.ai^)
)
echo.
echo   %BOLD%Select provider:%RST%
echo.
echo   %CYAN%[1]%RST%  Anthropic  %DIM%(claude.ai)%RST%
for /l %%i in (1,1,%CFG_BEDROCK_COUNT%) do (
    set /a "DNUM=%%i+1"
    echo   %CYAN%[!DNUM!]%RST%  !CFG_P%%i_NAME!
)
echo.
echo   %DIM%[Q] Quit%RST%
echo.
set /p "CHOICE=  > "
echo.

if /i "!CHOICE!"=="q" goto :EOF
if "!CHOICE!"=="1" goto :DO_ANTHROPIC

for /l %%i in (1,1,%CFG_BEDROCK_COUNT%) do (
    set /a "DNUM=%%i+1"
    if "!CHOICE!"=="!DNUM!" set "SEL_PIDX=%%i"
)
if defined SEL_PIDX goto :BEDROCK_MODEL_MENU

echo   %RED%Invalid selection.%RST%
timeout /t 1 /nobreak >nul
goto :MAIN_MENU

:: Anthropic
:DO_ANTHROPIC
cls
echo.
echo   %CYAN%+==========================================+%RST%
echo   %CYAN%^|%RST%  %BOLD%Switching to Anthropic%RST%                   %CYAN%^|%RST%
echo   %CYAN%+==========================================+%RST%
echo.
echo   Clearing Bedrock vars  (session + system)...
echo.

set "CLAUDE_CODE_USE_BEDROCK="
set "AWS_PROFILE="
set "AWS_REGION="
set "ANTHROPIC_MODEL="

powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('CLAUDE_CODE_USE_BEDROCK',$null,'User')" >nul 2>&1
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('AWS_PROFILE',$null,'User')" >nul 2>&1
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('AWS_REGION',$null,'User')" >nul 2>&1
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('ANTHROPIC_MODEL',$null,'User')" >nul 2>&1

echo   %GREEN%[OK]%RST%  Bedrock vars removed
echo.
echo   Launching web login...
echo.
claude login
echo.
echo   %DIM%Press any key to return to the menu.%RST%
pause >nul
goto :MAIN_MENU

:: Bedrock -- model selection
:BEDROCK_MODEL_MENU
call set "PNAME=%%CFG_P%SEL_PIDX%_NAME%%"
call set "PMCOUNT=%%CFG_P%SEL_PIDX%_MODEL_COUNT%%"

set "SEL_MODEL_ID="
set "SEL_MODEL_LABEL="

cls
echo.
echo   %CYAN%+------------------------------------------+%RST%
echo   %CYAN%^|%RST%  %BOLD%Select Model%RST%                              %CYAN%^|%RST%
echo   %CYAN%+------------------------------------------+%RST%
echo.
echo   %DIM%Profile:%RST%  %PNAME%
echo.
for /l %%m in (1,1,%PMCOUNT%) do (
    set "MRAW=!CFG_P%SEL_PIDX%_M%%m!"
    for /f "tokens=2 delims=|" %%L in ("!MRAW!") do (
        echo   %CYAN%[%%m]%RST%  %%L
    )
)
echo.
echo   %DIM%[B] Back%RST%
echo.
set /p "MCHOICE=  > "
echo.

if /i "!MCHOICE!"=="b" goto :MAIN_MENU

for /l %%m in (1,1,%PMCOUNT%) do (
    if "!MCHOICE!"=="%%m" (
        set "MRAW=!CFG_P%SEL_PIDX%_M%%m!"
        for /f "tokens=1 delims=|" %%I in ("!MRAW!") do set "SEL_MODEL_ID=%%I"
        for /f "tokens=2 delims=|" %%L in ("!MRAW!") do set "SEL_MODEL_LABEL=%%L"
    )
)

if not defined SEL_MODEL_ID (
    echo   %RED%Invalid selection.%RST%
    timeout /t 1 /nobreak >nul
    goto :BEDROCK_MODEL_MENU
)
goto :DO_BEDROCK

:: Bedrock -- apply settings
:DO_BEDROCK
call set "SEL_AWS_PROFILE=%%CFG_P%SEL_PIDX%_AWS_PROFILE%%"
call set "SEL_REGION=%%CFG_P%SEL_PIDX%_REGION%%"
call set "SEL_PNAME=%%CFG_P%SEL_PIDX%_NAME%%"

cls
echo.
echo   %CYAN%+------------------------------------------+%RST%
echo   %CYAN%^|%RST%  %BOLD%Switching to Bedrock%RST%                     %CYAN%^|%RST%
echo   %CYAN%+------------------------------------------+%RST%
echo.
echo   Profile   :  %SEL_PNAME%
echo   Model     :  %SEL_MODEL_LABEL%
echo   Region    :  %SEL_REGION%
echo   AWS Prof  :  %SEL_AWS_PROFILE%
echo.

set "CLAUDE_CODE_USE_BEDROCK=1"
set "AWS_PROFILE=%SEL_AWS_PROFILE%"
set "AWS_REGION=%SEL_REGION%"
set "ANTHROPIC_MODEL=%SEL_MODEL_ID%"

setx CLAUDE_CODE_USE_BEDROCK "1" >nul
setx AWS_PROFILE "%SEL_AWS_PROFILE%" >nul
setx AWS_REGION "%SEL_REGION%" >nul
setx ANTHROPIC_MODEL "%SEL_MODEL_ID%" >nul

echo   %GREEN%[OK]%RST%  Environment updated  (session + system)
echo.
echo   %DIM%Press any key to return to the menu.%RST%
pause >nul
goto :MAIN_MENU
