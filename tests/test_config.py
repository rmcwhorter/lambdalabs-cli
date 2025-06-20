"""Tests for configuration management."""
import pytest
import toml
from pathlib import Path
from unittest.mock import patch, mock_open

from lambdalabs_cli.config import Config


def test_config_initialization_new_config(temp_config_dir):
    """Test config initialization with no existing config file."""
    config = Config()
    
    # Should create default config
    assert config.api_key == ""
    assert config.ssh_dir.endswith("/.ssh")
    assert config.default_filesystem is None
    
    # Should save config file
    assert config.config_file.exists()


def test_config_initialization_existing_config(temp_config_dir):
    """Test config initialization with existing config file."""
    # Create existing config
    config_file = temp_config_dir / "config.toml"
    config_data = {
        "api_key": "existing-key",
        "ssh_dir": "/custom/ssh",
        "default_filesystem": "existing-fs"
    }
    
    with open(config_file, "w") as f:
        toml.dump(config_data, f)
    
    config = Config()
    
    assert config.api_key == "existing-key"
    assert config.ssh_dir == "/custom/ssh"
    assert config.default_filesystem == "existing-fs"


def test_config_setters(temp_config_dir):
    """Test config property setters."""
    config = Config()
    
    # Test API key setter
    config.api_key = "new-api-key"
    assert config.api_key == "new-api-key"
    
    # Verify it's saved to file
    saved_config = toml.load(config.config_file)
    assert saved_config["api_key"] == "new-api-key"
    
    # Test SSH dir setter
    config.ssh_dir = "/new/ssh/dir"
    assert config.ssh_dir == "/new/ssh/dir"
    
    # Test default filesystem setter
    config.default_filesystem = "new-fs"
    assert config.default_filesystem == "new-fs"


def test_get_ssh_public_key_found():
    """Test SSH public key detection when key exists."""
    mock_key_content = "ssh-rsa AAAAB3NzaC1yc2EAAA... test@example.com"
    
    with patch('pathlib.Path.exists') as mock_exists, \
         patch('pathlib.Path.read_text') as mock_read:
        
        # Mock that id_rsa.pub exists and return mock content
        mock_exists.return_value = True
        mock_read.return_value = f"{mock_key_content}\n"
        
        config = Config()
        config.ssh_dir = "/test/ssh"
        
        result = config.get_ssh_public_key()
        assert result == mock_key_content


def test_get_ssh_public_key_not_found():
    """Test SSH public key detection when no keys exist."""
    with patch('pathlib.Path.exists') as mock_exists:
        mock_exists.return_value = False
        
        config = Config()
        config.ssh_dir = "/test/ssh"
        
        result = config.get_ssh_public_key()
        assert result is None


def test_get_ssh_public_key_multiple_types():
    """Test SSH public key detection with multiple key types."""
    mock_key_content = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... test@example.com"
    
    with patch('pathlib.Path.exists') as mock_exists, \
         patch('pathlib.Path.read_text') as mock_read:
        
        # Mock that only ed25519 key exists
        def exists_side_effect(path):
            return "id_ed25519.pub" in str(path)
        
        mock_exists.side_effect = exists_side_effect
        mock_read.return_value = f"{mock_key_content}\n"
        
        config = Config()
        config.ssh_dir = "/test/ssh"
        
        result = config.get_ssh_public_key()
        assert result == mock_key_content


def test_config_default_values():
    """Test that default config has expected values."""
    with patch.object(Config, 'save'):  # Don't actually save during test
        config = Config()
        defaults = config.default_config()
        
        assert defaults["api_key"] == ""
        assert defaults["ssh_dir"].endswith("/.ssh")
        assert defaults["default_filesystem"] is None


def test_config_directory_creation(temp_config_dir):
    """Test that config directory is created if it doesn't exist."""
    # Remove the directory
    config_dir = temp_config_dir
    config_dir.rmdir()
    
    config = Config()
    config.save()  # This should create the directory
    
    assert config_dir.exists()
    assert config.config_file.exists()