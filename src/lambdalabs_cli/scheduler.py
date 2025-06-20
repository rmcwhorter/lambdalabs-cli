import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union
from crontab import CronTab
from .config import Config


class LambdaLabsScheduler:
    def __init__(self, config: Config):
        self.config = config
        self.cron = CronTab(user=True)
        self.comment_prefix = "lambdalabs-cli"
        
    def _get_script_path(self) -> str:
        return sys.executable
        
    def _create_job_command(self, action: str, **kwargs) -> str:
        cli_module = "lambdalabs_cli.cli"
        base_cmd = f"{self._get_script_path()} -m {cli_module}"
        
        if action == "terminate_instance":
            return f"{base_cmd} instances terminate {kwargs['instance_id']}"
        elif action == "terminate_instance_by_name":
            return f"{base_cmd} instances terminate-by-name {kwargs['instance_name']}"
        elif action == "terminate_all":
            return f"yes | {base_cmd} instances terminate-all"
        elif action == "create_instance":
            cmd = f"{base_cmd} instances ensure --type {kwargs['instance_type']} --region {kwargs['region']}"
            if kwargs.get('name'):
                cmd += f" --name {kwargs['name']}"
            else:
                raise ValueError("Instance name is required for scheduled creation")
            if kwargs.get('filesystem'):
                cmd += f" --filesystem {kwargs['filesystem']}"
            return cmd
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def _create_job_comment(self, action: str, description: str = "") -> str:
        return f"{self.comment_prefix}: {action} - {description}"
    
    def add_scheduled_job(self, action: str, schedule: str, description: str = "", **kwargs) -> str:
        command = self._create_job_command(action, **kwargs)
        comment = self._create_job_comment(action, description)
        
        job = self.cron.new(command=command, comment=comment)
        job.setall(schedule)
        
        if not job.is_valid():
            raise ValueError(f"Invalid cron schedule: {schedule}")
        
        self.cron.write()
        return str(job)
    
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
        for i, job in enumerate(self.cron):
            if job.comment and job.comment.startswith(self.comment_prefix):
                jobs.append({
                    "id": str(i),
                    "schedule": str(job.slices),
                    "command": job.command,
                    "comment": job.comment,
                    "enabled": job.is_enabled()
                })
        return jobs
    
    def remove_job(self, job_id: str) -> bool:
        jobs_to_check = []
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                jobs_to_check.append(job)
        
        try:
            job_index = int(job_id)
            if 0 <= job_index < len(jobs_to_check):
                self.cron.remove(jobs_to_check[job_index])
                self.cron.write()
                return True
        except ValueError:
            pass
        return False
    
    def enable_job(self, job_id: str) -> bool:
        jobs_to_check = []
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                jobs_to_check.append(job)
        
        try:
            job_index = int(job_id)
            if 0 <= job_index < len(jobs_to_check):
                jobs_to_check[job_index].enable()
                self.cron.write()
                return True
        except ValueError:
            pass
        return False
    
    def disable_job(self, job_id: str) -> bool:
        jobs_to_check = []
        for job in self.cron:
            if job.comment and job.comment.startswith(self.comment_prefix):
                jobs_to_check.append(job)
        
        try:
            job_index = int(job_id)
            if 0 <= job_index < len(jobs_to_check):
                jobs_to_check[job_index].enable(False)
                self.cron.write()
                return True
        except ValueError:
            pass
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