#!/usr/bin/env python
import json
from datetime import datetime
class WrenDashboard:
    def __init__(self):
        self.cycle_registry = '/vaults/nvme0/qsb_tower_v1/floors/floor_46_wren_bench/memory/cycle_registry.jsonl'
        self.floor_cards = '/vaults/nvme0/qsb_tower_v1/floors/floor_46_wren_bench/memory/floor_cards.jsonl'
    def get_cycle_count(self):
        with open(self.cycle_registry, 'r') as f:
            cycles = [json.loads(line) for line in f]
            return len(cycles)
    def get_floor_card(self, floor):
        with open(self.floor_cards, 'r') as f:
            cards = [json.loads(line) for line in f]
            card = next((c for c in cards if c['floor'] == floor), None)
            return card
if __name__ == '__main__':
    dashboard = WrenDashboard()
    cycle_count = dashboard.get_cycle_count()
    print(f'Current Cycle Count: {cycle_count}')