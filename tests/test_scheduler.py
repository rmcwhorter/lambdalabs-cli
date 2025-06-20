"""Tests for scheduling functionality."""
import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from lambdalabs_cli.scheduler import LambdaLabsScheduler
from lambdalabs_cli.config import Config


@pytest.fixture
def scheduler(mock_config):
    """Create scheduler with mock config."""
    with patch('crontab.CronTab') as mock_crontab:
        scheduler = LambdaLabsScheduler(mock_config)
        scheduler.cron = mock_crontab.return_value
        return scheduler


def test_scheduler_initialization(mock_config):
    """Test scheduler initialization."""
    with patch('crontab.CronTab') as mock_crontab:
        scheduler = LambdaLabsScheduler(mock_config)
        
        assert scheduler.config == mock_config
        assert scheduler.comment_prefix == "lambdalabs-cli"
        mock_crontab.assert_called_once_with(user=True)


def test_create_job_command_terminate_instance(scheduler):
    """Test command generation for instance termination."""
    cmd = scheduler._create_job_command(
        "terminate_instance", 
        instance_id="inst-123"
    )
    
    assert "instances terminate inst-123" in cmd
    assert "lambdalabs_cli.cli" in cmd


def test_create_job_command_terminate_all(scheduler):
    """Test command generation for terminate all."""
    cmd = scheduler._create_job_command("terminate_all")
    
    assert "yes |" in cmd
    assert "instances terminate-all" in cmd


def test_create_job_command_create_instance(scheduler):
    """Test command generation for instance creation."""
    cmd = scheduler._create_job_command(
        "create_instance",
        instance_type="gpu_1x_a10",
        region="us-south-1",
        name="test-instance",
        filesystem="test-fs"
    )
    
    assert "instances ensure" in cmd
    assert "--type gpu_1x_a10" in cmd
    assert "--region us-south-1" in cmd
    assert "--name test-instance" in cmd
    assert "--filesystem test-fs" in cmd


def test_create_job_command_create_instance_no_name(scheduler):
    """Test command generation fails without instance name."""
    with pytest.raises(ValueError, match="Instance name is required"):
        scheduler._create_job_command(
            "create_instance",
            instance_type="gpu_1x_a10",
            region="us-south-1"
        )


def test_create_job_command_invalid_action(scheduler):
    """Test command generation with invalid action."""
    with pytest.raises(ValueError, match="Unknown action"):
        scheduler._create_job_command("invalid_action")


def test_add_scheduled_job(scheduler):
    """Test adding a scheduled job."""
    mock_job = Mock()
    mock_job.is_valid.return_value = True
    scheduler.cron.new.return_value = mock_job
    
    result = scheduler.add_scheduled_job(
        "terminate_instance",
        "0 18 * * *",
        "Test termination",
        instance_id="inst-123"
    )
    
    scheduler.cron.new.assert_called_once()
    mock_job.setall.assert_called_once_with("0 18 * * *")
    mock_job.is_valid.assert_called_once()
    scheduler.cron.write.assert_called_once()


def test_add_scheduled_job_invalid_schedule(scheduler):
    """Test adding job with invalid cron schedule."""
    mock_job = Mock()
    mock_job.is_valid.return_value = False
    scheduler.cron.new.return_value = mock_job
    
    with pytest.raises(ValueError, match="Invalid cron schedule"):
        scheduler.add_scheduled_job(
            "terminate_instance",
            "invalid schedule",
            "Test",
            instance_id="inst-123"
        )


def test_add_time_based_termination_duration(scheduler):
    """Test adding time-based termination with duration."""
    mock_job = Mock()
    mock_job.is_valid.return_value = True
    scheduler.cron.new.return_value = mock_job
    
    with patch('lambdalabs_cli.scheduler.datetime') as mock_dt:
        now = datetime(2024, 6, 20, 14, 30, 0)
        target = now + timedelta(minutes=30)
        mock_dt.now.return_value = now
        
        scheduler.add_time_based_termination(
            instance_id="inst-123",
            duration_minutes=30,
            description="Test termination"
        )
        
        # Verify the schedule was set correctly
        expected_schedule = f"{target.minute} {target.hour} {target.day} {target.month} *"
        mock_job.setall.assert_called_once_with(expected_schedule)


def test_add_time_based_termination_end_time_today(scheduler):
    """Test adding time-based termination with end time today."""
    mock_job = Mock()
    mock_job.is_valid.return_value = True
    scheduler.cron.new.return_value = mock_job
    
    with patch('lambdalabs_cli.scheduler.datetime') as mock_dt:
        now = datetime(2024, 6, 20, 14, 30, 0)
        mock_dt.now.return_value = now
        mock_dt.strptime.return_value = datetime(1900, 1, 1, 18, 0, 0)
        
        scheduler.add_time_based_termination(
            instance_id=None,
            end_time="18:00",
            description="End of day"
        )
        
        # Should schedule for 18:00 today
        expected_schedule = "0 18 20 6 *"  # June 20, 2024 at 18:00
        mock_job.setall.assert_called_once_with(expected_schedule)


