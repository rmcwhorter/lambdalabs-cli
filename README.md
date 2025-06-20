# Lambda Labs CLI

An **unofficial** command-line interface for managing Lambda Labs cloud GPU instances with advanced scheduling capabilities.

> ⚠️ **Disclaimer**: This is an unofficial tool and is not affiliated with or endorsed by Lambda Labs. Use at your own risk.

## Why This CLI?

Lambda Labs provides powerful GPU instances but lacks advanced automation tools. This CLI fills that gap by providing:

- **Cost Control**: Automated instance termination to prevent surprise bills
- **Workflow Automation**: Schedule instances to start/stop based on your work schedule  
- **Better UX**: Rich terminal interface with clear, organized output
- **SSH Integration**: Seamless SSH key management using your existing keys
- **Filesystem Management**: Easy handling of persistent storage with smart defaults

## Features

- **Instance Management**: List, create, and terminate instances
- **Filesystem Management**: Manage filesystems with default filesystem support
- **SSH Key Integration**: Automatic SSH key management using your existing keys
- **Smart Scheduling**: Create cron jobs for automated instance management
- **Configuration Management**: Easy API key and SSH directory configuration

## Installation

### From GitHub (Recommended)

```bash
# Using uv (recommended)
uv pip install git+https://github.com/rmcwhorter/lambdalabs-cli.git

# Or using pip
pip install git+https://github.com/rmcwhorter/lambdalabs-cli.git
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/rmcwhorter/lambdalabs-cli.git
cd lambdalabs-cli

# Install in development mode
uv pip install -e .
# or
pip install -e .
```

### Requirements

- Python 3.11+
- A Lambda Labs account and API key

## Quick Start

1. **Get your Lambda Labs API key** from the [Lambda Labs dashboard](https://cloud.lambda.ai/)

2. **Set your API key**:
```bash
lambdalabs config set-api-key YOUR_API_KEY
```

3. **Verify the setup**:
```bash
# Check configuration
lambdalabs config show

# List your current instances
lambdalabs instances list

# View available instance types and regions
lambdalabs info
```

4. **Create your first scheduled job** (optional):
```bash
# Terminate all instances every day at midnight (cost protection)
lambdalabs schedule add-recurring-termination --cron "0 0 * * *" --description "Daily cleanup"
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
- **API authentication errors**: Verify your API key with `lambdalabs config show --full`

## Security Notes

- **API Key Storage**: Keys are stored in `~/.lambdalabs/config.toml` with file permissions 644
- **Cron Jobs**: Scheduled jobs run with your user privileges
- **SSH Keys**: The CLI only reads public keys from your SSH directory
- **No Key Logging**: API keys are never logged or printed unless explicitly requested

## Contributing

This is an unofficial community project. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Development

Built with:
- Python 3.11+
- Click for CLI framework
- Rich for beautiful terminal output
- python-crontab for scheduling
- requests for API communication

### Local Development

```bash
git clone https://github.com/rmcwhorter/lambdalabs-cli.git
cd lambdalabs-cli
uv pip install -e .
```

## Troubleshooting

### Common Issues

**Command not found after installation:**
```bash
# Make sure the installation path is in your PATH
export PATH="$HOME/.local/bin:$PATH"  # For pip
# or check where uv installed it
uv pip show lambdalabs-cli
```

**Cron jobs not working:**
```bash
# Check if crontab service is running
# On macOS: launchctl list | grep cron
# On Linux: systemctl status cron

# Verify jobs are installed
crontab -l | grep lambdalabs-cli
```

**API connection issues:**
```bash
# Test your API key directly
curl -H "Authorization: Bearer $(lambdalabs config get-api-key)" \
     https://cloud.lambda.ai/api/v1/instances
```

## License

MIT License

Copyright (c) 2024 Lambda Labs CLI Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.