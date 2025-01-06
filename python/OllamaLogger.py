#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
#
# This class can generate model specific chats for different roles
# using the tags use for training the model.
# This way we can generate model agnostic conversations.
import os
import logging
from logging.handlers import RotatingFileHandler

class OllamaLogger:
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG

    def __init__(self, log_filename, log_level=logging.ERROR):
        # Create a logger
        self.logger = logging.getLogger()
        self.logger.setLevel(log_level)

        log_dir = '/tmp/logs'

        # Create a file handler which logs even debug messages
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_path = os.path.join(log_dir, log_filename)
        fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=2)
        fh.setLevel(log_level)
        self.fh = fh

        # Create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR) # only trace errors to console

        # Create a logging format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        # Add the handlers to the logger
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

    def setLevel(self, level):
        self.logger.setLevel(level)
        self.fh.setLevel(level)

    def error(self, message):
        """
        Log a error message.
        """
        self.logger.error(message)

    def info(self, message):
        """
        Log an info message.
        """
        self.logger.info(message)

    def warning(self, message):
        """
        Log a warning message.
        """
        self.logger.warning(message)

    def debug(self, message):
        """
        Log a debug message.
        """
        self.logger.debug(message)

