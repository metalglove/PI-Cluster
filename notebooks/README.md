# Visualization Notebooks

This directory contains Jupyter notebooks for visualizing and analyzing Circle Cover algorithm results.

## Setup

1. **Install dependencies** (includes Jupyter, matplotlib, seaborn):
   ```bash
   source ../.venv/bin/activate
   pip install -r ../requirements.txt
   ```

2. **Start Jupyter**:
   ```bash
   jupyter notebook
   ```

   Or use JupyterLab:
   ```bash
   jupyter lab
   ```

## Available Notebooks

### `visualize_results.ipynb`

Comprehensive visualization and analysis of Circle Cover experiment results.

**Features:**
- Point distribution visualization (with cluster coloring)
- Selected circles overlaid on points
- Coverage progression charts
- Marginal gain analysis (submodular property)
- Performance metrics (runtime, throughput)
- MapReduce insights (stages, data sizes)
- Approximation quality analysis
- Detailed summary report

**Usage:**

1. Run an experiment first:
   ```bash
   cd ..
   python3 scripts/run_experiment.py \
       --config configs/small_experiment.yaml \
       --generate-data
   ```

2. Open the notebook and update the configuration cell:
   ```python
   EXPERIMENT_NAME = "small_experiment"  # Change to your experiment
   ```

3. Run all cells to generate visualizations

**What You'll See:**

📊 **Visualizations:**
- Point distribution (scatter plot with clusters)
- Selected circles on points (different colors per iteration)
- Cumulative coverage over iterations
- Marginal gain per iteration (bar chart)
- Diminishing returns curve (submodularity)
- Runtime per iteration
- Coverage vs time tradeoff

📈 **Analysis:**
- Coverage statistics (final coverage %, average gain)
- Performance metrics (runtime, throughput)
- MapReduce stage analysis
- Data size estimates (broadcast variables)
- Approximation quality vs random baseline
- Submodular property verification

## Example Output

After running the notebook on a small experiment (10K points, 1K circles, k=5), you'll see:

```
EXPERIMENT SUMMARY REPORT
======================================================================

1. DATASET
   - Points: 10,000
   - Candidate circles: 1,000
   - Budget k: 5

2. RESULTS
   - Final coverage: 8,432/10,000 (84.32%)
   - Circles selected: 5
   - Average gain: 1,686.4 points/circle

3. PERFORMANCE
   - Total runtime: 3.45s
   - Avg iteration: 0.690s
   - Throughput: 2,443.77 points/sec

4. EFFICIENCY
   - Points per circle: 1,686.40
   - Time per 1000 points: 0.409s

5. ALGORITHM PROPERTIES
   ✓ Submodular diminishing returns observed
   ✓ Monotonic coverage increase
   ✓ Greedy guarantee: ≥ 0.5 optimal
```

## Extending the Notebook

You can extend the notebook to add:

- **Comparison plots**: Compare multiple experiments
- **Heatmaps**: Coverage density visualization
- **Animation**: Animate circle selection over iterations
- **3D plots**: If you have elevation data
- **Cluster analysis**: Deeper analysis of clustered data
- **Spark UI screenshots**: Embed stage visualizations

## Tips

- For large datasets (>1M points), consider downsampling for scatter plots:
  ```python
  sample_points = points_pd.sample(n=10000)
  ```

- Save figures for papers/reports:
  ```python
  plt.savefig('coverage_progression.pdf', dpi=300, bbox_inches='tight')
  ```

- Export data to CSV for external analysis:
  ```python
  results_pd.to_csv('iteration_results.csv', index=False)
  ```
