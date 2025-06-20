"""All tests for Lambda Labs CLI."""
import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner
import requests

from lambdalabs_cli.api import LambdaLabsAPI
from lambdalabs_cli.scheduler import LambdaLabsScheduler
from lambdalabs_cli.cli import cli


# API Tests
def test_api_client_basic():
    mock_config = Mock()
    mock_config.api_key = "test-api-key"
    
    api = LambdaLabsAPI(mock_config)
    
    assert api.config == mock_config
    assert api.base_url == "https://cloud.lambda.ai/api/v1"
    assert "Bearer test-api-key" in api.session.headers["Authorization"]


@patch('requests.Session.request')
def test_api_list_instances(mock_request):
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
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


@patch('requests.Session.request')
def test_api_launch_instance(mock_request):
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    mock_response = Mock()
    mock_response.json.return_value = {"data": {"instance_ids": ["new-inst-123"]}}
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
    
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert "instance-operations/launch" in args[1]
    
    payload = kwargs["json"]
    assert payload["instance_type_name"] == "gpu_1x_a10"
    assert payload["region_name"] == "us-south-1"
    assert payload["ssh_key_names"] == ["test-key"]
    assert payload["name"] == "test-instance"


@patch('requests.Session.request')
def test_api_terminate_all_logic(mock_request):
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
    def request_side_effect(method, url, **kwargs):
        response = Mock()
        response.raise_for_status.return_value = None
        
        if "instances" in url and method == "GET":
            response.json.return_value = {
                "data": [
                    {"id": "inst1", "name": "test1"},
                    {"id": "inst2", "name": "test2"}
                ]
            }
        else:
            response.json.return_value = {
                "data": {"terminated_instances": ["inst1", "inst2"]}
            }
        
        return response
    
    mock_request.side_effect = request_side_effect
    
    api = LambdaLabsAPI(mock_config)
    result = api.terminate_all_instances()
    
    assert "terminated_instances" in result
    assert len(result["terminated_instances"]) == 2


@patch('requests.Session.request')
def test_api_instance_types_parsing(mock_request):
    mock_config = Mock()
    mock_config.api_key = "test-key"
    
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
            }
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response
    
    api = LambdaLabsAPI(mock_config)
    instance_types = api.list_instance_types()
    
    assert len(instance_types) == 1
    a10 = instance_types[0]
    assert a10["name"] == "gpu_1x_a10"
    assert a10["description"] == "1x A10 (24 GB PCIe)"
    assert "regions_available" in a10


# Scheduler Tests
def test_scheduler_command_generation():
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        # Test terminate instance command
        cmd = scheduler._create_job_command("terminate_instance", instance_id="inst-123")
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
        assert "--yes" in cmd
        assert "terminate-all" in cmd


def test_scheduler_validation():
    mock_config = Mock()
    
    with patch('crontab.CronTab'):
        scheduler = LambdaLabsScheduler(mock_config)
        
        # Should require name for create_instance
        with pytest.raises(ValueError, match="Instance name is required"):
            scheduler._create_job_command("create_instance", instance_type="gpu_1x_a10", region="us-south-1")
        
        # Should reject unknown actions
        with pytest.raises(ValueError, match="Unknown action"):
            scheduler._create_job_command("invalid_action")


# CLI Tests
def test_ensure_command_idempotent():
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config.default_filesystem = "test-fs"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        
        # Test 1: Instance doesn't exist - should create
        mock_api.list_instances.return_value = []
        mock_api.list_ssh_keys.return_value = [{"name": "test-key"}]
        mock_api.list_filesystems.return_value = [{"name": "test-fs"}]
        mock_api.launch_instance.return_value = {"instance_ids": ["new-inst"]}
        
        result = runner.invoke(cli, [
            'instances', 'ensure',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1', 
            '--name', 'test-workstation'
        ])
        
        assert result.exit_code == 0
        assert "not found, creating" in result.output
        mock_api.launch_instance.assert_called_once()
        
        # Test 2: Instance exists - should not create
        mock_api.reset_mock()
        mock_api.list_instances.return_value = [{"id": "existing-123", "name": "test-workstation"}]
        
        result = runner.invoke(cli, [
            'instances', 'ensure', 
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'test-workstation'
        ])
        
        assert result.exit_code == 0
        assert "already exists" in result.output
        mock_api.launch_instance.assert_not_called()


