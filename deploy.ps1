# Quick deployment script for Pi Cluster
# Copies all necessary files to the Raspberry Pi

Write-Host "Deploying to Pi Cluster..." -ForegroundColor Cyan
Write-Host ""

# Main algorithm
Write-Host "[1/5] Deploying main.py..." -ForegroundColor Yellow
scp main.py pi@raspberrypi:/home/pi/main.py

# Visualization server
Write-Host "[2/5] Deploying viz_server.py..." -ForegroundColor Yellow
scp viz_server.py pi@raspberrypi:/home/pi/viz_server.py

# UI files
Write-Host "[3/5] Deploying UI HTML..." -ForegroundColor Yellow
scp ui/index.html pi@raspberrypi:/home/pi/ui/index.html

Write-Host "[4/5] Deploying UI CSS..." -ForegroundColor Yellow
scp ui/style.css pi@raspberrypi:/home/pi/ui/style.css
scp ui/mobile.css pi@raspberrypi:/home/pi/ui/mobile.css

Write-Host "[5/5] Deploying UI JavaScript..." -ForegroundColor Yellow
scp ui/script.js pi@raspberrypi:/home/pi/ui/script.js

Write-Host ""
Write-Host "✓ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Restarting viz_server on Pi..." -ForegroundColor Cyan
ssh pi@raspberrypi "pkill -f viz_server.py; cd /home/pi && source spark-env/bin/activate && nohup python viz_server.py > viz_server.log 2>&1 &"

Start-Sleep -Seconds 2

Write-Host "✓ Server restarted!" -ForegroundColor Green
Write-Host ""
Write-Host "Access the UI at: http://raspberrypi:8000" -ForegroundColor Yellow
