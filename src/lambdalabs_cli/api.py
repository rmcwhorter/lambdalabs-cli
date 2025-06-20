import requests
from typing import List, Dict, Any, Optional
from .config import Config


class LambdaLabsAPI:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = "https://cloud.lambda.ai/api/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def list_instances(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/instances")["data"]

    def get_instance(self, instance_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/instances/{instance_id}")["data"]

    def launch_instance(self, instance_type: str, region: str, ssh_key_names: List[str], 
                       filesystem_names: Optional[List[str]] = None,
                       name: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "instance_type_name": instance_type,
            "region_name": region,
            "ssh_key_names": ssh_key_names,
        }
        
        if filesystem_names:
            payload["filesystem_names"] = filesystem_names
        if name:
            payload["name"] = name
            
        return self._request("POST", "/instance-operations/launch", json=payload)["data"]

    def terminate_instance(self, instance_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/instance-operations/terminate", 
                           json={"instance_ids": [instance_id]})["data"]

    def terminate_all_instances(self) -> Dict[str, Any]:
        instances = self.list_instances()
        instance_ids = [instance["id"] for instance in instances]
        if not instance_ids:
            return {"terminated_instances": []}
        
        return self._request("POST", f"/instance-operations/terminate", 
                           json={"instance_ids": instance_ids})["data"]

    def list_instance_types(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/instance-types")["data"]
        instance_types = []
        for key, value in data.items():
            instance_type = value["instance_type"]
            instance_type["regions_available"] = value.get("regions_with_capacity_available", [])
            instance_types.append(instance_type)
        return instance_types

    def list_regions(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/instance-types")["data"]
        regions = set()
        for key, value in data.items():
            for region in value.get("regions_with_capacity_available", []):
                regions.add((region["name"], region["description"]))
        return [{"name": name, "description": desc} for name, desc in regions]

    def list_ssh_keys(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/ssh-keys")["data"]

    def add_ssh_key(self, name: str, public_key: str) -> Dict[str, Any]:
        return self._request("POST", "/ssh-keys", 
                           json={"name": name, "public_key": public_key})["data"]

    def list_filesystems(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/file-systems")["data"]

    def create_filesystem(self, name: str, region: str) -> Dict[str, Any]:
        return self._request("POST", "/file-systems", 
                           json={"name": name, "region_name": region})["data"]

    def delete_filesystem(self, filesystem_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/file-systems/{filesystem_id}")

    def rotate_api_key(self) -> Dict[str, Any]:
        return self._request("POST", "/api-keys/rotate")["data"]