# PySpark - PI Cluster - MapReduce
In this repository the configuration and motivation behind design decisions of the pi cluster using PySpark is documented.

📚 **[Documentation Index](DOCUMENTATION_INDEX.md)** - Complete guide to all documentation

**Research questions**
1.  How does MapReduce theory translate to practice?
    - How is the data distributed?
    - Is storage space only considered as RAM or also disk?
    - Are communication rounds truly adhered to? (no mapper starts if any reducer is still running)
2. Is the usage of an Oracle in an MPC algorithm, still considered truly MPC?
3. How can the data be efficiently represented for MPC algorithms?
    - Specifically, for the GreedySubmodular 0.5-approximation algorithm for the maximum coverage problem on a point set P using a set of k circles.

## 1. Cluster configuration

All nodes are Raspberry Pi 5 devices; the master has an attached 256 GB SSD while the workers use 64 GB SD cards.

| Node | Role | Cores | RAM | Storage |
| --- | --- | ---: | ---: | --- |
| `raspberrypi` | **master** | 4 | 8 GB | Transcend 400S 256 GB SSD (sdram-less) |
| `applepi` | **worker** | 4 | 8 GB | 64 GB SD card |
| `blueberrypi` | **worker** | 4 | 8 GB | 64 GB SD card |

**Setup guides:**
- 📘 **[PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)** - Complete cluster setup and deployment guide
- 🚀 **[QUICK_START.md](QUICK_START.md)** - Quick reference for daily operations

**Network configuration:** Static IPs via Ethernet, SSH passwordless access between nodes

**Storage architecture:** Master's SSD shared via NFS to all workers at `/data`

## 2. PySpark - GreedySubmodular - CircleCover problem
Translating theory to practice.
### 2.1. GreedySubmodular MPC algorithm for CircleCover problem
> **TODO:** document mappers and reducers to solve the circle cover problem using the greedy submodular half approximation algorithm.

### 2.2. Translating abstract machines and space per machines
In theory, for example, we assume that we can uniformly distribute data over `O(sqrt(n))` machines with `polylog(n)` storage/space.
However, in practice, we have a fixed number of machines with a pre-determined storage size.


For example, `3` machines with `8Gb`of RAM and some secondary storage like SSD or SDcard of `64Gb-256Gb`.
And, in terms of `PySpark`, we consider `executor cores` as the concrete version of an abstract machine (processor).

The idea is that PySpark will handle assigning `partitions` of data to these executor cores.
Thus, we must pre-emptively prepare these partitions of the data such that each executor core can process it.

For example, if we know that each raspberry pi 5 has `4` cores and `8Gb` of memory, we must ensure that when all executors are processing their partition that we have enough space in memory for in-memory computations.

It turns out that, in the industry, the general recommendation is to keep each partition size low such as `128Mb-192Mb`.
This would leave plenty of room (depending on the task and memory configuration) and account for how much overhead we have from Spark (JVM, shuffle buffers, etc.); this overhead can be signifcant `50-150%+` per task due to data expension.
Then, each executor would have the following memory usage
```
usage = executor cores * (partition size) + Spark overhead
```
This is something which should be tuned to optimize the performance of the algorithms we run.

Thus, we have figured out, roughly, how much memory will be used to stay on the safe side and not get `out of memory` or `disk-spill` problems (which would be extremely bad on SDcards). 

> **NOTE:** The executors will still have to fetch the partitions from some shared storage pool to memory.

### 2.3 Translating mappers and reducers to code
Implementation complete! See [PLAN.md](PLAN.md) for full design details.

## 3. Implementation

The PySpark implementation is now complete. See [PLAN.md](PLAN.md) for detailed design documentation.

### 3.1 Setup

1. **Create virtual environment and install dependencies:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Verify installation:**
```bash
python3 -m pytest tests/test_geometry.py -v
```

### 3.2 Quick Start

**Generate a small dataset and run the algorithm:**

```bash
# Generate data
python3 scripts/generate_data.py \
    --config configs/small_experiment.yaml \
    --output-dir data/raw/small

# Run algorithm
python3 src/main.py \
    --points data/raw/small/points \
    --circles data/raw/small/circles \
    --k 5 \
    --output data/results/small
```

**Or run a complete experiment (generates data and runs algorithm):**

```bash
python3 scripts/run_experiment.py \
    --config configs/small_experiment.yaml \
    --generate-data
```

### 3.3 Running on Pi Cluster

1. **Set up Spark cluster** (on master node):
```bash
# Start master
$SPARK_HOME/sbin/start-master.sh

# On each worker node:
$SPARK_HOME/sbin/start-worker.sh spark://raspberrypi:7077
```

2. **Submit job to cluster:**
```bash
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --num-executors 6 \
    scripts/run_experiment.py \
    --config configs/medium_experiment.yaml \
    --master spark://raspberrypi:7077 \
    --generate-data
```

### 3.4 Experiment Configurations

Three pre-configured experiments are available:

| Config | Points | Circles | k | Expected Runtime |
|--------|--------|---------|---|------------------|
| `small_experiment.yaml` | 10K | 1K | 5 | < 1 min |
| `medium_experiment.yaml` | 1M | 10K | 10 | ~10 min |
| `large_experiment.yaml` | 10M | 50K | 20 | 1-2 hours |

### 3.5 Testing

```bash
# Run geometry tests
python3 -m pytest tests/test_geometry.py -v

# Run algorithm integration tests (requires PySpark)
python3 -m pytest tests/test_algorithm.py -v

# Or run all tests
python3 -m pytest tests/ -v
```

### 3.6 Project Structure

See [PLAN.md](PLAN.md) for complete project structure. Key files:

- `src/algorithm/greedy_submodular.py` - Main algorithm implementation
- `src/mapreduce/mappers.py` - Map functions for gain computation and coverage updates
- `src/mapreduce/reducers.py` - Reduce functions for aggregation
- `src/data/generators.py` - Synthetic data generation
- `src/config/spark_config.py` - Pi cluster optimized Spark configuration