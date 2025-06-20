"""Test configuration and fixtures."""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from click.testing import CliRunner

from lambdalabs_cli.config import Config
from lambdalabs_cli.api import LambdaLabsAPI
from lambdalabs_cli.cli import cli


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".lambdalabs"
        config_dir.mkdir()
        
        # Patch the config directory
        with patch.object(Config, '__init__') as mock_init:
            def init_with_temp_dir(self):
                self.config_dir = config_dir
                self.config_file = config_dir / "config.toml"
                self._config = {}
                self.load()
            
            mock_init.side_effect = init_with_temp_dir
            yield config_dir


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock(spec=Config)
    config.api_key = "test-api-key"
    config.ssh_dir = "/tmp/.ssh"
    config.default_filesystem = "test-fs"
    config.get_ssh_public_key.return_value = "ssh-rsa AAAA... test@example.com"
    return config


@pytest.fixture
def mock_api():
    """Create a mock Lambda Labs API."""
    api = Mock(spec=LambdaLabsAPI)
    
    # Default mock responses
    api.list_instances.return_value = []
    api.list_instance_types.return_value = [
        {
            "name": "gpu_1x_a10",
            "description": "1x A10 (24 GB PCIe)",
            "regions_available": [{"name": "us-south-1", "description": "Texas, USA"}]
        }
    ]
    api.list_regions.return_value = [
        {"name": "us-south-1", "description": "Texas, USA"}
    ]
    api.list_ssh_keys.return_value = [
        {"id": "key1", "name": "test-key", "public_key": "ssh-rsa AAAA..."}
    ]
    api.list_filesystems.return_value = [
        {"id": "fs1", "name": "test-fs", "region": {"name": "us-south-1"}, "size": 100}
    ]
    
    return api


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def sample_instance():
    """Sample instance data for testing."""
    return {
        "id": "instance-123",
        "name": "test-instance",
        "instance_type": {"name": "gpu_1x_a10"},
        "region": {"name": "us-south-1"},
        "status": "running",
        "ip": "192.168.1.100"
    }


@pytest.fixture
def clean_crontab():
    """Ensure clean crontab state for testing."""
    # Store original crontab
    import subprocess
    try:
        original_crontab = subprocess.run(
            ["crontab", "-l"], 
            capture_output=True, 
            text=True, 
            check=True
        ).stdout
    except subprocess.CalledProcessError:
        original_crontab = ""
    
    # Clear crontab for testing
    subprocess.run(["crontab", "-r"], capture_output=True)
    
    yield
    
    # Restore original crontab
    if original_crontab:
        subprocess.run(
            ["crontab", "-"], 
            input=original_crontab, 
            text=True, 
            capture_output=True
        )