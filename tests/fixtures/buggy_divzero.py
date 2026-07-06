#!/usr/bin/env python3
"""Fixture: trivially buggy script that raises ZeroDivisionError at line 5."""

def divide(a, b):
    return a / b  # line 5 — divides by zero when b == 0

result = divide(10, 0)
print(f"result = {result}")