def test_add_time_based_termination_end_time_tomorrow(scheduler):
    """Test adding time-based termination with end time tomorrow."""
    mock_job = Mock()
    mock_job.is_valid.return_value = True
    scheduler.cron.new.return_value = mock_job
    
    with patch('lambdalabs_cli.scheduler.datetime') as mock_dt:
        now = datetime(2024, 6, 20, 20, 30, 0)  # 8:30 PM
        mock_dt.now.return_value = now
        mock_dt.strptime.return_value = datetime(1900, 1, 1, 18, 0, 0)  # 6:00 PM
        
        scheduler.add_time_based_termination(
            instance_id=None,
            end_time="18:00",
            description="End of day"
        )
        
        # Should schedule for 18:00 tomorrow (June 21)
        expected_schedule = "0 18 21 6 *"
        mock_job.setall.assert_called_once_with(expected_schedule)


def test_add_time_based_termination_invalid_time(scheduler):
    """Test adding time-based termination with invalid time format."""
    with pytest.raises(ValueError, match="Time must be in HH:MM format"):
        scheduler.add_time_based_termination(
            instance_id="inst-123",
            end_time="invalid-time"
        )


def test_add_time_based_termination_no_params(scheduler):
    """Test adding time-based termination without duration or end time."""
    with pytest.raises(ValueError, match="Must specify either duration_minutes or end_time"):
        scheduler.add_time_based_termination(instance_id="inst-123")


def test_list_jobs(scheduler):
    """Test listing scheduled jobs."""
    # Mock cron jobs
    mock_job1 = Mock()
    mock_job1.comment = "lambdalabs-cli: terminate_instance - Test 1"
    mock_job1.slices = "0 18 * * *"
    mock_job1.command = "test command 1"
    mock_job1.is_enabled.return_value = True
    
    mock_job2 = Mock()
    mock_job2.comment = "lambdalabs-cli: create_instance - Test 2"
    mock_job2.slices = "0 9 * * 1-5"
    mock_job2.command = "test command 2"
    mock_job2.is_enabled.return_value = False
    
    mock_job3 = Mock()
    mock_job3.comment = "other-app: some task"  # Should be filtered out
    mock_job3.slices = "0 12 * * *"
    mock_job3.command = "other command"
    mock_job3.is_enabled.return_value = True
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job1, mock_job2, mock_job3]))
    
    jobs = scheduler.list_jobs()
    
    assert len(jobs) == 2  # Should exclude non-lambdalabs jobs
    
    assert jobs[0]["id"] == "0"
    assert jobs[0]["schedule"] == "0 18 * * *"
    assert jobs[0]["enabled"] is True
    
    assert jobs[1]["id"] == "1"
    assert jobs[1]["schedule"] == "0 9 * * 1-5"
    assert jobs[1]["enabled"] is False


def test_remove_job(scheduler):
    """Test removing a scheduled job."""
    mock_job1 = Mock()
    mock_job1.comment = "lambdalabs-cli: test job 1"
    
    mock_job2 = Mock()
    mock_job2.comment = "lambdalabs-cli: test job 2"
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job1, mock_job2]))
    
    result = scheduler.remove_job("1")  # Remove second job
    
    assert result is True
    scheduler.cron.remove.assert_called_once_with(mock_job2)
    scheduler.cron.write.assert_called_once()


def test_remove_job_not_found(scheduler):
    """Test removing a non-existent job."""
    mock_job = Mock()
    mock_job.comment = "lambdalabs-cli: test job"
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job]))
    
    result = scheduler.remove_job("999")  # Non-existent job
    
    assert result is False
    scheduler.cron.remove.assert_not_called()


def test_enable_job(scheduler):
    """Test enabling a scheduled job."""
    mock_job = Mock()
    mock_job.comment = "lambdalabs-cli: test job"
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job]))
    
    result = scheduler.enable_job("0")
    
    assert result is True
    mock_job.enable.assert_called_once()
    scheduler.cron.write.assert_called_once()


def test_disable_job(scheduler):
    """Test disabling a scheduled job."""
    mock_job = Mock()
    mock_job.comment = "lambdalabs-cli: test job"
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job]))
    
    result = scheduler.disable_job("0")
    
    assert result is True
    mock_job.enable.assert_called_once_with(False)
    scheduler.cron.write.assert_called_once()


def test_clear_all_jobs(scheduler):
    """Test clearing all scheduled jobs."""
    mock_job1 = Mock()
    mock_job1.comment = "lambdalabs-cli: test job 1"
    
    mock_job2 = Mock()
    mock_job2.comment = "lambdalabs-cli: test job 2"
    
    mock_job3 = Mock()
    mock_job3.comment = "other-app: other job"  # Should not be removed
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job1, mock_job2, mock_job3]))
    
    count = scheduler.clear_all_jobs()
    
    assert count == 2
    assert scheduler.cron.remove.call_count == 2
    scheduler.cron.write.assert_called_once()


def test_clear_all_jobs_none_found(scheduler):
    """Test clearing jobs when no lambdalabs jobs exist."""
    mock_job = Mock()
    mock_job.comment = "other-app: other job"
    
    scheduler.cron.__iter__ = Mock(return_value=iter([mock_job]))
    
    count = scheduler.clear_all_jobs()
    
    assert count == 0
    scheduler.cron.remove.assert_not_called()
    scheduler.cron.write.assert_not_called()


def test_job_comment_generation(scheduler):
    """Test job comment generation."""
    comment = scheduler._create_job_comment("terminate_instance", "Test description")
    
    assert comment == "lambdalabs-cli: terminate_instance - Test description"