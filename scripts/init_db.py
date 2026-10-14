import sys

from app.db import initialize_database
from scripts.cli import run_cli


if __name__ == "__main__":

    def main() -> None:
        initialize_database()
        print("Database schema initialized.")

    sys.exit(run_cli(main))
