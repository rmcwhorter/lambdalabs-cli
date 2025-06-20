import os
import toml
from pathlib import Path
from typing import Optional, Dict, Any


class Config:
    def __init__(self):
        self.config_dir = Path.home() / ".lambdalabs"
        self.config_file = self.config_dir / "config.toml"
        self._config = {}
        self.load()

    def load(self):
        if self.config_file.exists():
            self._config = toml.load(self.config_file)
        else:
            self._config = self.default_config()
            self.save()

    def save(self):
        self.config_dir.mkdir(exist_ok=True)
        with open(self.config_file, "w") as f:
            toml.dump(self._config, f)

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

    def get_ssh_public_key(self) -> Optional[str]:
        ssh_path = Path(self.ssh_dir)
        
        for key_file in ["id_rsa.pub", "id_ed25519.pub", "id_ecdsa.pub"]:
            key_path = ssh_path / key_file
            if key_path.exists():
                return key_path.read_text().strip()
        
        return None