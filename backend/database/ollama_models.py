from sqlmodel import Session, select

from database.models import OllamaModel


def list_models_from_db(session: Session, query: str | None = None) -> list[OllamaModel]:
    stmt = select(OllamaModel).order_by(OllamaModel.name)
    if query:
        stmt = stmt.where(OllamaModel.name.ilike(f"%{query.strip()}%"))  # type: ignore[attr-defined]
    return list(session.exec(stmt).all())


def upsert_models(session: Session, models: list[dict]) -> list[OllamaModel]:
    """Insert or update every model from Ollama and remove ones no longer available."""
    seen: set[str] = set()
    rows: list[OllamaModel] = []

    for item in models:
        name = item["name"]
        seen.add(name)
        row = session.get(OllamaModel, name)
        if row is None:
            row = OllamaModel(name=name)
        row.reasoning = bool(item.get("reasoning", False))
        row.family = item.get("family")
        row.parameter_size = item.get("parameter_size")
        row.quantization_level = item.get("quantization_level")
        row.size = item.get("size")
        row.modified_at = item.get("modified_at")
        session.add(row)
        rows.append(row)

    for existing in session.exec(select(OllamaModel)).all():
        if existing.name not in seen:
            session.delete(existing)

    session.commit()
    for row in rows:
        session.refresh(row)
    return sorted(rows, key=lambda m: m.name.lower())


def model_count(session: Session) -> int:
    return len(list(session.exec(select(OllamaModel)).all()))
