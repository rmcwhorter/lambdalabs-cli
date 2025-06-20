"""Tests for Lambda Labs API client."""
import pytest
import requests
from unittest.mock import Mock, patch
from requests.exceptions import HTTPError

from lambdalabs_cli.api import LambdaLabsAPI
from lambdalabs_cli.config import Config


@pytest.fixture
def api_client(mock_config):
    """Create API client with mock config."""
    return LambdaLabsAPI(mock_config)


def test_api_initialization(mock_config):
    """Test API client initialization."""
    api = LambdaLabsAPI(mock_config)
    
    assert api.config == mock_config
    assert api.base_url == "https://cloud.lambda.ai/api/v1"
    assert api.session.headers["Authorization"] == f"Bearer {mock_config.api_key}"
    assert api.session.headers["Content-Type"] == "application/json"


@patch('requests.Session.request')
def test_request_success(mock_request, api_client):
    """Test successful API request."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": ["test"]}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client._request("GET", "/test")
    
    assert result == {"data": ["test"]}
    mock_request.assert_called_once_with(
        "GET", 
        "https://cloud.lambda.ai/api/v1/test"
    )


@patch('requests.Session.request')
def test_request_http_error(mock_request, api_client):
    """Test API request with HTTP error."""
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = HTTPError("404 Not Found")
    mock_request.return_value = mock_response
    
    with pytest.raises(HTTPError):
        api_client._request("GET", "/nonexistent")


@patch('requests.Session.request')
def test_list_instances(mock_request, api_client):
    """Test listing instances."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [
            {"id": "inst1", "name": "test1"},
            {"id": "inst2", "name": "test2"}
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    instances = api_client.list_instances()
    
    assert len(instances) == 2
    assert instances[0]["id"] == "inst1"
    assert instances[1]["id"] == "inst2"


@patch('requests.Session.request')
def test_get_instance(mock_request, api_client):
    """Test getting specific instance."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {"id": "inst1", "name": "test1"}
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    instance = api_client.get_instance("inst1")
    
    assert instance["id"] == "inst1"
    mock_request.assert_called_once_with(
        "GET",
        "https://cloud.lambda.ai/api/v1/instances/inst1"
    )


@patch('requests.Session.request')
def test_launch_instance(mock_request, api_client):
    """Test launching an instance."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {"instance_ids": ["new-inst-123"]}
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.launch_instance(
        instance_type="gpu_1x_a10",
        region="us-south-1",
        ssh_key_names=["test-key"],
        filesystem_names=["test-fs"],
        name="test-instance"
    )
    
    assert result["instance_ids"] == ["new-inst-123"]
    
    # Verify the request payload
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert args[1] == "https://cloud.lambda.ai/api/v1/instance-operations/launch"
    
    expected_payload = {
        "instance_type_name": "gpu_1x_a10",
        "region_name": "us-south-1",
        "ssh_key_names": ["test-key"],
        "filesystem_names": ["test-fs"],
        "name": "test-instance"
    }
    assert kwargs["json"] == expected_payload


@patch('requests.Session.request')
def test_launch_instance_minimal(mock_request, api_client):
    """Test launching instance with minimal parameters."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": {"instance_ids": ["new-inst-123"]}}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.launch_instance(
        instance_type="gpu_1x_a10",
        region="us-south-1",
        ssh_key_names=["test-key"]
    )
    
    # Verify minimal payload doesn't include optional fields
    args, kwargs = mock_request.call_args
    payload = kwargs["json"]
    assert "filesystem_names" not in payload
    assert "name" not in payload


@patch('requests.Session.request')
def test_terminate_instance(mock_request, api_client):
    """Test terminating a single instance."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": {"terminated_instances": ["inst1"]}}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.terminate_instance("inst1")
    
    assert result["terminated_instances"] == ["inst1"]
    
    args, kwargs = mock_request.call_args
    assert kwargs["json"] == {"instance_ids": ["inst1"]}


@patch('requests.Session.request')
def test_terminate_all_instances_with_instances(mock_request, api_client):
    """Test terminating all instances when instances exist."""
    # Mock list_instances call
    def mock_request_side_effect(method, url, **kwargs):
        response = Mock()
        response.raise_for_status.return_value = None
        
        if "instances" in url and method == "GET":
            response.json.return_value = {
                "data": [{"id": "inst1"}, {"id": "inst2"}]
            }
        else:  # terminate call
            response.json.return_value = {
                "data": {"terminated_instances": ["inst1", "inst2"]}
            }
        
        return response
    
    mock_request.side_effect = mock_request_side_effect
    
    result = api_client.terminate_all_instances()
    
    assert result["terminated_instances"] == ["inst1", "inst2"]


@patch('requests.Session.request')
def test_terminate_all_instances_no_instances(mock_request, api_client):
    """Test terminating all instances when no instances exist."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": []}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.terminate_all_instances()
    
    assert result == {"terminated_instances": []}


@patch('requests.Session.request')
def test_list_instance_types(mock_request, api_client):
    """Test listing instance types."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {
            "gpu_1x_a10": {
                "instance_type": {
                    "name": "gpu_1x_a10",
                    "description": "1x A10 (24 GB PCIe)"
                },
                "regions_with_capacity_available": [
                    {"name": "us-south-1", "description": "Texas, USA"}
                ]
            }
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    instance_types = api_client.list_instance_types()
    
    assert len(instance_types) == 1
    assert instance_types[0]["name"] == "gpu_1x_a10"
    assert "regions_available" in instance_types[0]


@patch('requests.Session.request')
def test_list_regions(mock_request, api_client):
    """Test listing regions."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {
            "gpu_1x_a10": {
                "instance_type": {"name": "gpu_1x_a10"},
                "regions_with_capacity_available": [
                    {"name": "us-south-1", "description": "Texas, USA"},
                    {"name": "us-east-1", "description": "Virginia, USA"}
                ]
            },
            "gpu_1x_h100": {
                "instance_type": {"name": "gpu_1x_h100"},
                "regions_with_capacity_available": [
                    {"name": "us-south-1", "description": "Texas, USA"}
                ]
            }
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    regions = api_client.list_regions()
    
    # Should deduplicate regions
    region_names = [r["name"] for r in regions]
    assert "us-south-1" in region_names
    assert "us-east-1" in region_names
    assert len([r for r in regions if r["name"] == "us-south-1"]) == 1


@patch('requests.Session.request')
def test_add_ssh_key(mock_request, api_client):
    """Test adding SSH key."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {"id": "key123", "name": "test-key"}
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.add_ssh_key("test-key", "ssh-rsa AAAA...")
    
    assert result["id"] == "key123"
    
    args, kwargs = mock_request.call_args
    expected_payload = {
        "name": "test-key",
        "public_key": "ssh-rsa AAAA..."
    }
    assert kwargs["json"] == expected_payload


@patch('requests.Session.request')
def test_rotate_api_key(mock_request, api_client):
    """Test API key rotation."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {"api_key": "new-api-key-12345"}
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    result = api_client.rotate_api_key()
    
    assert result["api_key"] == "new-api-key-12345"
    
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert "/api-keys/rotate" in args[1]