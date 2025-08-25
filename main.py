#!/usr/bin/env python3
"""
Backward compatibility wrapper for main.py.
This imports the new CLI module for existing usage patterns.
"""

from k8s_ai.cli.main import main

if __name__ == "__main__":
    main()
