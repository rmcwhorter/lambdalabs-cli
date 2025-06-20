"""Logging configuration for Lambda Labs CLI."""
import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(debug: bool = False, log_file: Optional[str] = None) -> logging.Logger:
    """Set up logging for the CLI."""
    # Create logger
    logger = logging.getLogger("lambdalabs_cli")
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Set level
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler (only for errors and warnings by default)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(f"lambdalabs_cli.{name}")