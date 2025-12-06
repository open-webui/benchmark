"""
Configuration management for the benchmark suite.

Handles loading and validating configuration from YAML files and environment variables.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ResourceConfig(BaseModel):
    """Docker resource constraints configuration."""
    cpus: float = 2.0
    memory: str = "8g"
    memory_swap: str = "8g"
    memory_reservation: str = "4g"


class DockerConfig(BaseModel):
    """Docker-specific configuration."""
    cpu_shares: int = 1024
    cpu_period: int = 100000
    cpu_quota: int = 200000


class ComputeProfile(BaseModel):
    """A compute profile defining resource constraints."""
    name: str
    description: str
    resources: ResourceConfig
    docker: DockerConfig


class TestUserConfig(BaseModel):
    """Configuration for test users."""
    email: str
    password: str
    name: str
    role: str = "user"


class TestUserTemplateConfig(BaseModel):
    """Template for generating test users."""
    email_pattern: str = "user{n}@benchmark.local"
    password: str = "benchmark_user_password_123"
    name_pattern: str = "Test User {n}"
    role: str = "user"


class ThresholdsConfig(BaseModel):
    """Performance thresholds for pass/fail criteria."""
    max_response_time_ms: int = 2000
    max_p95_response_time_ms: int = 3000
    max_error_rate_percent: float = 1.0
    min_requests_per_second: float = 10.0


class ChannelBenchmarkConfig(BaseModel):
    """Channel-specific benchmark configuration."""
    max_concurrent_users: int = 100
    user_step_size: int = 10
    ramp_up_time: int = 5
    sustain_time: int = 30
    message_frequency: float = 0.5
    message_size: Dict[str, int] = Field(default_factory=lambda: {"min": 50, "max": 500, "avg": 200})


class OutputConfig(BaseModel):
    """Output configuration for benchmark results."""
    results_dir: str = "results"
    formats: List[str] = Field(default_factory=lambda: ["json", "csv"])
    include_timing_details: bool = True
    include_resource_metrics: bool = True


class BenchmarkConfig(BaseModel):
    """Main benchmark configuration."""
    target_url: str = "http://localhost:3000"
    request_timeout: int = 30
    websocket_timeout: int = 60
    iterations: int = 3
    warmup_requests: int = 10
    cooldown_seconds: int = 5
    
    # Sub-configurations
    output: OutputConfig = Field(default_factory=OutputConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    channels: ChannelBenchmarkConfig = Field(default_factory=ChannelBenchmarkConfig)
    
    # Compute profile
    compute_profile: Optional[ComputeProfile] = None
    
    # Test users - loaded from environment variables
    admin_user: Optional[TestUserConfig] = None
    test_user: Optional[TestUserConfig] = None  # Single test user for benchmarks
    user_template: TestUserTemplateConfig = Field(default_factory=TestUserTemplateConfig)
    
    # Use single user for all concurrent connections (simpler setup)
    use_single_user: bool = True


class ConfigLoader:
    """Loads and manages benchmark configuration."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the config loader.
        
        Args:
            config_dir: Path to configuration directory. If None, uses default.
        """
        if config_dir is None:
            # Default to benchmark/config directory
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        
        self._compute_profiles: Dict[str, ComputeProfile] = {}
        self._benchmark_config: Optional[BenchmarkConfig] = None
        
    def load_compute_profiles(self) -> Dict[str, ComputeProfile]:
        """Load compute profiles from YAML file."""
        profiles_file = self.config_dir / "compute_profiles.yaml"
        
        if not profiles_file.exists():
            raise FileNotFoundError(f"Compute profiles file not found: {profiles_file}")
        
        with open(profiles_file, 'r') as f:
            data = yaml.safe_load(f)
        
        profiles = {}
        for profile_id, profile_data in data.get("profiles", {}).items():
            profiles[profile_id] = ComputeProfile(
                name=profile_data["name"],
                description=profile_data["description"],
                resources=ResourceConfig(**profile_data["resources"]),
                docker=DockerConfig(**profile_data["docker"]),
            )
        
        self._compute_profiles = profiles
        return profiles
    
    def get_compute_profile(self, profile_id: str) -> ComputeProfile:
        """Get a specific compute profile by ID."""
        if not self._compute_profiles:
            self.load_compute_profiles()
        
        if profile_id not in self._compute_profiles:
            raise ValueError(f"Unknown compute profile: {profile_id}")
        
        return self._compute_profiles[profile_id]
    
    def load_benchmark_config(
        self, 
        profile_id: str = "default",
        overrides: Optional[Dict[str, Any]] = None
    ) -> BenchmarkConfig:
        """
        Load benchmark configuration with optional overrides.
        
        Args:
            profile_id: Compute profile to use
            overrides: Dictionary of configuration overrides
            
        Returns:
            BenchmarkConfig instance
        """
        config_file = self.config_dir / "benchmark_config.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Benchmark config file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        # Build configuration from YAML
        benchmark_data = data.get("benchmark", {})
        output_data = data.get("output", {})
        thresholds_data = data.get("thresholds", {})
        channels_data = data.get("channels", {})
        test_users_data = data.get("test_users", {})
        
        # Apply environment variable overrides for target URL
        target_url = os.environ.get("OPEN_WEBUI_URL", 
                     os.environ.get("BENCHMARK_TARGET_URL", 
                     benchmark_data.get("target_url")))
        
        # Load user credentials from environment variables (like the tests framework)
        admin_email = os.environ.get("ADMIN_USER_EMAIL")
        admin_password = os.environ.get("ADMIN_USER_PASSWORD")
        test_email = os.environ.get("TEST_USER_EMAIL")
        test_password = os.environ.get("TEST_USER_PASSWORD")
        use_single_user = os.environ.get("USE_SINGLE_USER", "true").lower() == "true"
        
        # Override channel settings from environment
        max_users = os.environ.get("MAX_CONCURRENT_USERS")
        user_step = os.environ.get("USER_STEP_SIZE")
        sustain_time = os.environ.get("SUSTAIN_TIME_SECONDS")
        msg_freq = os.environ.get("MESSAGE_FREQUENCY")
        
        channels_config = ChannelBenchmarkConfig(**channels_data) if channels_data else ChannelBenchmarkConfig()
        if max_users:
            channels_config.max_concurrent_users = int(max_users)
        if user_step:
            channels_config.user_step_size = int(user_step)
        if sustain_time:
            channels_config.sustain_time = int(sustain_time)
        if msg_freq:
            channels_config.message_frequency = float(msg_freq)
        
        config = BenchmarkConfig(
            target_url=target_url,
            request_timeout=benchmark_data.get("request_timeout", 30),
            websocket_timeout=benchmark_data.get("websocket_timeout", 60),
            iterations=benchmark_data.get("iterations", 3),
            warmup_requests=benchmark_data.get("warmup_requests", 10),
            cooldown_seconds=benchmark_data.get("cooldown_seconds", 5),
            output=OutputConfig(**output_data) if output_data else OutputConfig(),
            thresholds=ThresholdsConfig(**thresholds_data) if thresholds_data else ThresholdsConfig(),
            channels=channels_config,
            compute_profile=self.get_compute_profile(profile_id),
            use_single_user=use_single_user,
        )
        
        # Set admin user from environment variables (preferred) or YAML config
        if admin_email and admin_password:
            config.admin_user = TestUserConfig(
                email=admin_email,
                password=admin_password,
                name="Admin User",
                role="admin",
            )
        elif "admin" in test_users_data:
            config.admin_user = TestUserConfig(**test_users_data["admin"])
        
        # Set test user from environment variables
        if test_email and test_password:
            config.test_user = TestUserConfig(
                email=test_email,
                password=test_password,
                name="Test User",
                role="user",
            )
        
        # Set user template if configured
        if "user_template" in test_users_data:
            config.user_template = TestUserTemplateConfig(**test_users_data["user_template"])
        
        # Apply any additional overrides
        if overrides:
            for key, value in overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        self._benchmark_config = config
        return config
    
    @property
    def config(self) -> BenchmarkConfig:
        """Get the current benchmark configuration."""
        if self._benchmark_config is None:
            self._benchmark_config = self.load_benchmark_config()
        return self._benchmark_config


# Global config loader instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """Get the global config loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def load_config(
    profile_id: str = "default",
    config_dir: Optional[Path] = None,
    overrides: Optional[Dict[str, Any]] = None
) -> BenchmarkConfig:
    """
    Convenience function to load benchmark configuration.
    
    Args:
        profile_id: Compute profile to use
        config_dir: Optional custom config directory
        overrides: Optional configuration overrides
        
    Returns:
        BenchmarkConfig instance
    """
    loader = ConfigLoader(config_dir) if config_dir else get_config_loader()
    return loader.load_benchmark_config(profile_id, overrides)
