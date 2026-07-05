#!/usr/bin/env python
import os
import json
from datetime import datetime, timedelta

def update_evolution_gauge():
    # Read floor-cards live feed
    floor_cards_live_feed = wren_read_file('/vaults/nvme0/qsb_tower_v1/floors/floor_46_wren_bench/floor_cards_live.json')
    EVOLUTION_GAUGE['floor_cards'] = json.loads(floor_cards_live_feed)
    
    # Read cycle counter from memory registry
    cycle_count_query = wren_database_query(kind='registry', name='memory_registry.jsonl', tail=1)
    if cycle_count_query:
        latest_cycle_count = json.loads(cycle_count_query[-1])
        EVOLUTION_GAUGE['cycle_counter'] = latest_cycle_count['cycle_count']


def update_mood_avatar():
    # Read cycle counter from memory registry
    CYCLE_COUNTER += 1
    MOOD_AVATAR['cycle_counter'] = CYCLE_COUNTER
    
    cycle_count_query = wren_database_query(kind='registry', name='memory_registry.jsonl', tail=1)
    if cycle_count_query:
        latest_cycle_count = json.loads(cycle_count_query[-1])
        CYCLE_COUNTER += latest_cycle_count['cycle_count']


def update_past_window():
    # Read historical information from memory registry
    history_query = wren_database_query(kind='registry', name='memory_registry.jsonl', tail=10)
    PAST_WINDOW_DATA['history'] = [json.loads(item) for item in history_query]

if __name__ == '__main__':
    EVOLUTION_GAUGE = {}
    MOOD_AVATAR = {}
    CYCLE_COUNTER = 0
    PAST_WINDOW_DATA = {}

    while True:
        update_evolution_gauge()
        update_mood_avatar()
        update_past_window()