import os
import toml
from pathlib import Path
from typing import Optional, Dict, Any
from .logging_config import get_logger

logger = get_logger("config")


class Config:
    def __init__(self):
        self.config_dir = Path.home() / ".lambdalabs"
        self.config_file = self.config_dir / "config.toml"
        self._config = {}
        self.load()

    def load(self):
        if self.config_file.exists():
            logger.debug(f"Loading config from {self.config_file}")
            try:
                self._config = toml.load(self.config_file)
            except toml.TomlDecodeError as e:
                logger.error(f"Invalid TOML format in config file: {e}")
                raise ValueError(f"Configuration file is corrupted: {e}")
            except OSError as e:
                logger.error(f"Failed to read config file: {e}")
                raise
        else:
            logger.info(f"Config file not found, creating default at {self.config_file}")
            self._config = self.default_config()
            self.save()

    def save(self):
        try:
            self.config_dir.mkdir(exist_ok=True, mode=0o700)  # Secure directory permissions
            logger.debug(f"Saving config to {self.config_file}")
            with open(self.config_file, "w") as f:
                toml.dump(self._config, f)
            # Set secure file permissions (readable/writable by owner only)
            self.config_file.chmod(0o600)
        except OSError as e:
            logger.error(f"Failed to save config file: {e}")
            raise

    def default_config(self) -> Dict[str, Any]:
        ssh_dir = str(Path.home() / ".ssh")
        return {
            "api_key": "",
            "ssh_dir": ssh_dir,
            "default_filesystem": None,
        }

    @property
    def api_key(self) -> str:
        return self._config.get("api_key", "")

    @api_key.setter
    def api_key(self, value: str):
        self._config["api_key"] = value
        self.save()

    @property
    def ssh_dir(self) -> str:
        return self._config.get("ssh_dir", str(Path.home() / ".ssh"))

    @ssh_dir.setter
    def ssh_dir(self, value: str):
        self._config["ssh_dir"] = value
        self.save()

    @property
    def default_filesystem(self) -> Optional[str]:
        return self._config.get("default_filesystem")

    @default_filesystem.setter
    def default_filesystem(self, value: Optional[str]):
        self._config["default_filesystem"] = value
        self.save()

    def _validate_ssh_public_key(self, key_content: str) -> bool:
        """Validate SSH public key format."""
        if not key_content:
            return False
        
        # SSH public keys should start with key type and contain base64 data
        parts = key_content.strip().split()
        if len(parts) < 2:
            return False
        
        # Check for valid key types
        valid_key_types = ['ssh-rsa', 'ssh-ed25519', 'ssh-ecdsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521']
        key_type = parts[0]
        
        if key_type not in valid_key_types:
            return False
        
        # Basic check for base64 data (second part should be base64)
        import base64
        try:
            base64.b64decode(parts[1])
        except Exception:
            return False
        
        return True

    def get_ssh_public_key(self) -> Optional[str]:
        ssh_path = Path(self.ssh_dir)
        
        for key_file in ["id_rsa.pub", "id_ed25519.pub", "id_ecdsa.pub"]:
            key_path = ssh_path / key_file
            if key_path.exists():
                try:
                    key_content = key_path.read_text().strip()
                    if self._validate_ssh_public_key(key_content):
                        logger.debug(f"Found valid SSH key: {key_file}")
                        return key_content
                    else:
                        logger.warning(f"Invalid SSH key format in {key_file}")
                except OSError as e:
                    logger.error(f"Failed to read SSH key file {key_file}: {e}")
        
        return None