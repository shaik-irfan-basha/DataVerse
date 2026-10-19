$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\DataVerse Studio.lnk")
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Shortcut.TargetPath = "$ScriptDir\run.bat"
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "DataVerse - AI Data Studio"
$Shortcut.Save()
Write-Host "[OK] Created 'DataVerse Studio' shortcut on your Desktop: $DesktopPath\DataVerse Studio.lnk"
