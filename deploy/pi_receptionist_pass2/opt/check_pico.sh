#!/bin/bash
# QSB Receptionist — Pico (RP2040) presence check. Does NOT flash firmware.
echo "=== QSB Pico check $(date -Is) ==="
echo "--- lsusb (looking for RP2040 / Pico 2e8a) ---"
lsusb 2>/dev/null | grep -iE '2e8a|rp2040|pico|raspberry' || echo "no Pico USB id (2e8a) seen"
echo "--- serial devices ---"
ls -l /dev/ttyACM* 2>/dev/null || echo "no /dev/ttyACM*"
ls -l /dev/ttyUSB* 2>/dev/null || echo "no /dev/ttyUSB*"
echo "--- dmesg (Pico/RP2040/tty) ---"
(dmesg 2>/dev/null || sudo dmesg 2>/dev/null) | grep -iE 'rp2040|pico|ttyACM|cdc_acm' | tail -10 || echo "no dmesg matches"
echo "NOTE: firmware NOT flashed. Flash only on explicit Ross order."
