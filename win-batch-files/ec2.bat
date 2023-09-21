@echo off
if "%1"=="-help" goto print_help
if "%1"=="--help" goto print_help
if "%1"=="list" goto list
if "%1"=="start" goto start
exit /B 1

:print_help
echo Parameter one is action (list, start)
echo Parameter two is ID. Instance name (tag:Name), wildcard allowed
echo Example: ec2 start ECSDWART01
goto :eof

:list
set action=%1
set name=%2
aws ec2 describe-instances --output table --filters "Name=tag:Name,Values=%name%" --query "Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,IP:PrivateIpAddress,Tags:Tags[*]}"
goto :eof

:start
set action=%1
set name=%2
FOR /F "tokens=*" %%g IN ('aws ec2 describe-instances --output text --filters "Name=tag:Name,Values=%name%" --query "Reservations[].Instances[].InstanceId"') do (SET instance_ids=%%g)
aws ec2 start-instances --output table --instance-ids %instance_ids% --query "StartingInstances[].{ID:InstanceId,Currently:CurrentState.Name,Previously:PreviousState.Name}
goto :eof
