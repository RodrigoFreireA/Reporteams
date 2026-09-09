"""Run the Planner data retention job.

Usage:
    python scripts/purge_expired_data.py [--days 365]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from reportchart_web.config import PLANNER_RETENTION_DAYS  # noqa: E402
from reportchart_web.retention import purge_expired_planner_data  # noqa: E402


parser = argparse.ArgumentParser(description="Expurga dados antigos derivados do Planner.")
parser.add_argument("--days", type=int, default=PLANNER_RETENTION_DAYS)
args = parser.parse_args()

with app.app_context():
    result = purge_expired_planner_data(args.days)
    print(result)
