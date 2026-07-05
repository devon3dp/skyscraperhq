#!/usr/bin/env python
import os
import json
from datetime import datetime, timedelta

class Dashboard:
    def __init__(self):
        self.floor_cards = []
        from qsb_memory_registry import MemoryRegistry
registry = MemoryRegistry()
self.cycle_counter = registry.get_cycle_count()
        self.mood_avatar = 'neutral'
        self.past_window = None
        self.load_floor_cards()
        self.update_cycle_counter()
        self.set_mood_avatar()
        self.open_past_window()
    
    def load_floor_cards(self):
        from qsb_floor_cards import FloorCardsLiveFeed
        self.floor_cards = FloorCardsLiveFeed().get_live_feed()
    
    def update_cycle_counter(self):
        from qsb_memory_registry import MemoryRegistry
        registry = MemoryRegistry()
        self.cycle_counter = registry.get_cycle_count()
    
    def set_mood_avatar(self):
        from qsb_mood_avatar import MoodAvatar
        self.mood_avatar = MoodAvatar().get_current_state()
    
    def open_past_window(self):
        from qsb_past_window import PastWindow
        self.past_window = PastWindow().open()