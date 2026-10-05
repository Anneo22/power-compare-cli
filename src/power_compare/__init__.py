"""Local, read-only cycling power diagnostics."""
from .core import Ride, compare, compare_files, read_ride, recommend_protocol

__all__ = ["Ride", "compare", "compare_files", "read_ride", "recommend_protocol"]
