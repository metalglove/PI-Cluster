# Implementation Plan: PySpark GreedySubmodular CircleCover Algorithm

## Overview
Implement a distributed greedy algorithm for the maximum circle coverage problem using PySpark on a 3-node Raspberry Pi cluster. The algorithm iteratively selects k circles that maximize coverage of a point set P, achieving a 0.5-approximation guarantee.

## Algorithm Design

### Problem Definition
- **Input**: Point set P (n points with x,y coordinates), Candidate circles C (m circles with center and radius), Parameter k
- **Output**: k selected circles maximizing point coverage
- **Guarantee**: 0.5-approximation via greedy submodular optimization

### Sequential Algorithm
```
Initialize: S = ∅ (selected circles), U = P (uncovered points)
For i = 1 to k:
    For each circle c ∈ C \ S:
        Compute gain(c) = |{p ∈ U : p covered by c}|
    Select c* = argmax gain(c)
    S = S ∪ {c*}
    U = U \ {points covered by c*}
Return S
```

### MapReduce Translation
Each iteration consists of 3 stages:

**Stage 1: MAP - Gain Computation**
- Input: Points (partitioned RDD), circles (broadcast), coverage status (broadcast)
- Map operation: Each partition computes local gains for all candidate circles
- Output: Dictionary of circle_id → local_gain per partition

**Stage 2: REDUCE - Find Best Circle**
- Reduce operation: Aggregate local gains across partitions
- Action: Find circle with maximum total gain
- Output: best_circle_id and its gain

**Stage 3: MAP - Update Coverage**
- Map operation: Mark points covered by selected circle
- Action: Collect updates and re-broadcast coverage status
- Output: Updated coverage dictionary for next iteration

**Key Properties**:
- Each iteration = 3 Spark stages (enforced by .collect() actions)
- Total stages for k circles = 3k
- Clear synchronization boundaries ensure MapReduce semantics

## Data Distribution Strategy

### Partitioning
- **Points**: Hash partition by point_id, target 128-192MB per partition
  - For 10M points (320MB raw): use 24-36 partitions (12 cores × 2-3x)
- **Circles**: Broadcast variable (assume < 100K circles = ~2.4MB)
- **Coverage Status**: Broadcast dictionary (10M points × 1 byte = 10MB, optimizable to 1.25MB with bitarray)

### Storage Format (Parquet)
```python
Points: {point_id: long, x: double, y: double, cluster_id: int}
Circles: {circle_id: long, center_x: double, center_y: double, radius: double}
Results: {iteration: int, circle_id: long, gain: long, cumulative_coverage: long, timestamp: timestamp}
```

### Pi Cluster Configuration
- 3 nodes × 4 cores = 12 cores total
- 8GB RAM per node: allocate 2 executors/node × 3GB + 1GB overhead
- Master SSD (256GB) as NFS shared storage
- Minimize disk I/O on worker SD cards (avoid shuffle spills)

## Project Structure

```
PI-Cluster/
├── README.md
├── PLAN.md                           # This file
├── requirements.txt
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── algorithm/
│   │   ├── __init__.py
│   │   ├── greedy_submodular.py      # Main algorithm class with iteration loop
│   │   ├── circle_ops.py             # Circle-point operations
│   │   └── metrics.py                # Coverage metrics
│   │
│   ├── mapreduce/
│   │   ├── __init__.py
│   │   ├── mappers.py                # compute_local_gains, update_coverage
│   │   ├── reducers.py               # aggregate_gains, find_best_circle
│   │   └── partitioners.py           # Custom partitioning if needed
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── generators.py             # Synthetic data (uniform, clustered, grid)
│   │   ├── loaders.py                # Parquet I/O
│   │   └── schemas.py                # Spark schemas
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── spark_config.py           # Pi cluster Spark settings
│   │   └── algorithm_config.py       # Algorithm parameters (k, checkpoint interval)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── geometry.py               # euclidean_distance, is_point_in_circle
│       ├── monitoring.py             # Iteration and resource monitoring
│       └── validation.py             # Input validation
│
├── scripts/
│   ├── generate_data.py              # CLI for data generation
│   ├── run_experiment.py             # CLI for running experiments
│   └── analyze_results.py            # Results analysis
│
├── tests/
│   ├── __init__.py
│   ├── test_algorithm.py             # Algorithm correctness tests
│   ├── test_generators.py            # Data generation tests
│   └── test_geometry.py              # Geometry utility tests
│
├── configs/
│   ├── small_experiment.yaml         # 10K points, 1K circles, k=5
│   ├── medium_experiment.yaml        # 1M points, 10K circles, k=10
│   └── large_experiment.yaml         # 10M points, 50K circles, k=20
│
└── data/                             # Data directory (not in git)
    ├── raw/
    │   ├── points/                   # Point parquet files
    │   └── circles/                  # Circle parquet files
    ├── processed/
    └── results/
```

