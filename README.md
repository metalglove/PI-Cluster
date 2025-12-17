# PySpark - PI Cluster - MapReduce
In this repository the configuration and motivation behind design decisions of the pi cluster using PySpark is documented.

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

> **NOTE:** We must also ensure that our network and SSH configuration allow the nodes to communicate. Furthermore, we must also consider that the master worker will likely be an NFS storage pool for all the partitions to be fetched from initially. Or, dedicate an extra node for storage?

>**TODO:** bill of materials

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
> TODO: figure out how