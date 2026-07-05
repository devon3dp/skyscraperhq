#!/usr/bin/env python3
"""
qsb_logging.py — Provides a LoggingContext class for logging function entry and exit with wall-time.

Usage:
    with LoggingContext('my_function') as log_ctx:
        # Your code here
"""
import time
from datetime import datetime

class LoggingContext:
    def __init__(self, func_name):
        self.func_name = func_name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        print(f'[{datetime.now()}] Entering {self.func_name}')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        print(f'[{datetime.now()}] Exiting {self.func_name} (took {elapsed_time:.2f}s)')

    def log_event(self, event_message):
        current_time = time.time()
        elapsed_since_start = current_time - self.start_time
        print(f'[{datetime.now()}] {event_message} (at {elapsed_since_start:.2f}s since start of function)')

# Example usage:
if __name__ == '__main__':
    with LoggingContext('example_function') as log_ctx:
        time.sleep(1)
        log_ctx.log_event('Event happened inside the context.')