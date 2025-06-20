"""Tests for CLI commands."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from lambdalabs_cli.cli import cli, instances, config, schedule


@pytest.fixture
def mock_context():
    """Create a mock CLI context."""
    context = Mock()
    context.obj = {
        'config': Mock(),
        'api': Mock(),
        'scheduler': Mock()
    }
    
    # Set up reasonable defaults
    context.obj['config'].api_key = "test-api-key"
    context.obj['config'].ssh_dir = "/tmp/.ssh"
    context.obj['config'].default_filesystem = "test-fs"
    
    return context


def test_cli_requires_api_key():
    """Test that CLI requires API key for non-config commands."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""  # No API key
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['instances', 'list'])
        
        assert result.exit_code == 1
        assert "No API key configured" in result.output


def test_cli_allows_config_commands_without_api_key():
    """Test that config commands work without API key."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = ""  # No API key
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'show'])
        
        assert result.exit_code == 0


def test_instances_list_empty():
    """Test listing instances when none exist."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = []
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['instances', 'list'])
        
        assert result.exit_code == 0
        assert "No instances found" in result.output


def test_instances_list_with_instances():
    """Test listing instances when they exist."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = [
            {
                "id": "inst-123",
                "name": "test-instance",
                "instance_type": {"name": "gpu_1x_a10"},
                "region": {"name": "us-south-1"},
                "status": "running",
                "ip": "192.168.1.100"
            }
        ]
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['instances', 'list'])
        
        assert result.exit_code == 0
        assert "inst-123" in result.output
        assert "test-instance" in result.output
        assert "gpu_1x_a10" in result.output


def test_instances_create():
    """Test creating an instance."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config.default_filesystem = "test-fs"
        mock_config.get_ssh_public_key.return_value = "ssh-rsa AAAA..."
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_ssh_keys.return_value = [{"name": "test-key"}]
        mock_api.list_filesystems.return_value = [{"name": "test-fs"}]
        mock_api.launch_instance.return_value = {"instance_ids": ["inst-new"]}
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, [
            'instances', 'create',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'test-instance'
        ])
        
        assert result.exit_code == 0
        assert "Instance launch initiated" in result.output
        mock_api.launch_instance.assert_called_once()


def test_instances_ensure_existing():
    """Test ensuring instance that already exists."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = [
            {"id": "inst-123", "name": "existing-instance"}
        ]
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, [
            'instances', 'ensure',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'existing-instance'
        ])
        
        assert result.exit_code == 0
        assert "already exists" in result.output
        mock_api.launch_instance.assert_not_called()


def test_instances_ensure_not_existing():
    """Test ensuring instance that doesn't exist."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config.default_filesystem = "test-fs"
        mock_config.get_ssh_public_key.return_value = "ssh-rsa AAAA..."
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = []  # No existing instances
        mock_api.list_ssh_keys.return_value = [{"name": "test-key"}]
        mock_api.list_filesystems.return_value = [{"name": "test-fs"}]
        mock_api.launch_instance.return_value = {"instance_ids": ["inst-new"]}
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, [
            'instances', 'ensure',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'new-instance'
        ])
        
        assert result.exit_code == 0
        assert "not found, creating" in result.output
        mock_api.launch_instance.assert_called_once()


def test_instances_terminate():
    """Test terminating an instance."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.terminate_instance.return_value = {"success": True}
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['instances', 'terminate', 'inst-123'])
        
        assert result.exit_code == 0
        assert "termination initiated" in result.output
        mock_api.terminate_instance.assert_called_once_with('inst-123')


def test_instances_terminate_by_name_found():
    """Test terminating instance by name when found."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = [
            {"id": "inst-123", "name": "target-instance"}
        ]
        mock_api.terminate_instance.return_value = {"success": True}
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['instances', 'terminate-by-name', 'target-instance'])
        
        assert result.exit_code == 0
        assert "termination initiated" in result.output
        mock_api.terminate_instance.assert_called_once_with('inst-123')


def test_instances_terminate_by_name_not_found():
    """Test terminating instance by name when not found."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instances.return_value = []  # No instances
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['instances', 'terminate-by-name', 'nonexistent'])
        
        assert result.exit_code == 0
        assert "No instance found" in result.output
        mock_api.terminate_instance.assert_not_called()


def test_config_set_api_key():
    """Test setting API key."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'set-api-key', 'new-test-key'])
        
        assert result.exit_code == 0
        assert "API key updated successfully" in result.output
        assert mock_config.api_key == 'new-test-key'


