@echo off
"%~dp0pdf-watermark.exe" --interactive %*
set "result_code=%ERRORLEVEL%"
echo.
pause
exit /b %result_code%
