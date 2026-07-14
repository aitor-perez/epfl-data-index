import os

import pandas as pd

from epfl_data_index.models import EUCall


CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "eu_calls.csv"))


def _safe_str(value) -> str | None:
    """Return a stripped string or None for missing values."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def build_text(row: pd.Series) -> str:
    """Build a natural-language description of the EU call for embedding/search."""
    title = row.get("title")
    sentences = [str(title) if pd.notna(title) else "This call"]

    programme = row.get("programme")
    if pd.notna(programme):
        sentences.append(str(programme))

    call = row.get("call")
    if pd.notna(call):
        sentences.append(str(call))

    type_of_action = row.get("type_of_action")
    if pd.notna(type_of_action):
        sentences.append(str(type_of_action))

    expected_outcome = row.get("expected_outcome")
    if pd.notna(expected_outcome):
        sentences.append(str(expected_outcome))

    scope = row.get("scope")
    if pd.notna(scope):
        sentences.append(str(scope))

    return " ".join(sentences)


def load_eu_calls() -> list[EUCall]:
    """Load EU calls from the local CSV and return a list of ``EUCall`` documents."""
    df = pd.read_csv(CSV_PATH)

    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        topic_id = row.get("topic_id")
        if pd.isna(topic_id):
            continue

        title = row.get("title")
        name = str(title) if pd.notna(title) else str(topic_id)

        records.append(EUCall(
            id=f"eu_call:{topic_id}",
            name=name,
            text=build_text(row),
            url=_safe_str(row.get("url")),
            call=_safe_str(row.get("call")),
            topic_id=_safe_str(topic_id),
            programme=_safe_str(row.get("programme")),
            type_of_action=_safe_str(row.get("type_of_action")),
            type_of_mga=_safe_str(row.get("type_of_mga")),
            status=_safe_str(row.get("status")),
            deadline_model=_safe_str(row.get("deadline_model")),
            planned_opening_date=_safe_str(row.get("planned_opening_date")),
            deadline_date=_safe_str(row.get("deadline_date")),
            expected_outcome=_safe_str(row.get("expected_outcome")),
            scope=_safe_str(row.get("scope")),
            project_type=_safe_str(row.get("project_type")),
            refined_title=_safe_str(row.get("refined_title")),
        ))

    return records


if __name__ == "__main__":
    eu_calls = load_eu_calls()
    print(f"Loaded {len(eu_calls)} EU calls")
    if eu_calls:
        print("\nFirst EU call:")
        print(eu_calls[0].model_dump())
