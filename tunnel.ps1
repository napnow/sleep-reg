$proc = Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" | Where-Object { $_.CommandLine -like '*10808*39.96.1.106*' }
if (-not $proc) {
    Start-Process -FilePath "ssh.exe" -ArgumentList "-o","StrictHostKeyChecking=no","-o","ServerAliveInterval=30","-o","ExitOnForwardFailure=yes","-N","-R","10808:127.0.0.1:10808","root@39.96.1.106" -WindowStyle Hidden
}
