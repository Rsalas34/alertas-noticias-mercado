# Hace que el vigilante arranque solo (oculto) cada vez que inicias sesión en Windows.
# Para quitarlo:  Unregister-ScheduledTask -TaskName "VigilanteNoticias" -Confirm:$false
$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$python  = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command python.exe).Source }

$accion  = New-ScheduledTaskAction -Execute $python -Argument "`"$carpeta\vigilante.py`"" -WorkingDirectory $carpeta
$disparo = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
           -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "VigilanteNoticias" -Action $accion -Trigger $disparo -Settings $ajustes `
    -Description "Alertas de noticias que mueven el mercado (Telegram)" -Force | Out-Null
Start-ScheduledTask -TaskName "VigilanteNoticias"
Write-Host "Listo: el vigilante quedo encendido y arrancara solo cada vez que prendas la PC."
