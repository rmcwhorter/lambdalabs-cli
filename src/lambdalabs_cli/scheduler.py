import json
import sys
import shlex
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union
from crontab import CronTab
from .config import Config
from .logging_config import get_logger

logger = get_logger("scheduler")


class LambdaLabsScheduler:
    def __init__(self, config: Config):
        self.config = config
        self.cron = CronTab(user=True)
        self.comment_prefix = "lambdalabs-cli"
    
    def _validate_instance_name(self, name: str) -> bool:
        """Validate instance name to prevent command injection."""
        if not name:
            return False
        # Only allow alphanumeric, hyphens, and underscores
        return bool(re.match(r'^[a-zA-Z0-9-_]+$', name)) and len(name) <= 64
    
    def _validate_filesystem_name(self, name: str) -> bool:
        """Validate filesystem name to prevent command injection."""
        if not name:
            return False
        return bool(re.match(r'^[a-zA-Z0-9-_]+$', name)) and len(name) <= 64
    
    def _validate_instance_type(self, instance_type: str) -> bool:
        """Validate instance type to prevent command injection."""
        if not instance_type:
            return False
        # Lambda Labs instance types follow pattern like gpu_1x_a10
        return bool(re.match(r'^[a-zA-Z0-9_]+$', instance_type)) and len(instance_type) <= 32
    
    def _validate_region(self, region: str) -> bool:
        """Validate region name to prevent command injection."""
        if not region:
            return False
        # Regions follow pattern like us-south-1
        return bool(re.match(r'^[a-z]+-[a-z]+-[0-9]+$', region)) and len(region) <= 32
        
    def _get_script_path(self) -> str:
        return sys.executable
        
    def _create_job_command(self, action: str, **kwargs) -> str:
        """Create a safe shell command for cron execution."""
        cli_module = "lambdalabs_cli.cli"
        base_cmd = [self._get_script_path(), "-m", cli_module]
        
        if action == "terminate_instance":
            instance_id = kwargs.get('instance_id', '')
            if not re.match(r'^[a-zA-Z0-9-]+$', instance_id):
                raise ValueError(f"Invalid instance ID: {instance_id}")
            cmd = base_cmd + ["instances", "terminate", instance_id]
            
        elif action == "terminate_instance_by_name":
            instance_name = kwargs.get('instance_name', '')
            if not self._validate_instance_name(instance_name):
                raise ValueError(f"Invalid instance name: {instance_name}")
            cmd = base_cmd + ["instances", "terminate-by-name", instance_name]
            
        elif action == "terminate_all":
            # Use subprocess-safe approach instead of shell piping
            cmd = base_cmd + ["instances", "terminate-all", "--yes"]
            
        elif action == "create_instance":
            instance_type = kwargs.get('instance_type', '')
            region = kwargs.get('region', '')
            name = kwargs.get('name', '')
            
            if not self._validate_instance_type(instance_type):
                raise ValueError(f"Invalid instance type: {instance_type}")
            if not self._validate_region(region):
                raise ValueError(f"Invalid region: {region}")
            if not name:
                raise ValueError("Instance name is required")
            if not self._validate_instance_name(name):
                raise ValueError(f"Invalid instance name: {name}")
            
            cmd = base_cmd + ["instances", "ensure", "--type", instance_type, "--region", region, "--name", name]
            
            if kwargs.get('filesystem'):
                filesystem = kwargs['filesystem']
                if not self._validate_filesystem_name(filesystem):
                    raise ValueError(f"Invalid filesystem name: {filesystem}")
                cmd.extend(["--filesystem", filesystem])
        else:
            raise ValueError(f"Unknown action: {action}")
        
        # Use shlex.join for safe shell command construction
        return shlex.join(cmd)
    
    def _create_job_comment(self, action: str, description: str = "", job_id: Optional[str] = None) -> str:
        if not job_id:
            job_id = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
        return f"{self.comment_prefix}: {job_id} - {action} - {description}"
    
    def add_scheduled_job(self, action: str, schedule: str, description: str = "", **kwargs) -> str:
        logger.info(f"Adding scheduled job: action={action}, schedule={schedule}")
        command = self._create_job_command(action, **kwargs)
        job_id = str(uuid.uuid4())[:8]
        comment = self._create_job_comment(action, description, job_id)
        
        logger.debug(f"Generated command: {command}")
        
        job = self.cron.new(command=command, comment=comment)
        job.setall(schedule)
        
        if not job.is_valid():
            logger.error(f"Invalid cron schedule: {schedule}")
            raise ValueError(f"Invalid cron schedule: {schedule}")
        
        self.cron.write()
        logger.info(f"Successfully added scheduled job with ID: {job_id}")
        return job_id
    
    def add_time_based_termination(self, instance_id: Optional[str], 
                                 duration_minutes: Optional[int] = None,
                                 end_time: Optional[str] = None,
                                 description: str = "") -> str:
        if duration_minutes:
            target_time = datetime.now() + timedelta(minutes=duration_minutes)
        elif end_time:
            try:
                target_time = datetime.strptime(end_time, "%H:%M")
                if target_time.time() < datetime.now().time():
                    target_time = target_time.replace(day=datetime.now().day + 1)
                else:
                    target_time = target_time.replace(year=datetime.now().year,
                                                    month=datetime.now().month,
                                                    day=datetime.now().day)
            except ValueError:
                raise ValueError("Time must be in HH:MM format")
        else:
            raise ValueError("Must specify either duration_minutes or end_time")
        
        schedule = f"{target_time.minute} {target_time.hour} {target_time.day} {target_time.month} *"
        
        if instance_id:
            action = "terminate_instance"
            kwargs = {"instance_id": instance_id}
            desc = description or f"Terminate instance {instance_id} at {target_time.strftime('%Y-%m-%d %H:%M')}"
        else:
            action = "terminate_all"
            kwargs = {}
            desc = description or f"Terminate all instances at {target_time.strftime('%Y-%m-%d %H:%M')}"
        
        return self.add_scheduled_job(action, schedule, desc, **kwargs)
    
    def add_recurring_schedule(self, action: str, cron_schedule: str, description: str = "", **kwargs) -> str:
        return self.add_scheduled_job(action, cron_schedule, description, **kwargs)
    
    def list_jobs(self) -> List[Dict[str, str]]:
        jobs = []
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                # Extract job ID from comment format: "lambdalabs-cli: {job_id} - {action} - {description}"
                comment_parts = job.comment.split(" - ", 2)
                if len(comment_parts) >= 2:
                    job_id = comment_parts[0].split(": ")[1]
                else:
                    job_id = "unknown"
                
                jobs.append({
                    "id": job_id,
                    "schedule": str(job.slices),
                    "command": job.command,
                    "comment": job.comment,
                    "enabled": job.is_enabled()
                })
        return jobs
    
    def remove_job(self, job_id: str) -> bool:
        logger.info(f"Removing scheduled job: {job_id}")
        
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                # Extract job ID from comment
                comment_parts = job.comment.split(" - ", 2)
                if len(comment_parts) >= 2:
                    current_job_id = comment_parts[0].split(": ")[1]
                    if current_job_id == job_id:
                        logger.debug(f"Removing job: {job}")
                        self.cron.remove(job)
                        self.cron.write()
                        logger.info(f"Successfully removed job: {job_id}")
                        return True
        
        logger.warning(f"Job not found: {job_id}")
        return False
    
    def enable_job(self, job_id: str) -> bool:
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                # Extract job ID from comment
                comment_parts = job.comment.split(" - ", 2)
                if len(comment_parts) >= 2:
                    current_job_id = comment_parts[0].split(": ")[1]
                    if current_job_id == job_id:
                        job.enable()
                        self.cron.write()
                        return True
        return False
    
    def disable_job(self, job_id: str) -> bool:
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                # Extract job ID from comment
                comment_parts = job.comment.split(" - ", 2)
                if len(comment_parts) >= 2:
                    current_job_id = comment_parts[0].split(": ")[1]
                    if current_job_id == job_id:
                        job.enable(False)
                        self.cron.write()
                        return True
        return False
    
    def clear_all_jobs(self) -> int:
        removed_count = 0
        jobs_to_remove = []
        
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                jobs_to_remove.append(job)
        
        for job in jobs_to_remove:
            self.cron.remove(job)
            removed_count += 1
        
        if removed_count > 0:
            self.cron.write()
        
        return removed_count