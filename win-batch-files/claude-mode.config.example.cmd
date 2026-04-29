@echo off
:: claude-mode.config.example.cmd
::
:: Copy this file to claude-mode.config.cmd and fill in your values.
:: claude-mode.config.cmd is listed in .gitignore and will not be committed.
::
:: FORMAT
::   Each Bedrock profile is numbered from 1 (CFG_P1_*, CFG_P2_*, ...).
::   Update CFG_BEDROCK_COUNT to match the number of profiles defined below.
::   Anthropic (claude.ai) is always available and does not need a profile entry.
::
:: MODEL IDs  --  AWS Console > Bedrock > Model catalog > copy the Model ID
::   Example: anthropic.claude-sonnet-4-6

set "CFG_BEDROCK_COUNT=2"

:: --- Bedrock Profile 1 ---
set "CFG_P1_NAME=profile-1"
set "CFG_P1_AWS_PROFILE=profile-1"
set "CFG_P1_REGION=us-east-1"
set "CFG_P1_MODEL_COUNT=2"
set "CFG_P1_M1=us.anthropic.claude-sonnet-4-6|Sonnet 4.6"
set "CFG_P1_M2=us.anthropic.claude-opus-4-6-v1|Opus 4.6"

:: --- Bedrock Profile 2 ---
set "CFG_P2_NAME=profile-2"
set "CFG_P2_AWS_PROFILE=profile-2"
set "CFG_P2_REGION=us-east-1"
set "CFG_P2_MODEL_COUNT=2"
set "CFG_P2_M1=us.anthropic.claude-sonnet-4-6|Sonnet 4.6"
set "CFG_P2_M2=us.anthropic.claude-opus-4-6-v1|Opus 4.6"

:: --- Add more profiles as needed ---
:: set "CFG_P3_NAME=profile-3"
:: set "CFG_P3_AWS_PROFILE=profile-3"
:: set "CFG_P3_REGION=us-east-1"
:: set "CFG_P3_MODEL_COUNT=1"
:: set "CFG_P3_M1=us.anthropic.claude-sonnet-4-6|Sonnet 4.6"
:: set "CFG_P3_M2=us.anthropic.claude-opus-4-6-v1|Opus 4.6"
