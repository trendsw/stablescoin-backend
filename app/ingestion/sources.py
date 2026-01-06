import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "sources.yaml"

def load_sources():
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f)
    return data["sources"]

def get_source_credibility_map(default: float = 0.5) -> dict[str, float]:
    sources = load_sources()
    return {
        src["name"]: float(src.get("credibility_score", default))
        for src in sources
    }
    
SOURCE_CREDIBILITY_MAP = get_source_credibility_map()
