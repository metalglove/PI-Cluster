# Documentation Index

Complete guide to all documentation in this repository.

## Quick Navigation

### 🚀 Getting Started
1. **[README.md](README.md)** - Project overview and research questions
2. **[PLAN.md](PLAN.md)** - Complete implementation plan and design
3. **[PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)** - Step-by-step cluster setup (4-6 hours)
4. **[QUICK_START.md](QUICK_START.md)** - Daily operations quick reference

### 📊 Analysis & Results
5. **[VALIDATION_RESULTS.md](VALIDATION_RESULTS.md)** - Local testing results
6. **[notebooks/README.md](notebooks/README.md)** - Visualization guide
7. **[notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb)** - Interactive analysis

### 🔬 Research & Comparison
8. **[IMPLEMENTATION_COMPARISON.md](IMPLEMENTATION_COMPARISON.md)** - Comparison with GreedySubmodularV2

---

## Document Purposes

### [README.md](README.md)
**Purpose:** Project overview
**Contents:**
- Research questions
- Cluster hardware specifications
- MapReduce theoretical background
- Quick setup and usage instructions

**Read this first** to understand the project goals.

---

### [PLAN.md](PLAN.md)
**Purpose:** Complete implementation design and architecture
**Contents:**
- Algorithm design (sequential → MapReduce translation)
- Data distribution strategy
- Project structure
- Implementation workflow (5 phases)
- Critical implementation details
- Pi cluster optimizations
- Experimental validation plan

**Read this** to understand the full system design before implementing or modifying code.

**Key sections:**
- MapReduce Translation (3-stage per iteration)
- Data Distribution Strategy (partitioning, broadcast)
- Pi Cluster Specific Optimizations (memory, storage, network)
- Experimental Validation (3 dataset scales)

---

### [PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)
**Purpose:** Complete hardware and software setup guide
**Contents:**
- Hardware requirements and bill of materials
- OS installation (Raspberry Pi OS)
- Network configuration (static IPs, hostnames)
- SSH setup (passwordless access)
- Java and Spark installation
- NFS shared storage configuration
- Spark cluster configuration
- Python environment setup
- Code deployment
- Running experiments
- Monitoring and troubleshooting

**Follow this** to set up your Pi cluster from scratch.

**Time estimate:** 4-6 hours for first-time setup

**Sections:**
1. Hardware Requirements (what to buy)
2-4. OS, Network, SSH (basic setup)
5-7. Java, Spark, NFS (software stack)
8-10. Python, deployment, experiments (application layer)
11. Monitoring and troubleshooting

---

### [QUICK_START.md](QUICK_START.md)
**Purpose:** Fast reference for daily cluster operations
**Contents:**
- Daily workflow (start → run → monitor → stop)
- Common tasks (generate data, run experiments, visualize)
- Troubleshooting quick fixes
- Experiment checklist
- Performance expectations

**Use this** as a cheat sheet once your cluster is set up.

**Most useful for:**
- Starting/stopping cluster
- Running experiments
- Quick troubleshooting

---

### [VALIDATION_RESULTS.md](VALIDATION_RESULTS.md)
**Purpose:** Local testing and validation summary
**Contents:**
- Test results summary (9 tests, all passed)
- What was validated (geometry, MapReduce, greedy logic)
- Fixed issues during validation
- Next steps for deployment

**Read this** to verify the implementation is correct before running on the cluster.

**Confidence level:** HIGH ✓

---

### [notebooks/README.md](notebooks/README.md)
**Purpose:** Guide for using Jupyter notebooks
**Contents:**
- Setup instructions (Jupyter installation)
- Notebook features overview
- Usage instructions
- Example output
- Extension ideas

**Read this** before running the visualization notebook.

---

### [notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb)
**Purpose:** Interactive results analysis and visualization
**Contents:**
- 10 comprehensive analysis sections
- Point distribution plots
- Circle coverage visualization
- Coverage progression charts
- Performance metrics
- MapReduce insights
- Approximation quality analysis
- Summary report generation

**Run this** after completing experiments to analyze results.

**Requirements:** Jupyter, matplotlib, seaborn

---

### [IMPLEMENTATION_COMPARISON.md](IMPLEMENTATION_COMPARISON.md)
**Purpose:** Compare with previous implementation (GreedySubmodularV2)
**Contents:**
- Architecture comparison
- Key differences (MapReduce, state management, partitioning)
- Performance comparison
- Which implementation to use when
- Evolution summary
- Recommendations for improvement

**Read this** to understand how the new implementation improves upon GreedySubmodularV2.

**Key insight:** Both are correct, new one is production-ready and fully distributed.

---

## Document Flow for Different Users

### New User (Never Used Pi Cluster or PySpark)
1. **[README.md](README.md)** - Understand the project
2. **[PLAN.md](PLAN.md)** - Understand the design
3. **[PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)** - Set up your cluster (follow step-by-step)
4. **[QUICK_START.md](QUICK_START.md)** - Run your first experiment
5. **[notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb)** - Analyze results

