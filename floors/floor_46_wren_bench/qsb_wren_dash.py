#!/usr/bin/env python
import os
import json
from datetime import datetime

class WrenDashboard:
    def __init__(self):
        self.memory_registry = 'data/registries/memory.jsonl'
        self.floor_cards_path = 'floors/floor_46_wren_bench/wren_floor_card.md'
        
    def read_memory_registry(self):
        with open(self.memory_registry, 'r') as f:
            memory_data = list(f)[-1]
            cycle_count = json.loads(memory_data)['cycle']
            return cycle_count
        
    def read_floor_cards(self):
        with open(self.floor_cards_path, 'r') as f:
            floor_card_content = f.read()
            return floor_card_content
        
    def evolution_gauge(self):
        cycle_count = self.read_memory_registry()
        floor_card_data = self.read_floor_cards()
        # Calculate and display evolution gauge based on cycle count and live feed data
        print(f'Evolution Gauge: {cycle_count} cycles')
        
    def mood_avatar(self):
        # Display a mood avatar representing Wren's current state
        print('Mood Avatar: 🌟')
        
    def past_window(self):
        # Show a window of recent activities or events
        print('Past Window: Recent activities and events')
        
    def run_dashboard(self):
        self.evolution_gauge()
        self.mood_avatar()
        self.past_window()