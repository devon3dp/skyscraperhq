#!/usr/bin/env python
import os
from qsb import utils

def _offline_fallback():
    print('No inference hosts available, falling back to offline mode.')
    # Add your fallback logic here
    return None

if __name__ == '__main__':
    if not utils.get_inference_hosts():
        _offline_fallback()
    else:
        # Proceed with normal operations
        pass