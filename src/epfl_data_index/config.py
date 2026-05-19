from pathlib import Path
from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG = dotenv_values(Path(__file__).resolve().parents[2] / '.env')
