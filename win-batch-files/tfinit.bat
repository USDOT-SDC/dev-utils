@echo off
if "%1"=="-help" goto print_help
if "%1"=="--help" goto print_help
if "%1"=="" goto print_help
goto normal_start

:print_help
echo Parameter one is environment (dev ^| prod)
echo Parameter two sets an altarnate AWS profile (e.g., default)
echo Example: tfinit dev
echo Example: tfinit prod
echo Example: tfinit dev default
goto end

:normal_start
cls
set env=%1
if "%2"=="" set AWS_PROFILE=%env%
if not "%2"=="" set AWS_PROFILE=%2
set bucket=%env%.sdc.dot.gov.platform.terraform
if "%env%"=="dev" (set options=-upgrade -reconfigure) else (set options=-reconfigure)
echo Would you like to initiaze Terraform?
echo AWS_PROFILE=%AWS_PROFILE%
echo terraform init -backend-config "bucket=%bucket%" %options%
CHOICE /C YC /M "Press Y for Yes, or C to Cancel."
if "%ERRORLEVEL%"=="1" goto init
if "%ERRORLEVEL%"=="2" goto no_init
goto end

:init
terraform init -backend-config "bucket=%bucket%" %options%
goto end

:no_init
echo terraform init canceled
goto end

:end