## Implementation Workflow

### Phase 1: Foundation
1. **Project structure**: Create directories, update requirements.txt (pyspark, pyarrow, pandas, numpy, pyyaml)
2. **Geometry utilities**: src/utils/geometry.py - euclidean_distance, is_point_in_circle with tests
3. **Data schemas**: src/data/schemas.py - Point, Circle, Result schemas
4. **Basic generators**: src/data/generators.py - uniform random points and circles, save to Parquet

### Phase 2: MapReduce Core
1. **Mappers**: src/mapreduce/mappers.py
   - `compute_local_circle_gains(partition, broadcast_circles, broadcast_uncovered, broadcast_selected)`
   - `update_coverage_partition(partition, broadcast_selected_circle, broadcast_uncovered)`
2. **Reducers**: src/mapreduce/reducers.py
   - `aggregate_circle_gains(dict1, dict2)` - merge gain dictionaries
   - `find_best_circle(aggregated_gains)` - return (circle_id, max_gain)
3. **Spark config**: src/config/spark_config.py - Pi cluster optimized settings

### Phase 3: Algorithm Orchestration
1. **Main algorithm**: src/algorithm/greedy_submodular.py
   - `GreedySubmodularCircleCover` class
   - `run(points_rdd, circles_df)` - main iteration loop
   - `_compute_iteration()` - single greedy iteration
   - Broadcast variable management and checkpointing (every 5 iterations)
2. **Integration test**: Small dataset (1K points, 100 circles, k=5), verify correctness

### Phase 4: Data & Experiments
1. **Enhanced generators**: Clustered points (Gaussian mixture), grid patterns, realistic circles
2. **Main entry point**: src/main.py - orchestrate data loading, algorithm run, results saving
3. **Experiment scripts**: scripts/run_experiment.py with YAML config support
4. **Monitoring**: src/utils/monitoring.py - track iteration stats, resource usage

### Phase 5: Testing & Optimization
1. **Comprehensive tests**: Correctness (trivial cases, greedy property), approximation quality
2. **Performance tuning**: Partition sizes, memory allocation, broadcast thresholds
3. **Large-scale validation**: 10M points, monitor for OOM, disk spills, network bottlenecks

## Critical Implementation Details

### GreedySubmodularCircleCover Class (src/algorithm/greedy_submodular.py)
```python
class GreedySubmodularCircleCover:
    def __init__(self, spark_context, k, config):
        self.sc = spark_context
        self.k = k
        self.config = config
        self.monitor = IterationMonitor()

    def run(self, points_rdd, circles_df):
        # Initialize broadcasts
        circles = self.sc.broadcast(circles_df.collect())
        selected = self.sc.broadcast([])
        uncovered = self.sc.broadcast({p.point_id: True for p in points_rdd.collect()})

        selected_circles = []
        cumulative_coverage = 0

        for i in range(1, self.k + 1):
            # Stage 1: Compute gains (MAP)
            gains_rdd = points_rdd.mapPartitions(
                lambda part: compute_local_circle_gains(part, circles, uncovered, selected)
            )

            # Stage 2: Find best (REDUCE + ACTION)
            aggregated = gains_rdd.reduce(aggregate_circle_gains)
            best_circle_id, gain = find_best_circle(aggregated)

            # Stage 3: Update coverage (MAP + ACTION)
            best_circle_bc = self.sc.broadcast(circles.value[best_circle_id])
            coverage_updates = points_rdd.mapPartitions(
                lambda part: update_coverage_partition(part, best_circle_bc, uncovered)
            ).collect()

            # Update state
            selected_circles.append(best_circle_id)
            cumulative_coverage += gain
            selected = self.sc.broadcast(selected_circles)
            uncovered = self.sc.broadcast(merge_coverage_updates(coverage_updates, uncovered.value))

            # Monitor
            self.monitor.record_iteration(i, best_circle_id, gain, cumulative_coverage, duration)

            # Checkpoint periodically
            if i % self.config.checkpoint_interval == 0:
                points_rdd.checkpoint()
                points_rdd.count()  # Force checkpoint

        return selected_circles, self.monitor.iteration_stats
```

### Spark Configuration (src/config/spark_config.py)
```python
class SparkClusterConfig:
    @staticmethod
    def get_spark_conf():
        conf = SparkConf().setAppName("GreedySubmodularCircleCover")
        conf.set("spark.executor.cores", "2")
        conf.set("spark.executor.memory", "3g")
        conf.set("spark.executor.memoryOverhead", "1g")
        conf.set("spark.driver.memory", "2g")
        conf.set("spark.default.parallelism", "36")  # 12 cores × 3
        conf.set("spark.sql.shuffle.partitions", "24")
        conf.set("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        conf.set("spark.storage.memoryFraction", "0.6")
        return conf
```

