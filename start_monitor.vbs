Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c venv\Scripts\python.exe main.py", 0, false
