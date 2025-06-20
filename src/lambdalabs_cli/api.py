import requests
import time
from typing import List, Dict, Any, Optional
from .config import Config
from .logging_config import get_logger

logger = get_logger("api")


class LambdaLabsAPI:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = "https://cloud.lambda.ai/api/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        })

    def _request(self, method: str, endpoint: str, retries: int = 3, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Making {method} request to {url}")
        
        for attempt in range(retries):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
                logger.debug(f"Response status: {response.status_code}")
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                # Don't retry on client errors (4xx)
                if response.status_code < 500:
                    logger.error(f"HTTP client error: {method} {url} - {e}")
                    raise
                # Retry on server errors (5xx)
                if attempt < retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"HTTP server error (attempt {attempt + 1}/{retries}): {method} {url} - {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"HTTP server error after {retries} attempts: {method} {url} - {e}")
                raise
                
            except requests.exceptions.ConnectionError as e:
                if attempt < retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error (attempt {attempt + 1}/{retries}): {method} {url} - {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Connection error after {retries} attempts: {method} {url} - {e}")
                raise
                
            except requests.exceptions.Timeout as e:
                if attempt < retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Request timeout (attempt {attempt + 1}/{retries}): {method} {url} - {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Request timeout after {retries} attempts: {method} {url} - {e}")
                raise
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {method} {url} - {e}")
                raise
                
        # This should never be reached
        raise RuntimeError("Unexpected error in request retry logic")

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