### Data Generators (src/data/generators.py)
```python
class PointGenerator:
    @staticmethod
    def uniform_random(n_points, bounds=((0, 1000), (0, 1000)), seed=42):
        np.random.seed(seed)
        x_min, x_max = bounds[0]
        y_min, y_max = bounds[1]
        points = [
            (i, np.random.uniform(x_min, x_max), np.random.uniform(y_min, y_max))
            for i in range(n_points)
        ]
        return points

    @staticmethod
    def clustered(n_points, n_clusters=10, cluster_std=50, bounds=((0, 1000), (0, 1000)), seed=42):
        from sklearn.datasets import make_blobs
        X, y = make_blobs(n_samples=n_points, n_features=2, centers=n_clusters,
                         cluster_std=cluster_std, random_state=seed)
        # Rescale to bounds
        # ... implementation
        return points

class CircleGenerator:
    @staticmethod
    def random_centers(n_circles, radius, bounds=((0, 1000), (0, 1000)), seed=42):
        np.random.seed(seed)
        circles = [
            (i, np.random.uniform(*bounds[0]), np.random.uniform(*bounds[1]), radius)
            for i in range(n_circles)
        ]
        return circles
```

## Pi Cluster Specific Optimizations

### Memory Management
- **Partition size**: 128-192MB to fit comfortably in executor memory with overhead
- **Broadcast limits**: Keep < 100MB (circles < 100K, coverage status uses bitarray for 100M+ points)
- **Executor allocation**: 2 executors/node × 3GB = 6GB used, 2GB for OS/driver

### Storage Strategy
- **NFS**: Master's 256GB SSD mounted on workers at /data
- **Input data**: Read from NFS (points and circles parquet)
- **Shuffle**: Use compression, minimize shuffle partitions
- **Results**: Write to NFS (master SSD)
- **Avoid**: Disk spills on SD cards (fatal for performance)

### Checkpointing
- **Frequency**: Every 5 iterations to break lineage
- **Location**: Master SSD /data/checkpoints/
- **Purpose**: Prevent OOM on recomputation with long lineage

### Network Optimization
- **Broadcast**: Torrent-style broadcast for larger variables (spark.broadcast.blockSize = 4m)
- **Shuffle**: Minimize data movement - points stay partitioned, only small dictionaries shuffle
- **Data locality**: Spark schedules tasks near data when possible

## Experimental Validation

### Dataset Configurations
| Scale | Points | Circles | k | Partitions | Expected Runtime |
|-------|--------|---------|---|------------|------------------|
| Small | 10K | 1K | 5 | 12 | < 1 min |
| Medium | 1M | 10K | 10 | 24 | ~10 min |
| Large | 10M | 50K | 20 | 36 | 1-2 hours |

### Metrics to Track
- **Correctness**: Coverage per iteration (monotonic), final coverage vs expected
- **Performance**: Runtime per iteration, memory usage, disk I/O (should be 0), network transfer
- **Scalability**: Compare against sequential baseline, measure speedup

### Research Questions Validation
1. **MapReduce in practice**: Document actual stage boundaries in Spark UI, verify synchronization
2. **Storage**: Track RAM vs disk usage, measure partition sizes and skew
3. **Data representation**: Measure broadcast sizes, serialization overhead, network transfer

## Success Criteria
- ✅ Algorithm selects k circles correctly
- ✅ No disk spills (verify in Spark UI)
- ✅ Memory stays within bounds (< 3GB per executor)
- ✅ Processes 10M points in < 2 hours for k=20
- ✅ Achieves ≥ 0.5 approximation vs optimal (when computable)

## Critical Files to Implement (Priority Order)

1. **src/utils/geometry.py** - Foundation for all geometric operations
2. **src/data/schemas.py** - Data format definitions
3. **src/config/spark_config.py** - Cluster configuration
4. **src/data/generators.py** - Test data creation
5. **src/mapreduce/mappers.py** - Core map logic
6. **src/mapreduce/reducers.py** - Core reduce logic
7. **src/algorithm/greedy_submodular.py** - Main algorithm orchestration
8. **src/main.py** - Entry point
9. **scripts/run_experiment.py** - Experiment runner
10. **tests/** - Comprehensive test suite

## Next Steps
1. Set up project structure and requirements.txt
2. Implement foundation components (geometry, schemas, config)
3. Build data generators and create test datasets
4. Implement MapReduce core (mappers, reducers)
5. Build main algorithm with iteration loop
6. Test on small scale (10K points)
7. Scale up progressively (1M → 10M points)
8. Document findings for research questions
