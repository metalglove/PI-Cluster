# Raspberry Pi Cluster Setup and Deployment Guide

Complete guide for setting up a 3-node Raspberry Pi cluster for PySpark Circle Cover experiments.

## Table of Contents

1. [Hardware Requirements](#1-hardware-requirements)
2. [Operating System Installation](#2-operating-system-installation)
3. [Network Configuration](#3-network-configuration)
4. [SSH Setup](#4-ssh-setup)
5. [Java and Spark Installation](#5-java-and-spark-installation)
6. [Shared Storage (NFS)](#6-shared-storage-nfs)
7. [Spark Cluster Configuration](#7-spark-cluster-configuration)
8. [Python Environment Setup](#8-python-environment-setup)
9. [Code Deployment](#9-code-deployment)
10. [Running Experiments](#10-running-experiments)
11. [Monitoring and Troubleshooting](#11-monitoring-and-troubleshooting)

---

## 1. Hardware Requirements

### Bill of Materials

| Component | Master (raspberrypi) | Worker 1 (applepi) | Worker 2 (blueberrypi) |
|-----------|---------------------|-------------------|----------------------|
| **Hardware** | Raspberry Pi 5 (8GB) | Raspberry Pi 5 (8GB) | Raspberry Pi 5 (8GB) |
| **Storage** | 256GB SSD (Transcend 400S) | 64GB SD Card | 64GB SD Card |
| **Power** | USB-C Power Supply (5V/5A) | USB-C Power Supply (5V/5A) | USB-C Power Supply (5V/5A) |
| **Network** | Gigabit Ethernet Cable | Gigabit Ethernet Cable | Gigabit Ethernet Cable |
| **Cooling** | Heatsink + Fan (recommended) | Heatsink + Fan (recommended) | Heatsink + Fan (recommended) |

**Additional Components:**
- Gigabit Ethernet Switch (4+ ports)
- SD Card Reader (for flashing)
- SATA to USB adapter (for SSD on master)

**Total Cost Estimate:** ~$500-600 USD

### Storage Configuration

- **Master Node (`raspberrypi`)**: 256GB SSD via USB 3.0
  - OS and system: 32GB
  - Spark installation: 2GB
  - Shared data (/data): 220GB

- **Worker Nodes (`applepi`, `blueberrypi`)**: 64GB SD Cards
  - OS and system: 32GB
  - Spark installation: 2GB
  - Local temp/shuffle: 30GB

---

## 2. Operating System Installation

### 2.1 Download Raspberry Pi OS

```bash
# Download Raspberry Pi OS (64-bit) Lite
# URL: https://www.raspberrypi.com/software/operating-systems/
# Choose: "Raspberry Pi OS Lite (64-bit)" - no desktop needed
```

### 2.2 Flash OS to SD Cards/SSD

**Using Raspberry Pi Imager (Recommended):**

1. Install Raspberry Pi Imager on your computer
   ```bash
   # macOS
   brew install --cask raspberry-pi-imager

   # Or download from: https://www.raspberrypi.com/software/
   ```

2. Flash each device:
   - Insert SD card/SSD
   - Open Raspberry Pi Imager
   - Choose OS: "Raspberry Pi OS Lite (64-bit)"
   - Choose Storage: Your SD card/SSD
   - Click ⚙️ (Settings) for advanced options:
     - ✓ Enable SSH (Use password authentication)
     - ✓ Set hostname: `raspberrypi`, `applepi`, or `blueberrypi`
     - ✓ Set username and password: `pi` / `your-password`
     - ✓ Configure wireless LAN (optional, but Ethernet recommended)
     - ✓ Set locale settings
   - Click "Write"
   - Repeat for all three nodes

**Alternative: Manual dd command:**

```bash
# Find device name (be careful!)
diskutil list  # macOS
lsblk          # Linux

# Unmount
diskutil unmountDisk /dev/disk4  # Replace disk4 with your device

# Write image
sudo dd if=2024-xx-xx-raspios-bookworm-arm64-lite.img of=/dev/rdisk4 bs=1m status=progress

# Eject
diskutil eject /dev/disk4
```

### 2.3 First Boot

1. Insert SD cards/SSD into Pis
2. Connect Ethernet cables to switch
3. Power on all nodes
4. Wait 2-3 minutes for first boot

---

## 3. Network Configuration

### 3.1 Find IP Addresses

```bash
# From your computer, scan network
nmap -sn 192.168.1.0/24  # Adjust to your network

# Or check router DHCP leases
# Or connect monitor and run:
hostname -I
```

### 3.2 Assign Static IPs

**On each Pi, edit `/etc/dhcpcd.conf`:**

```bash
sudo nano /etc/dhcpcd.conf
```

**Add for Master (raspberrypi):**
```
interface eth0
static ip_address=192.168.1.10/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

**Add for Worker 1 (applepi):**
```
interface eth0
static ip_address=192.168.1.11/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

**Add for Worker 2 (blueberrypi):**
```
interface eth0
static ip_address=192.168.1.12/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

**Reboot each node:**
```bash
sudo reboot
```

### 3.3 Configure /etc/hosts

**On ALL nodes, add:**

```bash
sudo nano /etc/hosts
```

Add:
```
192.168.1.10    raspberrypi
192.168.1.11    applepi
192.168.1.12    blueberrypi
```

**Test connectivity:**
```bash
ping raspberrypi
ping applepi
ping blueberrypi
```

---

## 4. SSH Setup

### 4.1 Enable SSH (if not done during imaging)

```bash
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 4.2 Set Up SSH Keys (Passwordless Access)

**On your computer:**

```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy to each Pi
ssh-copy-id pi@raspberrypi
ssh-copy-id pi@applepi
ssh-copy-id pi@blueberrypi

# Test passwordless login
ssh pi@raspberrypi
```

### 4.3 Configure SSH Between Nodes

**On master (raspberrypi), as user `pi`:**

```bash
# Generate SSH key on master
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# Copy to workers
ssh-copy-id pi@applepi
ssh-copy-id pi@blueberrypi

# Copy to self (for consistency)
ssh-copy-id pi@raspberrypi

# Test
ssh applepi hostname
ssh blueberrypi hostname
```

**Repeat on each worker for bidirectional access** (optional but useful for debugging).

---

## 5. Java and Spark Installation

### 5.1 Install Java 11

**On ALL nodes:**

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y openjdk-11-jdk

# Verify
java -version
# Should show: openjdk version "11.x.x"
```

**Set JAVA_HOME:**

```bash
echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-arm64' >> ~/.bashrc
echo 'export PATH=$JAVA_HOME/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# Verify
echo $JAVA_HOME
```

### 5.2 Download and Install Spark

**On ALL nodes:**

```bash
# Download Spark 3.5.4 (pre-built for Hadoop 3)
cd ~
wget https://dlcdn.apache.org/spark/spark-3.5.4/spark-3.5.4-bin-hadoop3.tgz

# Extract
tar -xzf spark-3.5.4-bin-hadoop3.tgz
sudo mv spark-3.5.4-bin-hadoop3 /opt/spark

# Clean up
rm spark-3.5.4-bin-hadoop3.tgz

# Set environment variables
echo 'export SPARK_HOME=/opt/spark' >> ~/.bashrc
echo 'export PATH=$SPARK_HOME/bin:$SPARK_HOME/sbin:$PATH' >> ~/.bashrc
echo 'export PYSPARK_PYTHON=/usr/bin/python3' >> ~/.bashrc
source ~/.bashrc

# Verify
spark-submit --version
```

### 5.3 Install Python Dependencies

**On ALL nodes:**

```bash
# Install Python 3 and pip
sudo apt install -y python3 python3-pip python3-venv

# Create virtual environment
cd ~
python3 -m venv spark-env
source spark-env/bin/activate

# Install PySpark and dependencies
pip install pyspark==3.5.4 pyarrow pandas numpy

# Make activation permanent
echo 'source ~/spark-env/bin/activate' >> ~/.bashrc
```

---

## 6. Shared Storage (NFS)

### 6.1 Set Up NFS Server (Master Node)

**On master (raspberrypi):**

```bash
# Install NFS server
sudo apt install -y nfs-kernel-server

# Create data directory on SSD
sudo mkdir -p /data
sudo chown pi:pi /data
sudo chmod 755 /data

# Create subdirectories
mkdir -p /data/raw/points
mkdir -p /data/raw/circles
mkdir -p /data/results
mkdir -p /data/checkpoints

# Configure NFS exports
sudo nano /etc/exports
```

**Add to `/etc/exports`:**
```
/data 192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
```

**Apply changes:**
```bash
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server

# Verify
sudo exportfs -v
```

### 6.2 Mount NFS on Workers

**On applepi and blueberrypi:**

```bash
# Install NFS client
sudo apt install -y nfs-common

# Create mount point
sudo mkdir -p /data
sudo chown pi:pi /data

# Test mount
sudo mount raspberrypi:/data /data
ls -la /data  # Should see directories

# Unmount for now
sudo umount /data

# Configure auto-mount at boot
sudo nano /etc/fstab
```

**Add to `/etc/fstab`:**
```
raspberrypi:/data    /data    nfs    defaults,_netdev    0    0
```

**Mount and verify:**
```bash
sudo mount -a
df -h | grep /data
# Should show: raspberrypi:/data mounted at /data
```

**Test write access:**
```bash
# On worker
touch /data/test_from_worker.txt

# On master
ls -la /data/test_from_worker.txt

# Clean up
rm /data/test_from_worker.txt
```

---

## 7. Spark Cluster Configuration

### 7.1 Configure Spark Master

**On master (raspberrypi):**

```bash
cd $SPARK_HOME/conf

# Create config from template
cp spark-env.sh.template spark-env.sh
nano spark-env.sh
```

**Add to `spark-env.sh`:**
```bash
# Master node configuration
export SPARK_MASTER_HOST=raspberrypi
export SPARK_MASTER_PORT=7077
export SPARK_MASTER_WEBUI_PORT=8080

# Memory settings
export SPARK_WORKER_MEMORY=6g
export SPARK_WORKER_CORES=4
export SPARK_DAEMON_MEMORY=1g

# Python
export PYSPARK_PYTHON=/home/pi/spark-env/bin/python3
export PYSPARK_DRIVER_PYTHON=/home/pi/spark-env/bin/python3

# Temp directory (use faster storage if available)
export SPARK_WORKER_DIR=/tmp/spark-worker
export SPARK_LOCAL_DIRS=/tmp/spark-local
```

**Create workers file:**
```bash
nano $SPARK_HOME/conf/workers
```

**Add to `workers`:**
```
applepi
blueberrypi
```

### 7.2 Configure Spark Workers

**On applepi and blueberrypi:**

```bash
cd $SPARK_HOME/conf

# Create config from template
cp spark-env.sh.template spark-env.sh
nano spark-env.sh
```

**Add to `spark-env.sh`:**
```bash
# Worker node configuration
export SPARK_MASTER_HOST=raspberrypi
export SPARK_MASTER_PORT=7077

# Memory settings
export SPARK_WORKER_MEMORY=6g
export SPARK_WORKER_CORES=4
export SPARK_DAEMON_MEMORY=1g

# Python
export PYSPARK_PYTHON=/home/pi/spark-env/bin/python3
export PYSPARK_DRIVER_PYTHON=/home/pi/spark-env/bin/python3

# Temp directory
export SPARK_WORKER_DIR=/tmp/spark-worker
export SPARK_LOCAL_DIRS=/tmp/spark-local
```

### 7.3 Configure Spark Defaults

**On ALL nodes:**

```bash
cd $SPARK_HOME/conf
cp spark-defaults.conf.template spark-defaults.conf
nano spark-defaults.conf
```

**Add to `spark-defaults.conf`:**
```
# Cluster configuration
spark.master                     spark://raspberrypi:7077
spark.eventLog.enabled           true
spark.eventLog.dir               file:///data/spark-events
spark.history.fs.logDirectory    file:///data/spark-events

# Executor configuration (per executor)
spark.executor.memory            3g
spark.executor.memoryOverhead    1g
spark.executor.cores             2

# Driver configuration
spark.driver.memory              2g
spark.driver.memoryOverhead      512m

# Parallelism
spark.default.parallelism        36
spark.sql.shuffle.partitions     24

# Serialization
spark.serializer                 org.apache.spark.serializer.KryoSerializer
spark.kryoserializer.buffer.max  64m

# Shuffle optimization
spark.shuffle.compress           true
spark.shuffle.spill.compress     true
spark.shuffle.file.buffer        64k

# Network timeouts
spark.network.timeout            800s
spark.rpc.askTimeout             600s

# Speculation
spark.speculation                true
spark.speculation.interval       100ms
spark.speculation.multiplier     3
```

**Create event log directory:**
```bash
# On master
mkdir -p /data/spark-events
```

---

## 8. Python Environment Setup

### 8.1 Clone Repository to Master

**On master (raspberrypi):**

```bash
cd ~
git clone https://github.com/yourusername/PI-Cluster.git
cd PI-Cluster

# Or if you have the code locally, copy it:
# From your computer:
# rsync -avz --exclude='.git' --exclude='data' --exclude='.venv' \
#   /Users/glovali/repos/PI-Cluster/ pi@raspberrypi:~/PI-Cluster/
```

### 8.2 Install Project Dependencies

**On master (raspberrypi):**

```bash
cd ~/PI-Cluster
source ~/spark-env/bin/activate

# Install requirements
pip install -r requirements.txt

# Verify installation
python3 -c "import pyspark; print(pyspark.__version__)"
```

### 8.3 Sync Code to Workers (Optional)

**On master:**

```bash
# Create script for syncing
cat > ~/sync_code.sh << 'EOF'
#!/bin/bash
rsync -avz --exclude='.git' --exclude='data' --exclude='.venv' \
  ~/PI-Cluster/ applepi:~/PI-Cluster/

rsync -avz --exclude='.git' --exclude='data' --exclude='.venv' \
  ~/PI-Cluster/ blueberrypi:~/PI-Cluster/
EOF

chmod +x ~/sync_code.sh

# Run sync
./sync_code.sh
```

**On workers (if needed):**

```bash
cd ~/PI-Cluster
source ~/spark-env/bin/activate
pip install -r requirements.txt
```

---

## 9. Code Deployment

### 9.1 Start Spark Cluster

**On master (raspberrypi):**

```bash
# Start master
$SPARK_HOME/sbin/start-master.sh

# Check master is running
jps
# Should show: Master

# Check web UI
# Open browser: http://raspberrypi:8080 or http://192.168.1.10:8080
```

**Start workers:**

```bash
# From master, start all workers defined in workers file
$SPARK_HOME/sbin/start-workers.sh

# Or manually on each worker:
# On applepi:
$SPARK_HOME/sbin/start-worker.sh spark://raspberrypi:7077

# On blueberrypi:
$SPARK_HOME/sbin/start-worker.sh spark://raspberrypi:7077
```

**Verify cluster:**

```bash
# Check web UI: http://raspberrypi:8080
# Should show 2 workers (applepi, blueberrypi)
# Each with: 4 cores, 6GB memory

# Or check with jps on each node
ssh applepi jps    # Should show: Worker
ssh blueberrypi jps    # Should show: Worker
```

### 9.2 Test Spark Cluster

**On master:**

```bash
cd ~/PI-Cluster

# Test with spark-submit (Pi calculation example)
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 2 \
    $SPARK_HOME/examples/src/main/python/pi.py 100

# Should output: Pi is roughly 3.14...
```

---

## 10. Running Experiments

### 10.1 Generate Small Dataset (Test)

**On master:**

```bash
cd ~/PI-Cluster
source ~/spark-env/bin/activate

# Generate small test dataset
python3 scripts/generate_data.py \
    --config configs/small_experiment.yaml \
    --output-dir /data/raw/small \
    --master spark://raspberrypi:7077

# Verify data created
ls -lh /data/raw/small/points/
ls -lh /data/raw/small/circles/
```

### 10.2 Run Small Experiment

**Option 1: Using run_experiment.py**

```bash
python3 scripts/run_experiment.py \
    --config configs/small_experiment.yaml \
    --master spark://raspberrypi:7077 \
    --generate-data
```

**Option 2: Using spark-submit (recommended for cluster)**

```bash
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 2 \
    --driver-memory 2g \
    scripts/run_experiment.py \
    --config configs/small_experiment.yaml \
    --master spark://raspberrypi:7077
```

**Option 3: Using main.py directly**

```bash
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 2 \
    src/main.py \
    --points /data/raw/small/points \
    --circles /data/raw/small/circles \
    --k 5 \
    --output /data/results/small \
    --master spark://raspberrypi:7077
```

### 10.3 Run Medium Experiment

```bash
# Generate data first
python3 scripts/generate_data.py \
    --config configs/medium_experiment.yaml \
    --output-dir /data/raw/medium \
    --master spark://raspberrypi:7077

# Run algorithm
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 2 \
    --driver-memory 2g \
    --conf spark.checkpoint.dir=/data/checkpoints \
    scripts/run_experiment.py \
    --config configs/medium_experiment.yaml \
    --master spark://raspberrypi:7077

# Expected runtime: ~10 minutes
```

### 10.4 Run Large Experiment

```bash
# Generate data (this will take some time)
python3 scripts/generate_data.py \
    --config configs/large_experiment.yaml \
    --output-dir /data/raw/large \
    --master spark://raspberrypi:7077

# Run algorithm
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 2 \
    --driver-memory 2g \
    --conf spark.checkpoint.dir=/data/checkpoints \
    scripts/run_experiment.py \
    --config configs/large_experiment.yaml \
    --master spark://raspberrypi:7077

# Expected runtime: 1-2 hours
```

---

## 11. Monitoring and Troubleshooting

### 11.1 Monitoring Tools

**Spark Web UIs:**

- **Master UI**: `http://raspberrypi:8080`
  - Shows workers, applications, cluster resources

- **Application UI**: `http://raspberrypi:4040` (when app is running)
  - Shows stages, tasks, executors, storage, environment
  - **Critical for research**: View MapReduce stages, shuffle data, etc.

- **History Server** (optional):
  ```bash
  # Start history server on master
  $SPARK_HOME/sbin/start-history-server.sh

  # Access at: http://raspberrypi:18080
  ```

**System Monitoring:**

```bash
# CPU and memory usage
htop

# Disk usage
df -h

# Network usage
iftop

# Temperature (important for Pis!)
vcgencmd measure_temp
```

### 11.2 Common Issues

**Issue: Workers not connecting to master**

```bash
# Check if master is running
ssh raspberrypi jps

# Check if workers can reach master
ssh applepi telnet raspberrypi 7077
# Should connect successfully

# Check worker logs
ssh applepi tail -f /opt/spark/logs/spark-*-worker-*.out

# Restart cluster
$SPARK_HOME/sbin/stop-all.sh
$SPARK_HOME/sbin/start-all.sh
```

**Issue: Out of memory errors**

```bash
# Reduce executor memory
spark-submit --executor-memory 2g ...

# Reduce parallelism
--conf spark.default.parallelism=24

# Enable compression
--conf spark.shuffle.compress=true
```

**Issue: Disk spills on SD cards**

```bash
# Check Spark UI → Stages → Spill metrics
# Should be 0 for SD cards!

# Reduce partition size
# Edit configs/experiment.yaml:
# points:
#   n_points: 100000  # Reduce dataset size

# Or increase memory
--executor-memory 4g
```

**Issue: NFS mount issues**

```bash
# On worker, check mount
df -h | grep /data

# Remount
sudo umount /data
sudo mount -a

# Check NFS server
# On master:
sudo systemctl status nfs-kernel-server
sudo exportfs -v
```

**Issue: Python module not found**

```bash
# Ensure virtual environment activated
source ~/spark-env/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Set PYSPARK_PYTHON explicitly
export PYSPARK_PYTHON=/home/pi/spark-env/bin/python3
```

### 11.3 Performance Tuning

**Monitor temperature:**

```bash
# Create temperature monitor script
cat > ~/monitor_temp.sh << 'EOF'
#!/bin/bash
while true; do
    echo "$(date): Master: $(ssh raspberrypi vcgencmd measure_temp), Worker1: $(ssh applepi vcgencmd measure_temp), Worker2: $(ssh blueberrypi vcgencmd measure_temp)"
    sleep 60
done
EOF

chmod +x ~/monitor_temp.sh
./monitor_temp.sh
```

**If temperature > 70°C:**
- Improve cooling (larger heatsinks, fans)
- Reduce executor cores: `--executor-cores 1`
- Reduce parallelism

**Optimize for SD cards:**

```bash
# In spark-defaults.conf, ensure:
spark.shuffle.compress           true
spark.shuffle.spill.compress     true

# Minimize shuffle partitions
spark.sql.shuffle.partitions     12  # Reduce from 24
```

### 11.4 Useful Commands

**Cluster management:**

```bash
# Stop all
$SPARK_HOME/sbin/stop-all.sh

# Start all
$SPARK_HOME/sbin/start-all.sh

# Restart just master
$SPARK_HOME/sbin/stop-master.sh
$SPARK_HOME/sbin/start-master.sh

# Kill stuck jobs
# Find application ID in Spark UI, then:
$SPARK_HOME/bin/spark-class org.apache.spark.deploy.Client kill spark://raspberrypi:7077 <app-id>
```

**Data management:**

```bash
# Clear old results
rm -rf /data/results/*

# Clear checkpoints
rm -rf /data/checkpoints/*

# Check data sizes
du -sh /data/raw/*
du -sh /data/results/*
```

**Log viewing:**

```bash
# Master logs
tail -f $SPARK_HOME/logs/spark-*-master-*.out

# Worker logs
ssh applepi tail -f /opt/spark/logs/spark-*-worker-*.out

# Application logs
tail -f $SPARK_HOME/logs/spark-*-driver-*.log
```

---

## 12. Backup and Maintenance

### 12.1 Backup Configuration

```bash
# On master, create backup script
cat > ~/backup_config.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/config_backup_$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

# Backup Spark configs
cp -r $SPARK_HOME/conf $BACKUP_DIR/
cp ~/.bashrc $BACKUP_DIR/
cp /etc/fstab $BACKUP_DIR/
cp /etc/exports $BACKUP_DIR/
cp /etc/hosts $BACKUP_DIR/

tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

echo "Backup saved to $BACKUP_DIR.tar.gz"
EOF

chmod +x ~/backup_config.sh
```

### 12.2 System Updates

```bash
# On ALL nodes (do one at a time)
sudo apt update
sudo apt upgrade -y

# Reboot if kernel updated
sudo reboot
```

---

## 13. Quick Reference

### Start Cluster
```bash
# On master
$SPARK_HOME/sbin/start-master.sh
$SPARK_HOME/sbin/start-workers.sh
```

### Stop Cluster
```bash
# On master
$SPARK_HOME/sbin/stop-all.sh
```

### Run Experiment
```bash
# On master
cd ~/PI-Cluster
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    scripts/run_experiment.py \
    --config configs/small_experiment.yaml
```

### Check Status
```bash
# Web UI
http://raspberrypi:8080

# CLI
jps  # On each node
```

### View Results
```bash
# On master
ls -lh /data/results/
```

---

## Success Criteria

✅ All 3 nodes accessible via SSH
✅ Static IPs configured and hostnames resolving
✅ NFS shared storage mounted on all workers
✅ Java 11 installed on all nodes
✅ Spark 3.5.4 installed on all nodes
✅ Spark master running and accessible on port 8080
✅ 2 workers connected showing 4 cores, 6GB each
✅ Small experiment runs successfully (< 1 min)
✅ Results saved to `/data/results/`
✅ No disk spills observed in Spark UI

---

## Next Steps After Setup

1. ✅ Run validation experiments (small → medium → large)
2. 📊 Analyze results with Jupyter notebook
3. 📝 Document MapReduce observations (Spark UI screenshots)
4. 🔬 Answer research questions from README.md
5. 📈 Tune performance based on findings
6. 📄 Write up results

---

**Setup time estimate:** 4-6 hours for first-time setup

**Questions?** Check the troubleshooting section or consult:
- [Spark Documentation](https://spark.apache.org/docs/latest/)
- [Raspberry Pi Forums](https://forums.raspberrypi.com/)
- This repository's issues
