"""README checks: readable in under 5 minutes, has the agreed sections, and every path it names exists."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

SECTIONS = [
    "What it does", "Try it", "Why I built it", "How it works", "How the rain numbers are made",
    "Key decisions", "Testing", "Keeping it up to date", "Limitations", "What next", "Credits",
]


def _words(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)   # diagram and commands are skimmed, not read
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'.,%-]*", text)


def test_has_agreed_sections_in_order():
    heads = re.findall(r"^## (.+)$", README, flags=re.M)
    positions = []
    for s in SECTIONS:
        hit = [i for i, h in enumerate(heads) if h.startswith(s)]
        assert hit, f"missing section: {s}"
        positions.append(hit[0])
    assert positions == sorted(positions)


def test_readable_in_under_five_minutes():
    assert len(_words(README)) <= 1250   # ~250 words a minute


def test_no_emojis():
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", README)


def test_every_named_path_exists():
    paths = set(re.findall(r"\]\(((?:docs|scripts|tests|pipeline|api|web|config|\.github)/[^)#\s]+)", README))
    paths |= set(re.findall(r"`((?:docs|scripts|tests|pipeline|api|web|config|\.github)/[^`\s]+)`", README))
    assert paths
    for p in paths:
        assert (ROOT / p).exists(), p


def test_links_to_live_site_and_example_searches():
    assert "https://rain-forecast-api-qii4.onrender.com" in README
    for example in ("Ooty", "Madurei", "Tanjore"):
        assert example in README


def test_architecture_diagram():
    assert "```mermaid" in README


def test_states_rain_only_and_imd_source():
    assert "farming advice" in README
    assert "SOP" in README and "2021" in README
