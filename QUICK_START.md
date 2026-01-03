# Quick Start Guide

Fast track to running Circle Cover experiments on your Pi cluster.

## Prerequisites

✅ Pi cluster set up according to [PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)
✅ All nodes powered on and connected
✅ Spark cluster running

## Daily Workflow

### 1. Start the Cluster

```bash
# SSH to master
ssh pi@raspberrypi

# Start Spark master and workers
$SPARK_HOME/sbin/start-master.sh
$SPARK_HOME/sbin/start-workers.sh

# Verify cluster is running
# Open browser: http://raspberrypi:8080
# Should show 2 workers with 4 cores, 6GB each
```

### 2. Run an Experiment

```bash
# Navigate to project
cd ~/PI-Cluster
source ~/spark-env/bin/activate

# Option A: Quick test (small dataset)
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    scripts/run_experiment.py \
    --config configs/small_experiment.yaml \
    --generate-data

# Option B: Medium scale (1M points, ~10 min)
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    scripts/run_experiment.py \
    --config configs/medium_experiment.yaml \
    --generate-data

# Option C: Large scale (10M points, 1-2 hours)
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    --conf spark.checkpoint.dir=/data/checkpoints \
    scripts/run_experiment.py \
    --config configs/large_experiment.yaml \
    --generate-data
```

### 3. Monitor Progress

**Web UI:**
- Spark Master: `http://raspberrypi:8080` - Cluster overview
- Application UI: `http://raspberrypi:4040` - Live job progress (only while running)

**Console:**
```bash
# Watch live output
# (automatically shown when running spark-submit)

# Monitor temperature
watch -n 5 'vcgencmd measure_temp'

# Monitor resources
htop
```

### 4. View Results

```bash
# List completed experiments
ls -lh /data/results/

# View iteration results (latest)
ls -lh /data/results/small_experiment/results/
```

### 5. Visualize Results

```bash
# Start Jupyter on master (or copy data to your computer)
jupyter notebook --ip=0.0.0.0 --port=8888

# Open in browser: http://raspberrypi:8888
# Navigate to: notebooks/visualize_results.ipynb
# Update EXPERIMENT_NAME in cell 2
# Run all cells
```

### 6. Stop the Cluster

```bash
# Stop all Spark processes
$SPARK_HOME/sbin/stop-all.sh

# Or stop individually
$SPARK_HOME/sbin/stop-workers.sh
$SPARK_HOME/sbin/stop-master.sh

# Power off Pis (optional)
sudo shutdown -h now
```

## Common Tasks

### Generate Data Only

```bash
python3 scripts/generate_data.py \
    --config configs/small_experiment.yaml \
    --output-dir /data/raw/custom_dataset \
    --master spark://raspberrypi:7077
```

### Run Algorithm on Existing Data

```bash
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    src/main.py \
    --points /data/raw/small/points \
    --circles /data/raw/small/circles \
    --k 5 \
    --output /data/results/custom_run \
    --master spark://raspberrypi:7077
```

### Create Custom Experiment

```bash
# Copy existing config
cp configs/small_experiment.yaml configs/my_experiment.yaml

# Edit parameters
nano configs/my_experiment.yaml
# Adjust: k, n_points, n_circles, radius, etc.

# Run
spark-submit \
    --master spark://raspberrypi:7077 \
    --executor-memory 3g \
    --executor-cores 2 \
    scripts/run_experiment.py \
    --config configs/my_experiment.yaml \
    --generate-data
```

### Clean Up Data

```bash
# Remove all results (keep raw data)
rm -rf /data/results/*

# Remove specific experiment
rm -rf /data/results/small_experiment

# Remove all data (start fresh)
rm -rf /data/raw/*
rm -rf /data/results/*
rm -rf /data/checkpoints/*
```

### Check Cluster Health

