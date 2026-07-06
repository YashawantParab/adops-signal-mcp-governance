from pathlib import Path

from app.config import get_settings


def lookup_docs(query: str, limit: int = 3) -> list[dict[str, str]]:
    data_dir = Path(get_settings().data_dir) / "adops_docs"
    if not data_dir.exists():
        return []

    query_terms = {term.strip(".,:;!?").lower() for term in query.split() if len(term) > 2}
    matches: list[tuple[int, Path, str]] = []
    for path in data_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        score = sum(1 for term in query_terms if term in text.lower())
        if score:
            matches.append((score, path, text))

    ranked = sorted(matches, key=lambda item: item[0], reverse=True)[:limit]
    return [
        {
            "title": path.stem.replace("_", " ").title(),
            "source": path.name,
            "excerpt": text.strip().split("\n\n")[0][:420],
        }
        for _, path, text in ranked
    ]
