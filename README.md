# Circle Cover Problem - PySpark Implementation

Greedy thresholding algorithm for the circle cover problem with **1/2(1-ε) approximation guarantee**, implemented using Apache Spark for distributed computing.

## Algorithm

The circle cover problem is a geometric variant of set cover: given a set of points P and candidate circles C, find k circles that cover the maximum number of points.

This implementation uses:
- **Greedy thresholding** with logarithmic guesses for unknown OPT
- **Submodular maximization** (coverage function is monotone submodular)
- **PySpark** for parallelizing marginal gain computation

![Visualization Dashboard](docs/visualization_screenshot.png)

## Quick Start

### Local Mode (Windows/Linux)

```bash
# Create virtual environment
python -m venv .venv
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux

# Install dependencies
pip install -r requirements.txt

# Run locally with small dataset
python main.py --size small

# Run with visualization server (in separate terminals)
python viz_server.py  # Terminal 1
python main.py --ui-url http://localhost:8000 --size medium  # Terminal 2
```

### Cluster Mode (Raspberry Pi)

```bash
# SSH to master node
ssh pi@raspberrypi

# Run on cluster
~/spark-env/bin/python ~/main.py --cluster --size medium
```

---

## Raspberry Pi Cluster

### Cluster Information

| Node | Role | IP | Cores | Memory |
|------|------|-----|-------|--------|
| raspberrypi | Master + Worker | 192.168.1.223 | 4 | 6GB |
| applepi | Worker | 192.168.1.250 | 4 | 6GB |

**Total Resources:** 8 cores, 12GB memory

### Web Interfaces

| Service | URL |
|---------|-----|
| Spark Master UI | http://raspberrypi:8080 |
| Spark Application UI | http://raspberrypi:4040 (when app running) |

### Cluster Management

#### Start Cluster
```bash
# Start master
ssh pi@raspberrypi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-master.sh"

# Start worker on raspberrypi
ssh pi@raspberrypi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-worker.sh spark://192.168.1.223:7077"

# Start worker on applepi
ssh pi@applepi "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64 && ~/spark/sbin/start-worker.sh spark://192.168.1.223:7077"
```

#### Stop Cluster
```bash
# Stop all (from master)
ssh pi@raspberrypi "~/spark/sbin/stop-all.sh"

# Or stop individually
ssh pi@raspberrypi "~/spark/sbin/stop-worker.sh"
ssh pi@raspberrypi "~/spark/sbin/stop-master.sh"
ssh pi@applepi "~/spark/sbin/stop-worker.sh"
```

#### Check Status
```bash
# Check running Java processes
ssh pi@raspberrypi "jps"
ssh pi@applepi "jps"

# View logs
ssh pi@raspberrypi "tail -50 ~/spark/logs/spark-pi-org.apache.spark.deploy.master.Master-1-raspberrypi.out"
```

### Deploy Application

```bash
# Copy script to Pi
scp main.py pi@raspberrypi:~/main.py

# Run on cluster (without visualization)
ssh pi@raspberrypi "~/spark-env/bin/python ~/main.py --cluster --size medium"

# Run with visualization (requires viz_server running)
ssh pi@raspberrypi "~/spark-env/bin/python ~/main.py --cluster --ui-url http://127.0.0.1:8000 --size large"

# Or run directly from the UI dashboard (recommended)
# Navigate to http://raspberrypi:8000 and click "Run New Simulation"
```

### Visualization Dashboard

The project includes a real-time web visualization dashboard with interactive controls.

**Start the Server:**
```bash
ssh pi@raspberrypi
# Start the visualization server (runs on port 8000)
~/spark-env/bin/python ~/viz_server.py
```

**Run the Algorithm with Visualization:**
```bash
# In a separate terminal, run the algorithm with the --ui-url flag
ssh pi@raspberrypi "~/spark-env/bin/python ~/main.py --cluster --ui-url http://127.0.0.1:8000 --size medium"
```

**Access the UI:**
Open `http://raspberrypi:8000` in your browser.

**Features:**
- **Real-time Visualization**: See points and circles as they are covered during exploration.
- **Final Solution Highlighting**: Best solution circles rendered in **gold** with enhanced glow, distinguishing them from intermediate guesses (cyan).
- **Dataset Size Selection**: Choose from small (2K), medium (25K), or large (100K) point datasets.
- **Smart Sampling**: Automatic stratified/uniform sampling for large datasets to maintain UI performance.
- **Cluster Control**: Start new simulations directly from the UI with customizable dataset sizes.
- **Live Worker Stats**: Monitor core/memory usage of connected nodes in real-time.
- **Algorithm Metrics**: Track marginal gain and total coverage graphs across all guesses.

**What You'll See:**

The visualization progresses through multiple threshold guesses (j=0 to log k):
1. **Exploration phase** - Cyan circles appear as the algorithm tests different thresholds
2. **Final result** - Screen clears and the **best solution** is displayed in **gold**
3. Status shows: `FINAL SOLUTION: X% Coverage` with the winning guess number

---

## Configuration

### Dataset Size

Choose from three predefined configurations via command line:

```bash
# Small dataset (2K points, 500 circles, 8 clusters)
python main.py --size small

# Medium dataset (25K points, 2K circles, 20 clusters)
python main.py --size medium

# Large dataset (100K points, 5K circles, 50 clusters)
python main.py --size large
```

### Algorithm Parameters

Edit in `main.py` (applies to all sizes):

```python
K = 10              # Maximum circles to select
EPSILON = 0.2       # Approximation parameter (affects # of guesses)
BOUNDS = (0, 0, 1000, 1000)    # Spatial bounds
RADIUS_RANGE = (30, 100)        # Circle radius range
```

### Cluster Settings

```python
SPARK_MASTER_URL = "spark://192.168.1.223:7077"
```

Or use `--cluster` flag to enable cluster mode (auto-detects Pi cluster environment).

---

## Project Structure

```
PI-Cluster/
├── main.py              # Main algorithm implementation
├── viz_server.py        # Visualization backend (FastAPI)
├── ui/                  # Frontend assets
│   ├── index.html       # Dashboard UI
│   ├── style.css        # Glassmorphism styles
│   └── script.js        # Visualization logic
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── CLUSTER_SETUP.md     # Detailed cluster setup guide
```

---

## Requirements

### Local Development
- Python 3.11+
- Java 17+ (for Spark)
- See `requirements.txt`

### Raspberry Pi Cluster
- Raspberry Pi 5 (8GB RAM recommended)
- Raspberry Pi OS (Debian Trixie)
- Java 21
- Python 3.13

---

## References

- [Apache Spark Documentation](https://spark.apache.org/docs/latest/)
- Submodular maximization for set cover problems
- Greedy thresholding algorithm with logarithmic guesses