```bash
# Check all nodes are reachable
ping -c 1 raspberrypi && echo "Master OK"
ping -c 1 applepi && echo "Worker 1 OK"
ping -c 1 blueberrypi && echo "Worker 2 OK"

# Check NFS mounts
df -h | grep /data

# Check Spark processes
jps  # On master
ssh applepi jps  # On worker 1
ssh blueberrypi jps  # On worker 2

# Check temperatures
echo "Master: $(vcgencmd measure_temp)"
echo "Worker 1: $(ssh applepi vcgencmd measure_temp)"
echo "Worker 2: $(ssh blueberrypi vcgencmd measure_temp)"
```

## Troubleshooting Quick Fixes

### Workers Not Showing Up

```bash
# Restart cluster
$SPARK_HOME/sbin/stop-all.sh
sleep 5
$SPARK_HOME/sbin/start-master.sh
sleep 5
$SPARK_HOME/sbin/start-workers.sh

# Check web UI: http://raspberrypi:8080
```

### Out of Memory

```bash
# Reduce executor memory
spark-submit --executor-memory 2g ...

# Or reduce dataset size
# Edit configs/your_experiment.yaml:
# points:
#   n_points: 100000  # Reduce this
```

### Slow Performance

```bash
# Check temperature (should be < 70°C)
vcgencmd measure_temp

# Check for disk spills (should be 0!)
# Spark UI → Stages → Spill (Memory) and Spill (Disk)

# Reduce parallelism if spilling
spark-submit --conf spark.default.parallelism=24 ...
```

### Job Stuck

```bash
# Check Spark UI for errors
# http://raspberrypi:4040 → Stages → Failed stages

# Kill application
# Get app ID from Spark UI, then:
$SPARK_HOME/bin/spark-class org.apache.spark.deploy.Client \
    kill spark://raspberrypi:7077 app-XXXXXXXX-XXXX
```

## Experiment Checklist

Before running an experiment:

- [ ] Cluster is running (check `http://raspberrypi:8080`)
- [ ] 2 workers connected (8 cores, 12GB total)
- [ ] NFS mounted on workers (`df -h | grep /data`)
- [ ] Enough space on SSD (`df -h /data`)
- [ ] Temperature reasonable (< 65°C)
- [ ] Config file edited if needed
- [ ] Output directory doesn't exist (or will overwrite)

After running an experiment:

- [ ] Check Spark UI for stages (should be 3k stages for k circles)
- [ ] Verify no disk spills (Stages → Spill metrics = 0)
- [ ] Results saved (`ls /data/results/experiment_name/`)
- [ ] Take screenshots of Spark UI for research questions
- [ ] Note runtime and resource usage
- [ ] Copy results to computer for analysis (optional)

## Performance Expectations

| Experiment | Points | Circles | k | Partitions | Expected Time | Coverage |
|------------|--------|---------|---|------------|---------------|----------|
| Small | 10K | 1K | 5 | 12 | < 1 min | 70-90% |
| Medium | 1M | 10K | 10 | 24 | ~10 min | 70-85% |
| Large | 10M | 50K | 20 | 36 | 1-2 hr | 60-80% |

Actual results depend on:
- Data distribution (clustered vs uniform)
- Circle sizes (larger radius = more coverage)
- Random seed
- Cluster temperature (throttling if hot)

## Research Data Collection

For answering research questions, collect:

1. **Spark UI Screenshots:**
   - DAG visualization (Stages tab)
   - Stage details (duration, tasks, shuffle)
   - Storage tab (RDD persistence)

2. **Metrics from Iteration Results:**
   - Coverage progression
   - Runtime per iteration
   - Marginal gains (submodularity)

3. **System Metrics:**
   - Memory usage (executor metrics)
   - Disk I/O (should be minimal)
   - Network transfer (shuffle read/write)
   - Temperature logs

4. **Configuration:**
   - Partition counts
   - Executor settings
   - Data sizes

## Next Steps

1. Run all three experiments (small, medium, large)
2. Analyze with Jupyter notebook
3. Document MapReduce observations
4. Answer research questions
5. Optimize and re-run if needed

**Happy experimenting! 🎉**
