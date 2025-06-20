"""Simple focused tests to verify core functionality."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json
from pathlib import Path

from lambdalabs_cli.api import LambdaLabsAPI
from lambdalabs_cli.scheduler import LambdaLabsScheduler


def test_api_client_basic():
    """Test basic API client functionality."""
    mock_config = Mock()
    mock_config.api_key = "test-api-key"
    
    api = LambdaLabsAPI(mock_config)
    
    assert api.config == mock_config
    assert api.base_url == "https://cloud.lambda.ai/api/v1"
    assert "Bearer test-api-key" in api.session.headers["Authorization"]


@patch('requests.Session.request')
def test_api_list_instances(mock_request):
    """Test listing instances."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    # Mock successful response
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [
            {"id": "inst1", "name": "test1", "status": "running"},
            {"id": "inst2", "name": "test2", "status": "stopped"}
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    api = LambdaLabsAPI(mock_config)
    instances = api.list_instances()
    
    assert len(instances) == 2
    assert instances[0]["id"] == "inst1"
    assert instances[1]["name"] == "test2"
    mock_request.assert_called_once()


@patch('requests.Session.request')
def test_api_launch_instance(mock_request):
    """Test launching an instance."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {"instance_ids": ["new-inst-123"]}
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    api = LambdaLabsAPI(mock_config)
    result = api.launch_instance(
        instance_type="gpu_1x_a10",
        region="us-south-1",
        ssh_key_names=["test-key"],
        name="test-instance"
    )
    
    assert result["instance_ids"] == ["new-inst-123"]
    
    # Verify the request was made correctly
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert "instance-operations/launch" in args[1]
    
    payload = kwargs["json"]
    assert payload["instance_type_name"] == "gpu_1x_a10"
    assert payload["region_name"] == "us-south-1"
    assert payload["ssh_key_names"] == ["test-key"]
    assert payload["name"] == "test-instance"


def test_scheduler_command_generation():
    """Test scheduler command generation."""
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        # Test terminate instance command
        cmd = scheduler._create_job_command(
            "terminate_instance", 
            instance_id="inst-123"
        )
        assert "instances terminate inst-123" in cmd
        assert "lambdalabs_cli.cli" in cmd
        
        # Test create instance command (ensure)
        cmd = scheduler._create_job_command(
            "create_instance",
            instance_type="gpu_1x_a10",
            region="us-south-1", 
            name="test-workstation",
            filesystem="test-fs"
        )
        assert "instances ensure" in cmd
        assert "--type gpu_1x_a10" in cmd
        assert "--region us-south-1" in cmd
        assert "--name test-workstation" in cmd
        assert "--filesystem test-fs" in cmd
        
        # Test terminate all command
        cmd = scheduler._create_job_command("terminate_all")
        assert "yes |" in cmd
        assert "terminate-all" in cmd


def test_scheduler_command_validation():
    """Test scheduler command validation."""
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        # Should require name for create_instance
        with pytest.raises(ValueError, match="Instance name is required"):
            scheduler._create_job_command(
                "create_instance",
                instance_type="gpu_1x_a10",
                region="us-south-1"
                # Missing name parameter
            )
        
        # Should reject unknown actions
        with pytest.raises(ValueError, match="Unknown action"):
            scheduler._create_job_command("invalid_action")


def test_api_instance_types_parsing():
    """Test instance types API response parsing."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    with patch('requests.Session.request') as mock_request:
        # Mock the complex instance types response
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "gpu_1x_a10": {
                    "instance_type": {
                        "name": "gpu_1x_a10",
                        "description": "1x A10 (24 GB PCIe)",
                        "price_cents_per_hour": 100
                    },
                    "regions_with_capacity_available": [
                        {"name": "us-south-1", "description": "Texas, USA"}
                    ]
                },
                "gpu_1x_h100": {
                    "instance_type": {
                        "name": "gpu_1x_h100", 
                        "description": "1x H100 (80 GB SXM5)",
                        "price_cents_per_hour": 500
                    },
                    "regions_with_capacity_available": [
                        {"name": "us-east-1", "description": "Virginia, USA"}
                    ]
                }
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        api = LambdaLabsAPI(mock_config)
        instance_types = api.list_instance_types()
        
        assert len(instance_types) == 2
        
        # Check first instance type
        a10 = next(t for t in instance_types if t["name"] == "gpu_1x_a10")
        assert a10["description"] == "1x A10 (24 GB PCIe)"
        assert a10["price_cents_per_hour"] == 100
        assert "regions_available" in a10
        assert len(a10["regions_available"]) == 1
        assert a10["regions_available"][0]["name"] == "us-south-1"


def test_api_regions_deduplication():
    """Test that regions are properly deduplicated."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    with patch('requests.Session.request') as mock_request:
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
                        {"name": "us-south-1", "description": "Texas, USA"},  # Duplicate
                        {"name": "us-west-1", "description": "California, USA"}
                    ]
                }
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        api = LambdaLabsAPI(mock_config)
        regions = api.list_regions()
        
        # Should have 3 unique regions, not 4
        assert len(regions) == 3
        
        region_names = [r["name"] for r in regions]
        assert "us-south-1" in region_names
        assert "us-east-1" in region_names  
        assert "us-west-1" in region_names
        
        # Verify no duplicates
        assert len(region_names) == len(set(region_names))


def test_api_terminate_all_logic():
    """Test terminate all instances logic."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    with patch('requests.Session.request') as mock_request:
        # Mock sequence: list instances, then terminate
        def request_side_effect(method, url, **kwargs):
            response = Mock()
            response.raise_for_status.return_value = None
            
            if "instances" in url and method == "GET":
                # Return some instances to terminate
                response.json.return_value = {
                    "data": [
                        {"id": "inst1", "name": "test1"},
                        {"id": "inst2", "name": "test2"}
                    ]
                }
            else:  # terminate call
                response.json.return_value = {
                    "data": {"terminated_instances": ["inst1", "inst2"]}
                }
            
            return response
        
        mock_request.side_effect = request_side_effect
        
        api = LambdaLabsAPI(mock_config)
        result = api.terminate_all_instances()
        
        assert "terminated_instances" in result
        assert len(result["terminated_instances"]) == 2
        assert "inst1" in result["terminated_instances"]
        assert "inst2" in result["terminated_instances"]


def test_api_terminate_all_no_instances():
    """Test terminate all when no instances exist."""
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}  # No instances
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        api = LambdaLabsAPI(mock_config)
        result = api.terminate_all_instances()
        
        # Should return empty list, not make terminate call
        assert result == {"terminated_instances": []}
        
        # Should only have made one call (list instances)
        assert mock_request.call_count == 1


