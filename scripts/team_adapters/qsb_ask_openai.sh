#!/bin/bash
python3 -c "import sys; sys.path.insert(0, \"$HOME/qsb_agents\"); import consult; print(consult.ask_openai(sys.argv[1], 900))" "$1"
