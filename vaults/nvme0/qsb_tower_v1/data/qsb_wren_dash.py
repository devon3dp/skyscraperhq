#!/usr/bin/env python
import os
import sys
from datetime import datetime

class Dashboard:
    def __init__(self):
        self.floor_cards = []
        self.cycle_counter = 0
        self.mood_avatar = 'neutral'
        self.past_window = []

    def update_floor_cards(self, floor_cards):
        self.floor_cards = floor_cards
        self.update_cycle_counter()

    def update_cycle_counter(self):
        self.cycle_counter += 1

    def set_mood_avatar(self, mood):
        self.mood_avatar = mood

    def add_to_past_window(self, event):
        self.past_window.append(event)

    def display_dashboard(self):
        print(f'Cycle Counter: {self.cycle_counter}')
        print('Floor Cards:')
        for card in self.floor_cards:
            print(card)
        print(f'Mood Avatar: {self.mood_avatar}')
        print('Past Window Events:')
        for event in self.past_window:
            print(event)

if __name__ == '__main__':
    dashboard = Dashboard()
    # Example usage
    floor_cards = ['F46 - Wren Bench', 'F47 - HQ Claude']
    dashboard.update_floor_cards(floor_cards)
    dashboard.set_mood_avatar('happy')
    dashboard.add_to_past_window('Updated evolution gauge.')
    dashboard.display_dashboard()