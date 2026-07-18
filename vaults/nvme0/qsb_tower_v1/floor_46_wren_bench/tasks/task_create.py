#!/usr/bin/env python3
import json
from datetime import datetime

def create_task(task):
    timestamp = datetime.now().isoformat()
    task['created_at'] = timestamp
    with open('/vaults/nvme0/qsb_tower_v1/floor_46_wren_bench/tasks/tasks.json', 'a') as f:
        json.dump(task, f)
        f.write('\n')