def test_terminate_by_name():
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        
        mock_api.list_instances.return_value = [
            {"id": "inst-123", "name": "target-instance"},
            {"id": "inst-456", "name": "other-instance"}
        ]
        mock_api.terminate_instance.return_value = {"success": True}
        
        result = runner.invoke(cli, ['instances', 'terminate-by-name', 'target-instance'])
        
        assert result.exit_code == 0
        assert "termination initiated" in result.output
        mock_api.terminate_instance.assert_called_once_with('inst-123')


def test_config_api_key():
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        # Test setting API key
        result = runner.invoke(cli, ['config', 'set-api-key', 'new-test-key'])
        
        assert result.exit_code == 0
        assert "API key updated successfully" in result.output
        assert mock_config.api_key == 'new-test-key'
        
        # Test showing redacted API key
        mock_config.api_key = "secret_test_very_long_api_key_12345678"
        mock_config.ssh_dir = "/tmp/.ssh"
        mock_config.default_filesystem = "test-fs"
        
        result = runner.invoke(cli, ['config', 'show'])
        
        assert result.exit_code == 0
        assert "secret_t...12345678" in result.output
        
        # Test showing full API key
        result = runner.invoke(cli, ['config', 'show', '--full'])
        
        assert result.exit_code == 0
        assert "secret_test_very_long_api_key_12345678" in result.output


def test_scheduling_workflow():
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Test adding startup schedule
        result = runner.invoke(cli, [
            'schedule', 'add-startup',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'mle-workstation',
            '--filesystem', 'mle-data',
            '--cron', '0 9 * * 1-5',
            '--description', 'Daily MLE workstation'
        ])
        
        assert result.exit_code == 0
        assert "Scheduled idempotent instance startup" in result.output
        assert "will be created if it doesn't exist" in result.output
        
        mock_scheduler.add_recurring_schedule.assert_called_once()
        call_args = mock_scheduler.add_recurring_schedule.call_args
        
        assert call_args[1]["action"] == "create_instance"
        assert call_args[1]["cron_schedule"] == "0 9 * * 1-5"
        assert call_args[1]["instance_type"] == "gpu_1x_a10"
        assert call_args[1]["name"] == "mle-workstation"


def test_mle_workflow():
    """Test the complete MLE workflow."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Morning startup (idempotent)
        result1 = runner.invoke(cli, [
            'schedule', 'add-startup',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'dev-workstation',
            '--filesystem', 'project-data',
            '--cron', '0 9 * * 1-5'
        ])
        
        assert result1.exit_code == 0
        assert "idempotent" in result1.output
        
        # Evening termination (by name)
        result2 = runner.invoke(cli, [
            'schedule', 'add-recurring-termination',
            '--instance-name', 'dev-workstation',
            '--cron', '0 18 * * 1-5'
        ])
        
        assert result2.exit_code == 0
        
        assert mock_scheduler.add_recurring_schedule.call_count == 2
        
        startup_call = mock_scheduler.add_recurring_schedule.call_args_list[0]
        termination_call = mock_scheduler.add_recurring_schedule.call_args_list[1]
        
        # Verify startup uses create_instance (ensure)
        assert startup_call[1]["action"] == "create_instance"
        assert startup_call[1]["name"] == "dev-workstation"
        
        # Verify termination uses terminate by name
        assert termination_call[1]["action"] == "terminate_instance_by_name"
        assert termination_call[1]["instance_name"] == "dev-workstation"


def test_error_handling():
    runner = CliRunner()
    
    # Missing API key for non-config commands
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['instances', 'list'])
        
        assert result.exit_code == 1
        assert "No API key configured" in result.output
    
    # Config commands should work without API key
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""
        mock_config.ssh_dir = "/tmp/.ssh"
        mock_config.default_filesystem = None
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'show'])
        
        assert result.exit_code == 0
        assert "Not set" in result.output


def test_idempotent_behavior():
    """Test core idempotent behavior logic."""
    existing_instances = [
        {"id": "inst-123", "name": "mle-workstation", "status": "running"}
    ]
    
    def should_create_instance(desired_name, existing_instances):
        existing = [inst for inst in existing_instances if inst.get("name") == desired_name]
        return len(existing) == 0
    
    # Instance doesn't exist - should create
    assert should_create_instance("new-workstation", existing_instances) is True
    
    # Instance exists - should not create  
    assert should_create_instance("mle-workstation", existing_instances) is False
    
    # Empty instance list - should create
    assert should_create_instance("any-workstation", []) is True