def test_config_show_default():
    """Test showing config with redacted API key."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = "secret_test_12345678901234567890"
        mock_config.ssh_dir = "/tmp/.ssh"
        mock_config.default_filesystem = "test-fs"
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'show'])
        
        assert result.exit_code == 0
        assert "secret_t...67890" in result.output  # Redacted
        assert "/tmp/.ssh" in result.output
        assert "test-fs" in result.output


def test_config_show_full():
    """Test showing config with full API key."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = "secret_test_key"
        mock_config.ssh_dir = "/tmp/.ssh"
        mock_config.default_filesystem = "test-fs"
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'show', '--full'])
        
        assert result.exit_code == 0
        assert "secret_test_key" in result.output  # Full key
        assert "/tmp/.ssh" in result.output


def test_config_get_api_key():
    """Test getting API key for scripting."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class:
        mock_config = Mock()
        mock_config.api_key = "test-api-key-123"
        mock_config_class.return_value = mock_config
        
        result = runner.invoke(cli, ['config', 'get-api-key'])
        
        assert result.exit_code == 0
        assert result.output.strip() == "test-api-key-123"


def test_schedule_add_startup():
    """Test adding startup schedule."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler.add_recurring_schedule.return_value = "job-created"
        mock_scheduler_class.return_value = mock_scheduler
        
        result = runner.invoke(cli, [
            'schedule', 'add-startup',
            '--type', 'gpu_1x_a10',
            '--region', 'us-south-1',
            '--name', 'test-instance',
            '--cron', '0 9 * * 1-5',
            '--description', 'Test startup'
        ])
        
        assert result.exit_code == 0
        assert "Scheduled idempotent instance startup" in result.output
        mock_scheduler.add_recurring_schedule.assert_called_once()


def test_schedule_add_termination_duration():
    """Test adding termination schedule with duration."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler.add_time_based_termination.return_value = "job-created"
        mock_scheduler_class.return_value = mock_scheduler
        
        result = runner.invoke(cli, [
            'schedule', 'add-termination',
            '--in', '30',
            '--description', 'Test termination'
        ])
        
        assert result.exit_code == 0
        assert "in 30 minutes" in result.output
        mock_scheduler.add_time_based_termination.assert_called_once()


def test_schedule_list_empty():
    """Test listing schedules when none exist."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler.list_jobs.return_value = []
        mock_scheduler_class.return_value = mock_scheduler
        
        result = runner.invoke(cli, ['schedule', 'list'])
        
        assert result.exit_code == 0
        assert "No scheduled jobs found" in result.output


def test_schedule_remove():
    """Test removing a scheduled job."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsScheduler') as mock_scheduler_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_scheduler = Mock()
        mock_scheduler.remove_job.return_value = True
        mock_scheduler_class.return_value = mock_scheduler
        
        result = runner.invoke(cli, ['schedule', 'remove', '0'])
        
        assert result.exit_code == 0
        assert "Removed scheduled job 0" in result.output
        mock_scheduler.remove_job.assert_called_once_with('0')


def test_info_command():
    """Test info command."""
    runner = CliRunner()
    
    with patch('lambdalabs_cli.cli.Config') as mock_config_class, \
         patch('lambdalabs_cli.cli.LambdaLabsAPI') as mock_api_class:
        
        mock_config = Mock()
        mock_config.api_key = "test-key"
        mock_config_class.return_value = mock_config
        
        mock_api = Mock()
        mock_api.list_instance_types.return_value = [
            {"name": "gpu_1x_a10", "description": "1x A10 (24 GB PCIe)"}
        ]
        mock_api.list_regions.return_value = [
            {"name": "us-south-1", "description": "Texas, USA"}
        ]
        mock_api_class.return_value = mock_api
        
        result = runner.invoke(cli, ['info'])
        
        assert result.exit_code == 0
        assert "Available Instance Types" in result.output
        assert "gpu_1x_a10" in result.output
        assert "Available Regions" in result.output
        assert "us-south-1" in result.output