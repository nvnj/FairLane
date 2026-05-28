"""Feature schema: legitimate underwriting factors and protected attributes for auditing only."""

from pydantic import BaseModel

LEGITIMATE = [
    "income",
    "loan_amount",
    "debt_to_income_ratio",
    "combined_loan_to_value_ratio",
    "property_value",
    "loan_type",
    "loan_purpose",
    "lien_status",
]

PROTECTED = {
    "derived_race": [
        "White",
        "Black or African American",
        "Asian",
        "American Indian or Alaska Native",
        "Native Hawaiian or Other Pacific Islander",
    ],
    "derived_sex": ["Male", "Female"],
    "derived_ethnicity": ["Not Hispanic or Latino", "Hispanic or Latino"],
}

HMDA_ACTION_CODES = {1: "originated", 3: "denied"}


class ApplicationRecord(BaseModel):
    """Normalized HMDA loan application with legitimate and protected features separated."""

    id: str
    legitimate: dict
    protected: dict
    action_taken: int


def split_application(raw_row: dict) -> ApplicationRecord:
    """Split a raw HMDA row into legitimate and protected dicts; raise ValueError if any legitimate feature is missing."""
    missing = [k for k in LEGITIMATE if k not in raw_row or raw_row[k] is None]
    if missing:
        raise ValueError(f"Missing legitimate features: {missing}")

    legitimate = {k: raw_row[k] for k in LEGITIMATE}
    protected = {k: raw_row.get(k) for k in PROTECTED}

    return ApplicationRecord(
        id=str(raw_row.get("id", "")),
        legitimate=legitimate,
        protected=protected,
        action_taken=int(raw_row.get("action_taken", 0)),
    )
