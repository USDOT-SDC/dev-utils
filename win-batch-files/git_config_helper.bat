@echo off
:: Interactive Git Configuration Script
echo =========================================
echo Welcome to the Git Configuration Helper
echo =========================================

:: Ask for user name
set /p gitUserName="Please enter your Git username: {First Last}"

:: Ask for user email
set /p gitUserEmail="Please enter your Git email: {first.last.ctr@dot.gov}"

:: Confirm the entered details
echo.
echo You have entered:
echo Username: %gitUserName%
echo Email: %gitUserEmail%
echo.

:: Ask for confirmation
set /p confirm="Is this correct? (y/n): "

if /i "%confirm%"=="y" (
    :: Apply the git config settings
    git config --global user.name "%gitUserName%"
    git config --global user.email "%gitUserEmail%"
    git config --global core.hooksPath ./.githooks
    
    echo.
    echo Git configuration updated successfully!
) else (
    echo.
    echo Operation canceled. Please rerun the script to try again.
)

:: Pause to keep the command window open
pause
