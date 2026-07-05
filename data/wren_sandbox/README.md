# Wren Sandbox

Ross gave Wren a sandbox on 2026-07-03. Anything she wants to test — draft
patches, experiment with CSS, try new tools — she can drop it here without
touching production files.

Rules:
- She writes freely here.
- Auto-backup fires on every wren_edit_file — see _archive/wren_backups/.
- If a sandbox experiment works, she copies the vetted version to the
  production path (with auto-backup covering her).
- Nothing in here is loaded by production tools. Safe playground.

## Forge (2026-07-03 16:20Z)

```python
def calculate_distance(point1, point2):
    """
    Calculate the Euclidean distance between two points.
    
    :param point1: Tuple (x1, y1)
    :param point2: Tuple (x2, y2)
    :return: Distance between the two points
    """
    x1, y1 = point1
    x2, y2 = point2
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
```
