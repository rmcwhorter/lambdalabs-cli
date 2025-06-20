"""Integration tests for end-to-end workflows."""
import pytest
import tempfile
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from lambdalabs_cli.config import Config
from lambdalabs_cli.api import LambdaLabsAPI
from lambdalabs_cli.scheduler import LambdaLabsScheduler


class TestWorkflowIntegration:
    """Test complete workflows end-to-end."""
    
    def test_mle_daily_workflow_setup(self, temp_config_dir):
        """Test setting up a complete MLE daily workflow."""
        # Initialize components
        config = Config()
        config.api_key = "test-api-key"
        config.default_filesystem = "mle-data"
        
        # Mock API responses
        with patch.object(LambdaLabsAPI, '_request') as mock_request:
            # Mock successful responses for all API calls
            def request_side_effect(method, endpoint, **kwargs):
                if "instances" in endpoint and method == "GET":
                    return {"data": []}  # No existing instances
                elif "ssh-keys" in endpoint:
                    return {"data": [{"name": "test-key"}]}
                elif "file-systems" in endpoint:
                    return {"data": [{"name": "mle-data", "region": {"name": "us-south-1"}}]}
                elif "instance-operations/launch" in endpoint:
                    return {"data": {"instance_ids": ["inst-new-123"]}}
                else:
                    return {"data": {}}
            
            mock_request.side_effect = request_side_effect
            
            api = LambdaLabsAPI(config)
            
            # Test idempotent instance creation
            instances_before = api.list_instances()
            assert len(instances_before) == 0
            
            # First call should create instance
            result1 = api.launch_instance(
                instance_type="gpu_1x_a10",
                region="us-south-1", 
                ssh_key_names=["test-key"],
                filesystem_names=["mle-data"],
                name="mle-workstation"
            )
            assert "inst-new-123" in result1["instance_ids"]
    
    def test_scheduling_integration(self, temp_config_dir):
        """Test complete scheduling workflow."""
        config = Config()
        config.api_key = "test-api-key"
        
        with patch('crontab.CronTab') as mock_crontab_class:
            mock_crontab = Mock()
            mock_job = Mock()
            mock_job.is_valid.return_value = True
            mock_crontab.new.return_value = mock_job
            mock_crontab.__iter__ = Mock(return_value = iter([]))
            mock_crontab_class.return_value = mock_crontab
            
            scheduler = LambdaLabsScheduler(config)
            
            # Add startup schedule
            startup_job = scheduler.add_recurring_schedule(
                action="create_instance",
                cron_schedule="0 9 * * 1-5",
                description="Daily MLE workstation",
                instance_type="gpu_1x_a10",
                region="us-south-1",
                name="mle-workstation",
                filesystem="mle-data"
            )
            
            # Add termination schedule  
            termination_job = scheduler.add_recurring_schedule(
                action="terminate_instance_by_name",
                cron_schedule="0 18 * * 1-5", 
                description="End of day shutdown",
                instance_name="mle-workstation"
            )
            
            # Verify jobs were created
            assert mock_crontab.new.call_count == 2
            assert mock_crontab.write.call_count == 2
            
            # Verify job commands are correct
            startup_call = mock_crontab.new.call_args_list[0]
            startup_command = startup_call[1]["command"]
            assert "instances ensure" in startup_command
            assert "--name mle-workstation" in startup_command
            assert "--filesystem mle-data" in startup_command
            
            termination_call = mock_crontab.new.call_args_list[1]
            termination_command = termination_call[1]["command"]
            assert "terminate-by-name mle-workstation" in termination_command

    def test_config_persistence(self, temp_config_dir):
        """Test that configuration persists across sessions."""
        # First session - set config
        config1 = Config()
        config1.api_key = "persistent-api-key"
        config1.ssh_dir = "/custom/ssh/path"
        config1.default_filesystem = "persistent-fs"
        
        # Second session - load config
        config2 = Config()
        
        assert config2.api_key == "persistent-api-key"
        assert config2.ssh_dir == "/custom/ssh/path"
        assert config2.default_filesystem == "persistent-fs"

    def test_ssh_key_auto_upload(self, temp_config_dir):
        """Test automatic SSH key upload when none exist."""
        config = Config()
        config.api_key = "test-api-key"
        config.ssh_dir = "/tmp/test-ssh"
        
        # Mock SSH key file
        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.read_text') as mock_read, \
             patch.object(LambdaLabsAPI, '_request') as mock_request:
            
            mock_exists.return_value = True
            mock_read.return_value = "ssh-rsa AAAAB3NzaC1yc2EAAA... test@example.com\n"
            
            # Mock API responses
            def request_side_effect(method, endpoint, **kwargs):
                if "ssh-keys" in endpoint and method == "GET":
                    return {"data": []}  # No existing keys
                elif "ssh-keys" in endpoint and method == "POST":
                    return {"data": {"id": "key-123", "name": "default"}}
                elif "instance-operations/launch" in endpoint:
                    return {"data": {"instance_ids": ["inst-456"]}}
                else:
                    return {"data": {}}
            
            mock_request.side_effect = request_side_effect
            
            api = LambdaLabsAPI(config)
            
            # This should trigger SSH key upload
            result = api.launch_instance(
                instance_type="gpu_1x_a10",
                region="us-south-1",
                ssh_key_names=[],  # Empty, should trigger auto-upload
                name="test-instance"
            )
            
            # Verify SSH key was uploaded
            ssh_key_calls = [call for call in mock_request.call_args_list 
                           if "ssh-keys" in call[0][1] and call[0][0] == "POST"]
            assert len(ssh_key_calls) == 1
            
            # Verify the payload
            payload = ssh_key_calls[0][1]["json"]
            assert payload["name"] == "default"
            assert "ssh-rsa AAAAB3NzaC1yc2EAAA..." in payload["public_key"]

    def test_filesystem_integration(self, temp_config_dir):
        """Test filesystem management integration."""
        config = Config()
        config.api_key = "test-api-key"
        
        with patch.object(LambdaLabsAPI, '_request') as mock_request:
            # Mock filesystem API responses
            filesystems_data = [
                {"id": "fs-1", "name": "project-a", "region": {"name": "us-south-1"}, "size": 100},
                {"id": "fs-2", "name": "project-b", "region": {"name": "us-east-1"}, "size": 500}
            ]
            
            mock_request.return_value = {"data": filesystems_data}
            
            api = LambdaLabsAPI(config)
            filesystems = api.list_filesystems()
            
            assert len(filesystems) == 2
            assert filesystems[0]["name"] == "project-a"
            assert filesystems[1]["name"] == "project-b"
            
            # Test setting default filesystem
            config.default_filesystem = "project-a"
            assert config.default_filesystem == "project-a"
            
            # Verify it persists
            config2 = Config()
            assert config2.default_filesystem == "project-a"

    def test_error_handling_integration(self, temp_config_dir):
        """Test error handling across components."""
        config = Config()
        config.api_key = "test-api-key"
        
        with patch.object(LambdaLabsAPI, '_request') as mock_request:
            # Mock API error
            from requests.exceptions import HTTPError
            mock_request.side_effect = HTTPError("400 Bad Request")
            
            api = LambdaLabsAPI(config)
            
            # Should raise the HTTP error
            with pytest.raises(HTTPError):
                api.list_instances()

    def test_cron_job_command_execution(self, temp_config_dir):
        """Test that generated cron job commands are valid."""
        config = Config()
        config.api_key = "test-api-key"
        
        with patch('crontab.CronTab') as mock_crontab_class:
            mock_crontab = Mock()
            mock_job = Mock()
            mock_job.is_valid.return_value = True
            mock_crontab.new.return_value = mock_job
            mock_crontab_class.return_value = mock_crontab
            
            scheduler = LambdaLabsScheduler(config)
            
            # Generate a startup command
            cmd = scheduler._create_job_command(
                "create_instance",
                instance_type="gpu_1x_a10", 
                region="us-south-1",
                name="test-workstation",
                filesystem="test-data"
            )
            
            # Verify command structure
            assert "python" in cmd or "python3" in cmd
            assert "lambdalabs_cli.cli" in cmd
            assert "instances ensure" in cmd
            assert "--type gpu_1x_a10" in cmd
            assert "--region us-south-1" in cmd
            assert "--name test-workstation" in cmd
            assert "--filesystem test-data" in cmd
            
            # Generate a termination command
            term_cmd = scheduler._create_job_command(
                "terminate_instance_by_name",
                instance_name="test-workstation"
            )
            
            assert "terminate-by-name test-workstation" in term_cmd

    def test_full_lifecycle_simulation(self, temp_config_dir):
        """Test a complete instance lifecycle simulation."""
        config = Config()
        config.api_key = "test-api-key"
        config.default_filesystem = "dev-data"
        
        # Track instance state
        instance_state = {"instances": []}
        
        def mock_api_request(method, endpoint, **kwargs):
            if "instances" in endpoint and method == "GET":
                return {"data": instance_state["instances"]}
            elif "instance-operations/launch" in endpoint:
                new_instance = {
                    "id": f"inst-{len(instance_state['instances']) + 1}",
                    "name": kwargs["json"]["name"],
                    "status": "running"
                }
                instance_state["instances"].append(new_instance)
                return {"data": {"instance_ids": [new_instance["id"]]}}
            elif "instance-operations/terminate" in endpoint:
                instance_ids = kwargs["json"]["instance_ids"]
                instance_state["instances"] = [
                    inst for inst in instance_state["instances"] 
                    if inst["id"] not in instance_ids
                ]
                return {"data": {"terminated_instances": instance_ids}}
            elif "ssh-keys" in endpoint:
                return {"data": [{"name": "test-key"}]}
            elif "file-systems" in endpoint:
                return {"data": [{"name": "dev-data"}]}
            else:
                return {"data": {}}
        
        with patch.object(LambdaLabsAPI, '_request', side_effect=mock_api_request):
            api = LambdaLabsAPI(config)
            
            # 1. Start with no instances
            instances = api.list_instances()
            assert len(instances) == 0
            
            # 2. Launch instance
            result = api.launch_instance(
                instance_type="gpu_1x_a10",
                region="us-south-1",
                ssh_key_names=["test-key"],
                filesystem_names=["dev-data"],
                name="lifecycle-test"
            )
            assert len(result["instance_ids"]) == 1
            
            # 3. Verify instance exists
            instances = api.list_instances()
            assert len(instances) == 1
            assert instances[0]["name"] == "lifecycle-test"
            
            # 4. Attempt to launch again (should still only have 1)
            # This simulates the "ensure" behavior
            existing_instances = [inst for inst in instances if inst["name"] == "lifecycle-test"]
            if not existing_instances:
                api.launch_instance(
                    instance_type="gpu_1x_a10",
                    region="us-south-1", 
                    ssh_key_names=["test-key"],
                    filesystem_names=["dev-data"],
                    name="lifecycle-test"
                )
            
            # Should still have only 1 instance
            instances = api.list_instances()
            assert len(instances) == 1
            
            # 5. Terminate instance
            instance_id = instances[0]["id"]
            result = api.terminate_instance(instance_id)
            assert instance_id in result["terminated_instances"]
            
            # 6. Verify no instances remain
            instances = api.list_instances()
            assert len(instances) == 0