"""mood_badge — Wren+iQuest L10 collaboration."""

def render_mood_badge(mood: str, energy: int) -> str:
    colors = {
        "happy": "#FFD700",
        "sad": "#4682B4",
        "angry": "#DC143C",
    }
    return f'<span style="background-color: {colors.get(mood, "#000")}; width: {energy * 10}px; display: inline-block;"></span>'