# MOOD BADGE tile spec

Exposes render_mood_badge(mood: str, energy: int) -> str returning inline HTML.
Use case: renders a small colored chip with mood word + energy fill.
Colors: focused=green, sparky=orange, steady=blue, quiet=grey, cloudy=slate.