### Experienced User (Has Pi Cluster, Wants to Run)
1. **[QUICK_START.md](QUICK_START.md)** - Start cluster and run experiments
2. **[PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md)** § 7-10 - Configure Spark and deploy code
3. **[notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb)** - Analyze results

### Developer (Wants to Modify Code)
1. **[PLAN.md](PLAN.md)** - Understand architecture
2. **[IMPLEMENTATION_COMPARISON.md](IMPLEMENTATION_COMPARISON.md)** - Understand design decisions
3. **[VALIDATION_RESULTS.md](VALIDATION_RESULTS.md)** - Run tests after changes
4. Source code in `src/` directory

### Researcher (Answering Research Questions)
1. **[README.md](README.md)** - Research questions
2. **[PLAN.md](PLAN.md)** § MapReduce Translation - Theoretical mapping
3. Run experiments with **[QUICK_START.md](QUICK_START.md)**
4. Collect data from Spark UI (screenshots)
5. **[notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb)** - Analyze and document

---

## Additional Resources

### Code Documentation

**Algorithm:**
- `src/algorithm/greedy_submodular.py` - Main algorithm orchestration
- `src/mapreduce/mappers.py` - Map functions
- `src/mapreduce/reducers.py` - Reduce functions

**Data:**
- `src/data/generators.py` - Synthetic data generation
- `src/data/schemas.py` - Parquet schemas
- `src/data/loaders.py` - I/O operations

**Configuration:**
- `src/config/spark_config.py` - Pi cluster Spark settings
- `src/config/algorithm_config.py` - Algorithm parameters
- `configs/*.yaml` - Experiment configurations

**Scripts:**
- `scripts/generate_data.py` - Data generation CLI
- `scripts/run_experiment.py` - End-to-end experiment runner
- `src/main.py` - Main algorithm entry point

**Tests:**
- `tests/test_geometry.py` - Geometry unit tests (5 tests)
- `tests/test_algorithm.py` - Algorithm integration tests (4 tests)
- `test_algorithm_logic.py` - Standalone validation (no Spark needed)

---

## Documentation Status

| Document | Status | Last Updated | Words |
|----------|--------|--------------|-------|
| README.md | ✅ Complete | 2025-01-03 | ~800 |
| PLAN.md | ✅ Complete | 2025-01-03 | ~4,500 |
| PI_CLUSTER_SETUP.md | ✅ Complete | 2025-01-03 | ~5,000 |
| QUICK_START.md | ✅ Complete | 2025-01-03 | ~1,500 |
| VALIDATION_RESULTS.md | ✅ Complete | 2025-01-03 | ~800 |
| IMPLEMENTATION_COMPARISON.md | ✅ Complete | 2025-01-03 | ~3,000 |
| notebooks/README.md | ✅ Complete | 2025-01-03 | ~600 |
| notebooks/visualize_results.ipynb | ✅ Complete | 2025-01-03 | ~2,000 |

**Total documentation:** ~18,200 words

---

## FAQs

**Q: Where do I start?**
A: Read [README.md](README.md) → [PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md) → [QUICK_START.md](QUICK_START.md)

**Q: How do I set up the cluster?**
A: Follow [PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md) step-by-step (4-6 hours)

**Q: How do I run an experiment?**
A: See [QUICK_START.md](QUICK_START.md) § 2. Run an Experiment

**Q: How do I visualize results?**
A: Open [notebooks/visualize_results.ipynb](notebooks/visualize_results.ipynb) in Jupyter

**Q: How does this compare to GreedySubmodularV2?**
A: Read [IMPLEMENTATION_COMPARISON.md](IMPLEMENTATION_COMPARISON.md)

**Q: What if I encounter errors?**
A: Check [PI_CLUSTER_SETUP.md](PI_CLUSTER_SETUP.md) § 11 Monitoring and Troubleshooting

**Q: How do I modify the algorithm?**
A: Read [PLAN.md](PLAN.md) for architecture, then edit `src/algorithm/greedy_submodular.py`

**Q: How do I answer the research questions?**
A: Run experiments, collect Spark UI data, analyze with notebook, document findings

---

## Contributing

If you add new documentation:
1. Add it to this index
2. Update the Table of Contents
3. Add cross-references to related documents
4. Update the Documentation Status table

---

## Quick Command Reference

```bash
# Set up cluster
# → Follow PI_CLUSTER_SETUP.md

# Start cluster
$SPARK_HOME/sbin/start-master.sh
$SPARK_HOME/sbin/start-workers.sh

# Run experiment
spark-submit --master spark://raspberrypi:7077 \
    --executor-memory 3g --executor-cores 2 \
    scripts/run_experiment.py \
    --config configs/small_experiment.yaml

# Visualize
jupyter notebook notebooks/visualize_results.ipynb

# Stop cluster
$SPARK_HOME/sbin/stop-all.sh
```

---

**Last updated:** 2025-01-03
**Repository:** https://github.com/yourusername/PI-Cluster