def test_scheduler_job_comment_generation():
    """Test job comment generation."""
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        comment = scheduler._create_job_comment("terminate_instance", "Test job")
        assert comment == "lambdalabs-cli: terminate_instance - Test job"
        
        comment = scheduler._create_job_comment("create_instance", "")
        assert comment == "lambdalabs-cli: create_instance - "


def test_idempotent_behavior_simulation():
    """Test the core idempotent behavior that MLEs need."""
    # This simulates the 'ensure' behavior without complex mocking
    
    # Simulate existing instances
    existing_instances = [
        {"id": "inst-123", "name": "mle-workstation", "status": "running"}
    ]
    
    def should_create_instance(desired_name, existing_instances):
        """Logic from the ensure command."""
        existing = [inst for inst in existing_instances if inst.get("name") == desired_name]
        return len(existing) == 0
    
    # Test 1: Instance doesn't exist - should create
    assert should_create_instance("new-workstation", existing_instances) is True
    
    # Test 2: Instance exists - should not create  
    assert should_create_instance("mle-workstation", existing_instances) is False
    
    # Test 3: Multiple instances exist but different names - should create
    assert should_create_instance("different-workstation", existing_instances) is True
    
    # Test 4: Empty instance list - should create
    assert should_create_instance("any-workstation", []) is True


def test_mle_workflow_commands():
    """Test that generated commands match MLE workflow expectations."""
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        # Morning startup command (should use 'ensure')
        startup_cmd = scheduler._create_job_command(
            "create_instance",
            instance_type="gpu_1x_a10",
            region="us-south-1",
            name="mle-workstation",
            filesystem="mle-data"
        )
        
        # Verify it uses 'ensure' not 'create'
        assert "instances ensure" in startup_cmd
        assert "instances create" not in startup_cmd
        assert "--name mle-workstation" in startup_cmd
        assert "--filesystem mle-data" in startup_cmd
        
        # Evening termination command
        termination_cmd = scheduler._create_job_command(
            "terminate_instance_by_name",
            instance_name="mle-workstation"
        )
        
        assert "terminate-by-name mle-workstation" in termination_cmd