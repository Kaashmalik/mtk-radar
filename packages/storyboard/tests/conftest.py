import sys
from pathlib import Path

# packages/ is on sys.path for every worker and the API; mirror that here.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
