# Raspberry Pi Spark Cluster Setup Guide

This guide documents the complete setup procedure for a 2-node Apache Spark cluster using Raspberry Pi 5 devices.

## Hardware

| Component | Specification |
|-----------|---------------|
| Nodes | 2x Raspberry Pi 5 |
| RAM | 8GB per node |
| Storage | 256GB SSD per node |
| Network | Ethernet (same LAN) |

## Network Configuration

| Hostname | Role | IP Address |
|----------|------|------------|
| raspberrypi | Master + Worker | 192.168.1.223 |
| applepi | Worker | 192.168.1.250 |

---

## Prerequisites

### 1. OS Installation
Both Pis should have Raspberry Pi OS (Debian Trixie) installed with SSH enabled.

### 2. SSH Access from Development Machine
Ensure passwordless SSH access from your development machine to both Pis:

```bash
# Test connectivity
ssh pi@raspberrypi "hostname"
ssh pi@applepi "hostname"
```

---

## Setup Procedure

### Step 1: Install Java 21 on Both Nodes

```bash
# On raspberrypi
ssh pi@raspberrypi "sudo apt update && sudo apt install -y openjdk-21-jdk-headless"

# On applepi
ssh pi@applepi "sudo apt update && sudo apt install -y openjdk-21-jdk-headless"
```

Verify installation:
```bash
ssh pi@raspberrypi "java -version"
ssh pi@applepi "java -version"
```

### Step 2: Install Python and Dependencies

Raspberry Pi OS (Debian Trixie) comes with Python 3.13 pre-installed. Install pip and venv packages:

```bash
# On raspberrypi
ssh pi@raspberrypi "sudo apt install -y python3-pip python3-venv"

# On applepi
ssh pi@applepi "sudo apt install -y python3-pip python3-venv"
```

Verify Python installation:
```bash
ssh pi@raspberrypi "python3 --version"
ssh pi@applepi "python3 --version"
```

> **Note:** Due to PEP 668, Debian prevents system-wide pip installs. We use virtual environments instead.

### Step 3: Create Python Virtual Environment

Both nodes need identical Python environments:

```bash
# On raspberrypi
ssh pi@raspberrypi "python3 -m venv ~/spark-env && ~/spark-env/bin/pip install pyspark numpy"

# On applepi
ssh pi@applepi "python3 -m venv ~/spark-env && ~/spark-env/bin/pip install pyspark numpy"
```

### Step 3: Download Apache Spark

Download and extract Spark 4.1.1 on both nodes:

```bash
# On raspberrypi
ssh pi@raspberrypi "cd ~ && wget -q https://dlcdn.apache.org/spark/spark-4.1.1/spark-4.1.1-bin-hadoop3.tgz && tar xzf spark-4.1.1-bin-hadoop3.tgz && rm spark-4.1.1-bin-hadoop3.tgz && ln -sf spark-4.1.1-bin-hadoop3 spark"

# On applepi
ssh pi@applepi "cd ~ && wget -q https://dlcdn.apache.org/spark/spark-4.1.1/spark-4.1.1-bin-hadoop3.tgz && tar xzf spark-4.1.1-bin-hadoop3.tgz && rm spark-4.1.1-bin-hadoop3.tgz && ln -sf spark-4.1.1-bin-hadoop3 spark"
```

### Step 4: Configure Inter-Node SSH

The master node needs passwordless SSH access to all worker nodes:

```bash
# Generate SSH key on master (if not exists)
ssh pi@raspberrypi "test -f ~/.ssh/id_rsa || ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa"

# Get the public key
ssh pi@raspberrypi "cat ~/.ssh/id_rsa.pub"

# Add public key to worker's authorized_keys
ssh pi@applepi "mkdir -p ~/.ssh && echo 'PASTE_PUBLIC_KEY_HERE' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# Test connection (from master to worker)
ssh pi@raspberrypi "ssh -o StrictHostKeyChecking=no pi@192.168.1.250 'hostname'"
```

### Step 5: Configure Spark

#### Create workers file on master:
```bash
ssh pi@raspberrypi "cat > ~/spark/conf/workers << 'EOF'
192.168.1.223
192.168.1.250
EOF"
```

#### Create spark-env.sh on both nodes:

**On raspberrypi (master):**
```bash
ssh pi@raspberrypi "cat > ~/spark/conf/spark-env.sh << 'EOF'
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64
export SPARK_HOME=/home/pi/spark
export PYSPARK_PYTHON=/home/pi/spark-env/bin/python
export SPARK_MASTER_HOST=192.168.1.223
export SPARK_WORKER_CORES=4
export SPARK_WORKER_MEMORY=6g
export SPARK_SSH_OPTS=\"-o StrictHostKeyChecking=no\"
EOF"
```

**On applepi (worker):**
```bash
ssh pi@applepi "cat > ~/spark/conf/spark-env.sh << 'EOF'
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64
export SPARK_HOME=/home/pi/spark
export PYSPARK_PYTHON=/home/pi/spark-env/bin/python
export SPARK_MASTER_HOST=192.168.1.223
export SPARK_WORKER_CORES=4
export SPARK_WORKER_MEMORY=6g
EOF"
```

### Step 6: Start the Cluster

#### Start Master:
```bash
ssh pi@raspberrypi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-master.sh"
```

#### Start Workers:
```bash
# Worker on master node
ssh pi@raspberrypi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-worker.sh spark://192.168.1.223:7077"

# Worker on applepi
ssh pi@applepi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-worker.sh spark://192.168.1.223:7077"
```

### Step 7: Verify Cluster

Check running processes:
```bash
ssh pi@raspberrypi "jps"  # Should show: Master, Worker, Jps
ssh pi@applepi "jps"       # Should show: Worker, Jps
```

Access Web UI: http://192.168.1.223:8080

---

## Troubleshooting

### Workers not connecting
- Check firewall rules (ports 7077, 8080, 4040 should be open)
- Verify network connectivity: `ping 192.168.1.250` from raspberrypi
- Check Spark logs: `~/spark/logs/`

### Java not found
- Ensure JAVA_HOME is set correctly
- Verify Java installation: `java -version`

### Python version mismatch
- Both nodes must use the same Python version
- Use the virtual environment: `~/spark-env/bin/python`

---

## Directory Structure (on each Pi)

```
/home/pi/
├── spark/                    # Spark installation (symlink)
│   ├── bin/
│   ├── conf/
│   │   ├── workers          # List of worker IPs
│   │   └── spark-env.sh     # Environment configuration
│   ├── sbin/
│   └── logs/
├── spark-4.1.1-bin-hadoop3/ # Actual Spark directory
├── spark-env/               # Python virtual environment
│   └── bin/python
└── main.py                  # Application script
```
