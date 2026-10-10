#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This class is used by the other Vim-Ollama python scripts
# to trace debug info to file and severe errors also to console.
# This way we can generate model-agnostic conversations.
import os
import logging
from logging.handlers import RotatingFileHandler


DEFAULT_LOG_DIR = os.path.expanduser("~/.vim/state/ollama/logs")


class SecureRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler that creates log files with owner-only access."""

    def _open(self):
        previous_umask = os.umask(0o077)
        try:
            return super()._open()
        finally:
            os.umask(previous_umask)

    def doRollover(self):
        super().doRollover()
        for suffix in [""] + [f".{index}" for index in range(1, self.backupCount + 1)]:
            path = self.baseFilename + suffix
            if os.path.isfile(path) and not os.path.islink(path):
                os.chmod(path, 0o600)


class OllamaLogger:
    DEFAULT_LOG_DIR = DEFAULT_LOG_DIR
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG

    def __init__(self, log_dir=DEFAULT_LOG_DIR, log_filename='ollama.log', log_level=logging.ERROR):
        # Create a logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        # Attempt to create a log directory and set up file logging
        self.fh = None  # File handler

        try:
            if os.path.islink(log_dir):
                raise OSError("log directory must not be a symbolic link")
            previous_umask = os.umask(0o077)
            try:
                os.makedirs(log_dir, mode=0o700, exist_ok=True)
            finally:
                os.umask(previous_umask)
            os.chmod(log_dir, 0o700)

            log_path = os.path.join(log_dir, log_filename)
            if os.path.islink(log_path):
                raise OSError("log file must not be a symbolic link")
            fh = SecureRotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=2)
            os.chmod(log_path, 0o600)
            fh.setLevel(log_level)

            # Create a logging format for the file handler
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)

            # Add the file handler to the logger
            self.logger.addHandler(fh)
            self.fh = fh
        except (OSError, PermissionError) as e:
            pass
            # File logging will be skipped

        # Set up a console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR)  # Only trace errors to console

        # Create a logging format for the console handler
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(console_formatter)

        # Add the console handler to the logger
        self.logger.addHandler(ch)

    def setLevel(self, level):
        self.logger.setLevel(level)
        if self.fh:
            self.fh.setLevel(level)

    def error(self, message):
        """Log an error message."""
        self.logger.error(message)

    def info(self, message):
        """Log an info message."""
        self.logger.info(message)

    def warning(self, message):
        """Log a warning message."""
        self.logger.warning(message)

    def debug(self, message):
        """Log a debug message."""
        self.logger.debug(message)
