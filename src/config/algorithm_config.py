import yaml


class AlgorithmConfig:
    """Configuration for greedy algorithm parameters"""

    def __init__(self, k, checkpoint_interval=5, checkpoint_dir=None):
        """
        Args:
            k: Number of circles to select
            checkpoint_interval: Checkpoint RDD lineage every N iterations
            checkpoint_dir: Directory for checkpoints (None = no checkpointing)
        """
        self.k = k
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_dir = checkpoint_dir

    @classmethod
    def from_yaml(cls, yaml_path):
        """
        Load configuration from YAML file.

        Args:
            yaml_path: Path to YAML configuration file

        Returns:
            AlgorithmConfig instance

        YAML format:
            algorithm:
              k: 10
              checkpoint_interval: 5
              checkpoint_dir: "/data/checkpoints"
        """
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)

        algo_config = config.get('algorithm', {})
        return cls(
            k=algo_config.get('k', 10),
            checkpoint_interval=algo_config.get('checkpoint_interval', 5),
            checkpoint_dir=algo_config.get('checkpoint_dir', None)
        )

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'k': self.k,
            'checkpoint_interval': self.checkpoint_interval,
            'checkpoint_dir': self.checkpoint_dir
        }

    def __repr__(self):
        return f"AlgorithmConfig(k={self.k}, checkpoint_interval={self.checkpoint_interval})"
