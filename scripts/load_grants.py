import os
from functools import cache

import pandas as pd
from dotenv import dotenv_values
import tableauserverclient as TSC
from vizql_data_service_py import (
    VizQLDataServiceClient,
    Datasource,
    ReadMetadataRequest,
    read_metadata,
    DimensionField,
    Query,
    QueryRequest,
    query_datasource,
)

from epfl_data_index.models import Grant


TABLEAU_API_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tableau_api"))
CONFIG_PATH = os.path.join(TABLEAU_API_REPO, "conf", "pat-prod.env")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"Configuration file not found: {CONFIG_PATH}\n"
        "Ensure 'conf/pat-prod.env' exists in the tableau_api repo."
    )

@cache
def _get_client() -> VizQLDataServiceClient:
    """Return a cached VizQL data service client (initialized lazily)."""
    settings = dotenv_values(CONFIG_PATH)
    tableau_auth = TSC.PersonalAccessTokenAuth(
        settings["ACCESS_TOKEN_NAME"], settings["PERSONAL_ACCESS_TOKEN"]
    )
    server = TSC.Server(settings["SERVER_URL"])
    server.auth.sign_in(tableau_auth)
    return VizQLDataServiceClient(settings["SERVER_URL"], server, tableau_auth)


GRANTS_LUID = "0fbeb8ba-5b3c-4809-85b9-340b6934363f"

# Selected columns from the datasource, mapped to friendlier names.
GRANT_COLUMNS = {
    "Projet - ID": "grant_id",
    "Demande - Référence subside": "reference",
    "SUBSIDE_OR_CONTRAT_ID": "internal_id",
    "Demande - Titre": "title",
    "Projet - Type - Description": "project_type",
    "Demande - Etat - Description": "status",
    "Project_start_date": "start_date",
    "Project end date": "end_date",
    "Project duration": "duration",
    "Requérante principale PI - Prénom": "pi_firstname",
    "Requérante principale PI - Nom": "pi_lastname",
    "Requérante principale PI - SCIPER": "pi_sciper",
    "EPFL contact - Prénom": "epfl_contact_firstname",
    "EPFL contact - Nom": "epfl_contact_lastname",
    "EPFL contact - SCIPER": "epfl_contact_sciper",
    "source financement": "funding_source",
    "Action - Description": "funding_program",
    "Action": "action",
    "Funding source - Country (en)": "funding_country",
    "EPFL_amount_CHF": "amount",
    "Total funding CHF": "total_funding",
    "Sigle unité subside": "unit_acronym",
    "Nom unité subside": "unit_name",
    "Proposal Faculté": "faculty",
    "Proposal Laboratory acronym": "laboratory",
    "URL unité": "unit_url",
}


def _safe_int(value) -> int | None:
    """Convert a value to int if possible, otherwise None."""
    if pd.isna(value):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> float | None:
    """Convert a value to float if possible, otherwise None."""
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _full_name(firstname, lastname) -> str | None:
    """Combine first and last names, handling NaN."""
    parts = []
    if pd.notna(firstname) and str(firstname).strip():
        parts.append(str(firstname).strip())
    if pd.notna(lastname) and str(lastname).strip():
        parts.append(str(lastname).strip())
    return " ".join(parts) if parts else None


def extract_data(luid: str) -> pd.DataFrame:
    """Query the selected grant fields from Tableau and return a DataFrame."""
    client = _get_client()
    datasource = Datasource(datasourceLuid=luid)

    meta_request = ReadMetadataRequest(datasource=datasource)
    meta_response = read_metadata.sync(client=client, body=meta_request)

    if meta_response is None:
        print("ERROR: Could not read metadata. Details:")
        print(read_metadata.sync_detailed(client=client, body=meta_request))
        return pd.DataFrame()

    available_captions = {md.fieldCaption for md in meta_response.data}
    missing = set(GRANT_COLUMNS.keys()) - available_captions
    if missing:
        print(f"WARNING: requested fields not found in datasource: {sorted(missing)}")

    fields = [
        DimensionField(fieldCaption=caption)
        for caption in GRANT_COLUMNS.keys()
        if caption in available_captions
    ]

    query_request = QueryRequest(
        query=Query(fields=fields),
        datasource=datasource,
    )
    query_response = query_datasource.sync(client=client, body=query_request)

    if query_response is None:
        print("ERROR: Could not query data. Details:")
        print(query_datasource.sync_detailed(client=client, body=query_request))
        return pd.DataFrame()

    df = pd.DataFrame(query_response.data)
    df = df.rename(columns=GRANT_COLUMNS)
    return df


