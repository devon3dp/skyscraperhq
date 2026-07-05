import shutil

def run():
    paths = ["/", "/vaults/nvme0", "/vaults/ai", "/vaults/kingston"]
    results = {}
    for path in paths:
        total, used, free = shutil.disk_usage(path)
        total_gb = total // (2**30)
        used_gb = used // (2**30)
        free_gb = free // (2**30)
        pct_used = (used / total) * 100
        if pct_used >= 90:
            status = 'critical'
        elif pct_used >= 80:
            status = 'tight'
        else:
            status = 'ok'
        results[path] = {
            'total_gb': total_gb,
            'used_gb': used_gb,
            'free_gb': free_gb,
            'pct_used': pct_used,
            'status': status
        }
    return results