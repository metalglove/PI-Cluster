#!/bin/bash
# Quick deployment script for Pi Cluster
# Copies all necessary files to the Raspberry Pi

# Color codes
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}Deploying to Pi Cluster...${NC}"
echo ""

# Main algorithm
echo -e "${YELLOW}[1/5] Deploying main.py...${NC}"
scp main.py pi@raspberrypi:/home/pi/main.py

# Visualization server
echo -e "${YELLOW}[2/5] Deploying viz_server.py...${NC}"
scp viz_server.py pi@raspberrypi:/home/pi/viz_server.py

# UI files
echo -e "${YELLOW}[3/5] Deploying UI HTML...${NC}"
scp ui/index.html pi@raspberrypi:/home/pi/ui/index.html

echo -e "${YELLOW}[4/5] Deploying UI CSS...${NC}"
scp ui/style.css pi@raspberrypi:/home/pi/ui/style.css
scp ui/mobile.css pi@raspberrypi:/home/pi/ui/mobile.css

echo -e "${YELLOW}[5/5] Deploying UI JavaScript...${NC}"
scp ui/script.js pi@raspberrypi:/home/pi/ui/script.js

echo ""
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo ""

echo -e "${YELLOW}Stopping existing server...${NC}"
ssh pi@raspberrypi "pkill -f viz_server.py"
sleep 1

echo -e "${YELLOW}Starting new server in background...${NC}"
# Using a specific bash wrapper and disown to ensure process survival
ssh pi@raspberrypi "cd /home/pi && (nohup /home/pi/spark-env/bin/python viz_server.py > viz_server.log 2>&1 &)"

echo -e "${YELLOW}Waiting for startup...${NC}"
sleep 5

# Verification step
check=$(ssh pi@raspberrypi "netstat -tuln | grep :8000")
if [[ $check == *"8000"* ]]; then
    echo -e "${GREEN}✓ Server restarted and listening on port 8000!${NC}"
else
    echo -e "${RED}⚠ WARNING: Server might not have started correctly. Check viz_server.log on Pi.${NC}"
    ssh pi@raspberrypi "tail -n 10 /home/pi/viz_server.log"
fi

echo ""
echo -e "${YELLOW}Access the UI at: http://raspberrypi:8000${NC}"
