@echo off
chcp 65001 > nul
echo ===================================================
echo 📊 배당 및 ETF 공시 모니터링 시스템 종료 스크립트
echo ===================================================
echo.
echo 모니터링 데몬 프로세스를 안전하게 종료하고 있습니다...

wmic process where "commandline like '%%python%%main.py%%'" call terminate > nul 2>&1

echo.
echo ✅ 모니터링 프로세스가 성공적으로 종료되었습니다.
echo.
echo ===================================================
