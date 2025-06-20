"""Tests that verify the core system functionality works as expected."""
import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner

from lambdalabs_cli.cli import cli


def test_ensure_command_idempotent_behavior():
    """Test that ensure command behaves idempotently."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        # Setup mocks
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config.default_filesystem = "test-fs"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        
        # Test 1: Instance doesn't exist - should attempt to create
        mock_api.list_instances.return_value = []  # No existing instances
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
        
        # Reset mocks for test 2
        mock_api.reset_mock()
        
        # Test 2: Instance exists - should not create
        mock_api.list_instances.return_value = [
            {"id": "existing-123", "name": "test-workstation"}
        ]
        
        result = runner.invoke(cli, [
            'instances', 'ensure', 
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'test-workstation'
        ])
        
        assert result.exit_code == 0
        assert "already exists" in result.output
        mock_api.launch_instance.assert_not_called()


def test_terminate_by_name_functionality():
    """Test terminating instances by name."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        
        # Test successful termination
        mock_api.list_instances.return_value = [
            {"id": "inst-123", "name": "target-instance"},
            {"id": "inst-456", "name": "other-instance"}
        ]
        mock_api.terminate_instance.return_value = {"success": True}
        
        result = runner.invoke(cli, ['instances', 'terminate-by-name', 'target-instance'])
        
        assert result.exit_code == 0
        assert "termination initiated" in result.output
        mock_api.terminate_instance.assert_called_once_with('inst-123')


def test_scheduling_workflow():
    """Test the complete scheduling workflow."""
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
        
        # Verify the scheduler was called correctly
        mock_scheduler.add_recurring_schedule.assert_called_once()
        call_args = mock_scheduler.add_recurring_schedule.call_args
        
        assert call_args[1]["action"] == "create_instance"
        assert call_args[1]["cron_schedule"] == "0 9 * * 1-5"
        assert call_args[1]["instance_type"] == "gpu_1x_a10"
        assert call_args[1]["region"] == "us-south-1"
        assert call_args[1]["name"] == "mle-workstation"
        assert call_args[1]["filesystem"] == "mle-data"


def test_config_api_key_handling():
    """Test API key configuration and display."""
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
        # Should show first 8 and last 8 characters  
        assert "secret_t...12345678" in result.output
        
        # Test showing full API key
        result = runner.invoke(cli, ['config', 'show', '--full'])
        
        assert result.exit_code == 0
        assert "secret_test_very_long_api_key_12345678" in result.output


def test_mle_workflow_integration():
    """Test the complete MLE workflow integration."""
    # This tests the key MLE use case: 
    # 1. Schedule instance to start every morning (idempotent)
    # 2. Schedule instance to stop every evening (by name)
    
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Step 1: Add morning startup (idempotent)
        result1 = runner.invoke(cli, [
            'schedule', 'add-startup',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'dev-workstation',
            '--filesystem', 'project-data',
            '--cron', '0 9 * * 1-5',
            '--description', 'Morning dev workstation'
        ])
        
        assert result1.exit_code == 0
        assert "idempotent" in result1.output
        
        # Step 2: Add evening termination (by name)
        result2 = runner.invoke(cli, [
            'schedule', 'add-recurring-termination',
            '--instance-name', 'dev-workstation',
            '--cron', '0 18 * * 1-5',
            '--description', 'Evening shutdown'
        ])
        
        assert result2.exit_code == 0
        assert "dev-workstation" in result2.output
        
        # Verify both calls were made correctly
        assert mock_scheduler.add_recurring_schedule.call_count == 2
        
        startup_call = mock_scheduler.add_recurring_schedule.call_args_list[0]
        termination_call = mock_scheduler.add_recurring_schedule.call_args_list[1]
        
        # Verify startup call uses create_instance (ensure)
        assert startup_call[1]["action"] == "create_instance"
        assert startup_call[1]["name"] == "dev-workstation"
        
        # Verify termination call uses terminate by name
        assert termination_call[1]["action"] == "terminate_instance_by_name"
        assert termination_call[1]["instance_name"] == "dev-workstation"


def test_error_cases():
    """Test error handling for common cases."""
    runner = CliRunner()
    
    # Test 1: Missing API key for non-config commands
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""  # No API key
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['instances', 'list'])
        
        assert result.exit_code == 1
        assert "No API key configured" in result.output
    
    # Test 2: Config commands should work without API key
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""  # No API key
        mock_config.ssh_dir = "/tmp/.ssh"
        mock_config.default_filesystem = None
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'show'])
        
        assert result.exit_code == 0
        assert "Not set" in result.output


def test_filesystem_default_behavior():
    """Test default filesystem behavior."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config.default_filesystem = "auto-fs"
        mock_config.get_ssh_public_key.return_value = "ssh-rsa AAAA..."
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = []  # No existing instances
        mock_api.list_ssh_keys.return_value = [{"name": "test-key"}]
        mock_api.list_filesystems.return_value = [
            {"name": "auto-fs", "id": "fs-123"}
        ]
        mock_api.launch_instance.return_value = {"instance_ids": ["new-inst"]}
        mock_api_class.return_value = mock_api
        
        # Create instance without specifying filesystem
        result = runner.invoke(cli, [
            'instances', 'ensure',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'test-instance'
            # No --filesystem specified
        ])
        
        assert result.exit_code == 0
        assert "Using default filesystem: auto-fs" in result.output
        
        # Verify the API was called with the default filesystem
        mock_api.launch_instance.assert_called_once()
        call_args = mock_api.launch_instance.call_args[1]
        assert call_args["filesystem_names"] == ["auto-fs"]