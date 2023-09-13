@echo off
if "%1"=="-help" goto print_help
if "%1"=="--help" goto print_help
goto normal_start

:print_help
echo Parameter one is environment
echo Parameter two is last 2 segments of the IP address
echo Example: ssh_ prod 208.209
goto end

:normal_start
set env=%1
set ip=%2
echo on
ssh -i "%UserProfile%\.ssh\ost-sdc-%env%.pem" ec2-user@10.75.%ip%

:end
