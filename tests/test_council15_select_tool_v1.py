#!/usr/bin/env python3

import os
import sys
from importlib.util import spec_from_file_location, module_from_spec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
module_path = os.path.join(ROOT, "tools/qsb_council15_tools.py")
spec = spec_from_file_location("qsb_council15_tools", module_path)
qsb_council15_tools = module_from_spec(spec)
sys.modules["qsb_council15_tools"] = qsb_council15_tools
spec.loader.exec_module(qsb_council15_tools)

def check_tool_routing():
    fake_roster = {
        "workers": [
            {"display_name": "Coder Specialist", "worker_type": "coder", "model": "iquest-coder-v1:40b"},
            {"display_name": "Hermes (reasoning)", "worker_type": "reasoning", "model": "hermes3:70b"},
            {"display_name": "Qwen Researcher", "worker_type": "research", "model": "qwen2.5:14b"}
        ]
    }
    
    qsb_council15_tools._load_roster = lambda: fake_roster["workers"]
    
    # Test code task routing
    tool_spec = qsb_council15_tools.select_tool("Code a new feature", "Implement a new API endpoint")
    assert tool_spec['display_name'] == 'Coder Specialist', f"Expected Coder Specialist, got {tool_spec['display_name']}"

    # Test governance task routing
    tool_spec = qsb_council15_tools.select_tool("Review compliance policy", "Ensure adherence to regulations")
    assert tool_spec['display_name'] == 'Hermes (reasoning)', f"Expected Hermes (reasoning), got {tool_spec['display_name']}"

    # Test research task routing
    tool_spec = qsb_council15_tools.select_tool("Research market trends", "Analyze recent financial data")
    assert tool_spec['display_name'] == 'Qwen Researcher', f"Expected Qwen Researcher, got {tool_spec['display_name']}"

print("OVERALL: PASS")
sys.exit(0)