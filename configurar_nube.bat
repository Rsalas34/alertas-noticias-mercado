@echo off
title Conectar el vigilante en la nube
cd /d "%~dp0"
echo.
echo  PASO 1 de 2: Permiso para las tareas automaticas de GitHub
echo  Se abrira tu navegador. Copia el codigo que aparece abajo, pegalo en la pagina y autoriza.
echo.
gh auth refresh -h github.com -s workflow
echo.
echo  PASO 2 de 2: Guardando tu codigo de Telegram como SECRETO en GitHub (nadie lo puede ver)...
python -c "import json;print(json.load(open('secreto.json'))['bot_token'],end='')" | gh secret set TELEGRAM_BOT_TOKEN
python -c "import json;print(json.load(open('secreto.json'))['chat_id'],end='')" | gh secret set TELEGRAM_CHAT_ID
echo.
echo  Listo. Ya puedes cerrar esta ventana y avisarle a Claude.
pause
