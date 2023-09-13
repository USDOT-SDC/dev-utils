@echo off
if "%1"=="-help" goto print_help
if "%1"=="--help" goto print_help
goto normal_start

:print_help
echo Parameter one is environment
echo Example: tfinit dev
goto end

:normal_start
set env=%1
echo on
terraform init -backend-config "bucket=%env%.sdc.dot.gov.platform.terraform"

:end
