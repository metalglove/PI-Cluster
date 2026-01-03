from pyspark import SparkConf


class SparkClusterConfig:
    """Configuration for Raspberry Pi cluster Spark setup"""

    # Cluster specifications
    N_NODES = 3
    N_CORES_PER_NODE = 4
    RAM_PER_NODE_GB = 8

    # Partition sizing (in MB)
    TARGET_PARTITION_SIZE_MB = 160  # Middle of 128-192 range
    MIN_PARTITION_SIZE_MB = 128
    MAX_PARTITION_SIZE_MB = 192

    @staticmethod
    def get_spark_conf(app_name="GreedySubmodularCircleCover", master=None):
        """
        Generate SparkConf optimized for Raspberry Pi cluster.

        Args:
            app_name: Application name
            master: Spark master URL (e.g., "spark://raspberrypi:7077")
                   If None, uses local mode for testing

        Returns:
            SparkConf object configured for Pi cluster
        """
        conf = SparkConf().setAppName(app_name)

        if master:
            conf.setMaster(master)
        else:
            # Local mode for testing
            conf.setMaster("local[*]")

        # Executor configuration
        # Use 2 cores per executor to balance parallelism and memory
        conf.set("spark.executor.cores", "2")
        conf.set("spark.executor.memory", "3g")
        conf.set("spark.executor.memoryOverhead", "1g")

        # Driver configuration (runs on master node)
        conf.set("spark.driver.memory", "2g")
        conf.set("spark.driver.memoryOverhead", "512m")

        # Partitioning
        # Total cores in cluster
        total_cores = SparkClusterConfig.N_NODES * SparkClusterConfig.N_CORES_PER_NODE

        # Default parallelism: 2-3x number of cores for better load balancing
        conf.set("spark.default.parallelism", str(total_cores * 3))

        # Shuffle partitions (for reduce operations)
        conf.set("spark.sql.shuffle.partitions", str(total_cores * 2))

        # Shuffle configuration - minimize disk writes on SD cards
        conf.set("spark.shuffle.compress", "true")
        conf.set("spark.shuffle.spill.compress", "true")
        conf.set("spark.shuffle.file.buffer", "64k")  # Reduce buffer size for lower memory

        # Serialization - use Kryo for better performance
        conf.set("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        conf.set("spark.kryoserializer.buffer.max", "64m")

        # Broadcast configuration
        conf.set("spark.broadcast.blockSize", "4m")
        conf.set("spark.broadcast.compress", "true")

        # Storage configuration - prefer memory to avoid SD card writes
        conf.set("spark.storage.memoryFraction", "0.6")
        conf.set("spark.memory.fraction", "0.6")
        conf.set("spark.memory.storageFraction", "0.5")

        # Network configuration
        conf.set("spark.network.timeout", "800s")
        conf.set("spark.rpc.askTimeout", "600s")
        conf.set("spark.rpc.lookupTimeout", "600s")

        # Speculation - retry slow tasks
        conf.set("spark.speculation", "true")
        conf.set("spark.speculation.interval", "100ms")
        conf.set("spark.speculation.multiplier", "3")

        # Checkpointing
        conf.set("spark.cleaner.referenceTracking.cleanCheckpoints", "true")

        return conf

    @staticmethod
    def calculate_partitions(data_size_mb, target_partition_mb=None):
        """
        Calculate optimal number of partitions for given data size.

        Args:
            data_size_mb: Total data size in MB
            target_partition_mb: Target partition size (uses TARGET_PARTITION_SIZE_MB if None)

        Returns:
            Recommended number of partitions
        """
        if target_partition_mb is None:
            target_partition_mb = SparkClusterConfig.TARGET_PARTITION_SIZE_MB

        n_partitions = int(data_size_mb / target_partition_mb)

        # Ensure at least as many partitions as cores
        min_partitions = SparkClusterConfig.N_NODES * SparkClusterConfig.N_CORES_PER_NODE

        return max(n_partitions, min_partitions)

    @staticmethod
    def estimate_data_size_mb(n_points, bytes_per_point=32):
        """
        Estimate data size for points.

        Args:
            n_points: Number of points
            bytes_per_point: Bytes per point (default 32: 8 bytes each for id, x, y, cluster_id)

        Returns:
            Estimated size in MB
        """
        bytes_total = n_points * bytes_per_point
        mb_total = bytes_total / (1024 * 1024)
        return mb_total

    @staticmethod
    def get_executor_info():
        """
        Get executor configuration summary.

        Returns:
            Dictionary with executor configuration
        """
        return {
            'n_nodes': SparkClusterConfig.N_NODES,
            'cores_per_node': SparkClusterConfig.N_CORES_PER_NODE,
            'total_cores': SparkClusterConfig.N_NODES * SparkClusterConfig.N_CORES_PER_NODE,
            'ram_per_node_gb': SparkClusterConfig.RAM_PER_NODE_GB,
            'executor_memory_gb': 3,
            'executor_overhead_gb': 1,
            'driver_memory_gb': 2,
            'target_partition_size_mb': SparkClusterConfig.TARGET_PARTITION_SIZE_MB
        }
