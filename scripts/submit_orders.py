import sys

from scripts.burst_demo import main
from scripts.cli import run_cli

if __name__ == "__main__":
    sys.exit(run_cli(main))
