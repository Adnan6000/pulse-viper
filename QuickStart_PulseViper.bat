@echo off
REM Quick start for PulseViper:
REM   * Skips MT5/broker pre-flight check (engine still connects MT5 normally)
REM   * Does NOT auto-open browser tab (avoids any IDE/browser hijack behavior)
title PulseViper QuickStart
call "%~dp0start_pulse_viper.bat" --skip-mt5 --no-browser --mode scalping --interval 15 --symbols XAUUSDm %*