def build_text(row: pd.Series) -> str:
    """Build a natural-language description of the grant for embedding/search."""
    title = row.get("title")
    sentences = [str(title) if pd.notna(title) else "This project"]

    funding_program = row.get("funding_program")
    if pd.notna(funding_program):
        sentences.append(str(funding_program))

    pi = _full_name(row.get("pi_firstname"), row.get("pi_lastname"))
    if pi:
        sentences.append(f"Principal investigator: {pi}.")

    epfl_contact = _full_name(row.get("epfl_contact_firstname"), row.get("epfl_contact_lastname"))
    if epfl_contact:
        sentences.append(f"EPFL contact: {epfl_contact}.")

    unit_parts = []
    if pd.notna(row.get("laboratory")):
        unit_parts.append(str(row["laboratory"]))
    if pd.notna(row.get("unit_name")):
        unit_parts.append(str(row["unit_name"]))
    if pd.notna(row.get("faculty")):
        unit_parts.append(f"{row['faculty']} faculty")

    if unit_parts:
        sentences.append("Hosted at " + ", ".join(unit_parts) + ".")

    return " ".join(sentences)


def load_grants() -> list[Grant]:
    """Fetch grants data from Tableau and return a list of ``Grant`` documents."""
    df = extract_data(GRANTS_LUID)

    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        grant_id = row.get("grant_id")
        if pd.isna(grant_id):
            continue

        title = row.get("title")
        name = str(title) if pd.notna(title) else str(grant_id)

        start_date = row.get("start_date")
        year = None
        if pd.notna(start_date):
            try:
                year = pd.to_datetime(start_date).year
            except (ValueError, TypeError):
                year = None

        records.append(Grant(
            id=f"grant:{grant_id}",
            name=name,
            text=build_text(row),
            url=row.get("unit_url") if pd.notna(row.get("unit_url")) else None,
            grant_id=str(grant_id),
            title=title if pd.notna(title) else None,
            year=year,
            status=row.get("status") if pd.notna(row.get("status")) else None,
            start_date=str(start_date) if pd.notna(start_date) else None,
            end_date=str(row.get("end_date")) if pd.notna(row.get("end_date")) else None,
            duration=_safe_float(row.get("duration")),
            pi_name=_full_name(row.get("pi_firstname"), row.get("pi_lastname")),
            pi_sciper=str(int(row["pi_sciper"])) if pd.notna(row.get("pi_sciper")) and str(row["pi_sciper"]) != "00000000000" else None,
            epfl_contact_name=_full_name(row.get("epfl_contact_firstname"), row.get("epfl_contact_lastname")),
            epfl_contact_sciper=str(int(row["epfl_contact_sciper"])) if pd.notna(row.get("epfl_contact_sciper")) and str(row["epfl_contact_sciper"]) != "00000000000" else None,
            funding_source=row.get("funding_source") if pd.notna(row.get("funding_source")) else None,
            funding_program=row.get("funding_program") if pd.notna(row.get("funding_program")) else None,
            funding_country=row.get("funding_country") if pd.notna(row.get("funding_country")) else None,
            amount=_safe_float(row.get("amount")),
            total_funding=_safe_float(row.get("total_funding")),
            unit_name=row.get("unit_name") if pd.notna(row.get("unit_name")) else None,
            unit_acronym=row.get("unit_acronym") if pd.notna(row.get("unit_acronym")) else None,
            faculty=row.get("faculty") if pd.notna(row.get("faculty")) else None,
            laboratory=row.get("laboratory") if pd.notna(row.get("laboratory")) else None,
            unit_url=row.get("unit_url") if pd.notna(row.get("unit_url")) else None,
            project_type=row.get("project_type") if pd.notna(row.get("project_type")) else None,
            reference=row.get("reference") if pd.notna(row.get("reference")) else None,
            internal_id=str(row.get("internal_id")) if pd.notna(row.get("internal_id")) else None,
        ))

    return records


if __name__ == "__main__":
    grants = load_grants()
    print(f"Loaded {len(grants)} grants")
    if grants:
        print("\nFirst grant:")
        print(grants[0].model_dump())
