```python
import os
import shutil
time_threshold = 7 * 24 * 3600  # 7 days in seconds

snapshots_path = 'data/'

# Glob all *_sandbox/ dirs under data/
sandbox_dirs = glob.glob('data/*_sandbox/')

for sandbox_dir in sandbox_dirs:
    for root, _, files in os.walk(sandbox_dir):
        if 'snapshots' in root:
            continue  # Skip snapshots directory

        for file_name in files:
            file_path = os.path.join(root, file_name)
            mtime = os.path.getmtime(file_path)
            if time.time() - mtime > time_threshold:
                shutil.rmtree(os.path.dirname(file_path))
```