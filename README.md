# Lambda Labs CLI

A command-line interface for managing Lambda Labs cloud GPU instances with advanced scheduling capabilities.

## Features

- **Instance Management**: List, create, and terminate instances
- **Filesystem Management**: Manage filesystems with default filesystem support
- **SSH Key Integration**: Automatic SSH key management using your existing keys
- **Smart Scheduling**: Create cron jobs for automated instance management
- **Configuration Management**: Easy API key and SSH directory configuration

## Installation

```bash
uv pip install -e .
```

## Quick Start

1. Set your API key:
```bash
lambdalabs config set-api-key YOUR_API_KEY
```

2. List available instances:
```bash
lambdalabs instances list
```

3. View available instance types and regions:
```bash
lambdalabs info
```

## Core Commands

### Instance Management

```bash
# List all instances
lambdalabs instances list

# Create a new instance
lambdalabs instances create --type gpu_1x_a10 --region us-south-1 --name my-instance

# Terminate an instance
lambdalabs instances terminate INSTANCE_ID

# Terminate all instances
lambdalabs instances terminate-all
```

### Filesystem Management

```bash
# List filesystems
lambdalabs filesystems list

# Set default filesystem (used automatically when creating instances)
lambdalabs filesystems set-default FILESYSTEM_NAME

# Create a new filesystem
lambdalabs filesystems create my-filesystem --region us-south-1
```

### Scheduling (Cron Jobs)

Schedule automatic instance management:

```bash
# Terminate all instances in 30 minutes
lambdalabs schedule add-termination --in 30

# Terminate all instances at 6 PM
lambdalabs schedule add-termination --at 18:00

# Start an instance every weekday at 9 AM
lambdalabs schedule add-startup --type gpu_1x_a10 --region us-south-1 --cron "0 9 * * 1-5"

# Terminate all instances every weekday at 6 PM
lambdalabs schedule add-recurring-termination --cron "0 18 * * 1-5"

# List all scheduled jobs
lambdalabs schedule list

# Disable a job
lambdalabs schedule disable JOB_ID

# Remove a job
lambdalabs schedule remove JOB_ID

# Clear all scheduled jobs
lambdalabs schedule clear
```

### Configuration

```bash
# Show current configuration (API key partially redacted)
lambdalabs config show

# Show configuration with full API key
lambdalabs config show --full

# Get just the API key (useful for scripting)
lambdalabs config get-api-key

# Set API key
lambdalabs config set-api-key YOUR_API_KEY

# Set SSH directory
lambdalabs config set-ssh-dir /path/to/ssh/keys

# Rotate API key
lambdalabs config rotate
```

## Configuration

The CLI stores configuration in `~/.lambdalabs/config.toml`:

```toml
api_key = "your_api_key_here"
ssh_dir = "/Users/you/.ssh"
default_filesystem = "your_default_filesystem"
```

## SSH Key Management

The CLI automatically uses SSH keys from your configured SSH directory (default: `~/.ssh`). It looks for:
- `id_rsa.pub`
- `id_ed25519.pub` 
- `id_ecdsa.pub`

If no SSH keys are found in Lambda Labs, it will automatically upload your first available public key.

## Scheduling Examples

Create a development workflow:

```bash
# Start instance every weekday morning
lambdalabs schedule add-startup \
  --type gpu_1x_a10 \
  --region us-south-1 \
  --name dev-instance \
  --cron "0 9 * * 1-5" \
  --description "Daily dev instance"

# Shut down every evening
lambdalabs schedule add-recurring-termination \
  --cron "0 18 * * 1-5" \
  --description "Evening shutdown"
```

## Error Handling

The CLI provides clear error messages and suggestions. Common issues:

- **No capacity**: Try a different instance type or region
- **No SSH keys**: The CLI will automatically upload your SSH key
- **Invalid cron schedule**: Use standard cron format (minute hour day month weekday)

## Development

Built with:
- Python 3.13+
- Click for CLI framework
- Rich for beautiful terminal output
- python-crontab for scheduling
- requests for API communication

## License

MIT License