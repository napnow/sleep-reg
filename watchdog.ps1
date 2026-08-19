$proc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*auto_register_agent*' }
if (-not $proc) {
    Start-Process -FilePath "python" -ArgumentList "auto_register_agent.py" -WorkingDirectory "D:\cpa\chatgpt-register-cpa" -WindowStyle Minimized
}
