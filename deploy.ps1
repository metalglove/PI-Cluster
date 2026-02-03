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

Write-Host "Stopping existing server..." -ForegroundColor Yellow
ssh pi@raspberrypi "pkill -f viz_server.py"
Start-Sleep -Seconds 1

Write-Host "Starting new server in background..." -ForegroundColor Yellow
# Using a specific bash wrapper and disown to ensure process survival
ssh pi@raspberrypi "cd /home/pi && (nohup /home/pi/spark-env/bin/python viz_server.py > viz_server.log 2>&1 &)"

Write-Host "Waiting for startup..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Verification step
$check = ssh pi@raspberrypi "netstat -tuln | grep :8000"
if ($check -match "8000") {
    Write-Host "✓ Server restarted and listening on port 8000!" -ForegroundColor Green
}
else {
    Write-Host "⚠ WARNING: Server might not have started correctly. Check viz_server.log on Pi." -ForegroundColor Red
    ssh pi@raspberrypi "tail -n 10 /home/pi/viz_server.log"
}

Write-Host ""
Write-Host "Access the UI at: http://raspberrypi:8000" -ForegroundColor Yellow
