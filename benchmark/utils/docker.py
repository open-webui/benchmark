"""
Docker utilities for benchmark environment management.

Provides functions for managing Docker containers with specific resource constraints.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    import docker
    from docker.models.containers import Container
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    Container = None

from benchmark.core.config import ComputeProfile


@dataclass
class ContainerStats:
    """Container resource usage statistics."""
    cpu_percent: float
    memory_usage_mb: float
    memory_limit_mb: float
    memory_percent: float
    network_rx_bytes: int
    network_tx_bytes: int
    timestamp: float


class DockerManager:
    """
    Manages Docker containers for benchmark environments.
    
    Provides methods for starting, stopping, and monitoring
    Open WebUI containers with specific resource constraints.
    """
    
    def __init__(self):
        """Initialize the Docker manager."""
        if not DOCKER_AVAILABLE:
            raise ImportError("Docker SDK not available. Install with: pip install docker")
        
        self._client = docker.from_env()
        self._containers: Dict[str, Container] = {}
    
    def start_open_webui(
        self,
        profile: ComputeProfile,
        name: str = "open-webui-benchmark",
        image: str = "ghcr.io/open-webui/open-webui:main",
        port: int = 3000,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, Dict]] = None,
    ) -> Container:
        """
        Start an Open WebUI container with specified resource constraints.
        
        Args:
            profile: Compute profile defining resource constraints
            name: Container name
            image: Docker image to use
            port: Host port to expose
            environment: Additional environment variables
            volumes: Volume mounts
            
        Returns:
            Container instance
        """
        # Remove existing container if present
        try:
            existing = self._client.containers.get(name)
            existing.remove(force=True)
        except docker.errors.NotFound:
            pass
        
        # Build environment
        env = {
            "WEBUI_SECRET_KEY": "benchmark-secret-key",
        }
        if environment:
            env.update(environment)
        
        # Build volume mounts
        vol_mounts = {}
        if volumes:
            vol_mounts.update(volumes)
        
        # Calculate resource constraints
        resources = profile.resources
        docker_config = profile.docker
        
        # Convert memory string to bytes
        memory_limit = self._parse_memory(resources.memory)
        memory_reservation = self._parse_memory(resources.memory_reservation)
        memswap_limit = self._parse_memory(resources.memory_swap)
        
        # Start container
        container = self._client.containers.run(
            image=image,
            name=name,
            detach=True,
            ports={"8080/tcp": port},
            environment=env,
            volumes=vol_mounts,
            # Resource constraints
            cpu_shares=docker_config.cpu_shares,
            cpu_period=docker_config.cpu_period,
            cpu_quota=docker_config.cpu_quota,
            mem_limit=memory_limit,
            mem_reservation=memory_reservation,
            memswap_limit=memswap_limit,
            # Other options
            restart_policy={"Name": "unless-stopped"},
            remove=False,
        )
        
        self._containers[name] = container
        return container
    
    def stop_container(self, name: str, timeout: int = 10) -> bool:
        """
        Stop and remove a container.
        
        Args:
            name: Container name
            timeout: Timeout for graceful stop
            
        Returns:
            True if successful
        """
        try:
            container = self._containers.get(name)
            if container is None:
                container = self._client.containers.get(name)
            
            container.stop(timeout=timeout)
            container.remove()
            
            if name in self._containers:
                del self._containers[name]
            
            return True
        except Exception:
            return False
    
    def get_container_stats(self, name: str) -> Optional[ContainerStats]:
        """
        Get current resource usage statistics for a container.
        
        Args:
            name: Container name
            
        Returns:
            ContainerStats or None if container not found
        """
        try:
            container = self._containers.get(name)
            if container is None:
                container = self._client.containers.get(name)
            
            stats = container.stats(stream=False)
            
            # Calculate CPU percentage
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"] -
                stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"] -
                stats["precpu_stats"]["system_cpu_usage"]
            )
            num_cpus = stats["cpu_stats"]["online_cpus"]
            
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * num_cpus * 100
            else:
                cpu_percent = 0.0
            
            # Calculate memory usage
            memory_usage = stats["memory_stats"].get("usage", 0)
            memory_limit = stats["memory_stats"].get("limit", 1)
            memory_percent = (memory_usage / memory_limit) * 100
            
            # Get network stats
            networks = stats.get("networks", {})
            network_rx = sum(net.get("rx_bytes", 0) for net in networks.values())
            network_tx = sum(net.get("tx_bytes", 0) for net in networks.values())
            
            return ContainerStats(
                cpu_percent=cpu_percent,
                memory_usage_mb=memory_usage / (1024 * 1024),
                memory_limit_mb=memory_limit / (1024 * 1024),
                memory_percent=memory_percent,
                network_rx_bytes=network_rx,
                network_tx_bytes=network_tx,
                timestamp=time.time(),
            )
        except Exception:
            return None
    
    async def collect_stats_async(
        self,
        name: str,
        duration: float,
        interval: float = 1.0,
    ) -> List[ContainerStats]:
        """
        Collect container stats over a period of time.
        
        Args:
            name: Container name
            duration: Duration to collect stats
            interval: Time between samples
            
        Returns:
            List of ContainerStats samples
        """
        samples = []
        end_time = time.time() + duration
        
        while time.time() < end_time:
            stats = self.get_container_stats(name)
            if stats:
                samples.append(stats)
            await asyncio.sleep(interval)
        
        return samples
    
    def wait_for_healthy(
        self,
        name: str,
        timeout: float = 60.0,
        interval: float = 2.0,
    ) -> bool:
        """
        Wait for a container to become healthy.
        
        Args:
            name: Container name
            timeout: Maximum time to wait
            interval: Time between checks
            
        Returns:
            True if container is healthy, False if timeout
        """
        try:
            container = self._containers.get(name)
            if container is None:
                container = self._client.containers.get(name)
            
            elapsed = 0.0
            while elapsed < timeout:
                container.reload()
                status = container.status
                
                if status == "running":
                    # Check health if available
                    health = container.attrs.get("State", {}).get("Health", {})
                    health_status = health.get("Status", "none")
                    
                    if health_status in ("healthy", "none"):
                        return True
                
                time.sleep(interval)
                elapsed += interval
            
            return False
        except Exception:
            return False
    
    def _parse_memory(self, memory_str: str) -> int:
        """Parse memory string (e.g., '8g') to bytes."""
        memory_str = memory_str.lower().strip()
        
        multipliers = {
            'b': 1,
            'k': 1024,
            'kb': 1024,
            'm': 1024 * 1024,
            'mb': 1024 * 1024,
            'g': 1024 * 1024 * 1024,
            'gb': 1024 * 1024 * 1024,
        }
        
        for suffix, multiplier in multipliers.items():
            if memory_str.endswith(suffix):
                value = memory_str[:-len(suffix)]
                return int(float(value) * multiplier)
        
        return int(memory_str)
    
    def cleanup_all(self) -> None:
        """Stop and remove all managed containers."""
        for name in list(self._containers.keys()):
            self.stop_container(name)


class DockerComposeManager:
    """
    Manages Docker Compose environments for benchmarking.
    
    Uses existing docker-compose.yaml files from the Open WebUI repository.
    """
    
    def __init__(self, compose_dir: Path):
        """
        Initialize the compose manager.
        
        Args:
            compose_dir: Directory containing docker-compose.yaml
        """
        self.compose_dir = Path(compose_dir)
        self._project_name = "open-webui-benchmark"
    
    async def up(
        self,
        profile: Optional[ComputeProfile] = None,
        build: bool = False,
        detach: bool = True,
    ) -> bool:
        """
        Start the Docker Compose environment.
        
        Args:
            profile: Optional compute profile for resource constraints
            build: Whether to build images
            detach: Whether to run in background
            
        Returns:
            True if successful
        """
        cmd = ["docker", "compose", "-p", self._project_name]
        
        # Add compose file
        compose_file = self.compose_dir / "docker-compose.yaml"
        if compose_file.exists():
            cmd.extend(["-f", str(compose_file)])
        
        cmd.append("up")
        
        if build:
            cmd.append("--build")
        if detach:
            cmd.append("-d")
        
        # TODO: Apply resource constraints from profile
        # This would require modifying the compose file or using override files
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.compose_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        return process.returncode == 0
    
    async def down(self, volumes: bool = False) -> bool:
        """
        Stop the Docker Compose environment.
        
        Args:
            volumes: Whether to remove volumes
            
        Returns:
            True if successful
        """
        cmd = ["docker", "compose", "-p", self._project_name, "down"]
        
        if volumes:
            cmd.append("-v")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.compose_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        await process.communicate()
        return process.returncode == 0
    
    async def logs(self, follow: bool = False, tail: int = 100) -> str:
        """
        Get logs from the Docker Compose environment.
        
        Args:
            follow: Whether to follow logs
            tail: Number of lines to show
            
        Returns:
            Log output
        """
        cmd = ["docker", "compose", "-p", self._project_name, "logs"]
        
        if not follow:
            cmd.extend(["--tail", str(tail)])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.compose_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        return stdout.decode()
