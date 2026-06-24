import io

import pandas as pd
import requests

from epfl_data_index.models import (
    Professor, Publication, Unit,
    PublicationAuthor, PublicationUnit, ProfessorPublication, ProfessorUnit, UnitProfessor, UnitPublication,
)

API_URL = "http://itsisa0052.xaas.epfl.ch:5001/sql/csv"


def _fetch(table: str) -> pd.DataFrame:
    response = requests.post(API_URL, json={"query": f"SELECT * FROM {table}"})
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _load_csvs():
    professors = _fetch("prof")
    prof_pubs = _fetch("sciper_pub")
    prof_units = _fetch("sciper_lab")
    units = _fetch("lab")
    publications = _fetch("pub")

    prof_unit_merged = prof_units.merge(units, on="cf", how="left")

    sciper_to_units = (
        prof_unit_merged
        .groupby("sciper")
        .apply(
            lambda g: g[["cf", "unit_name", "unit_type", "role", "acronym_level_2", "acronym_level_3"]].to_dict("records"),
            include_groups=False,
        )
        .to_dict()
    )

    sciper_to_pub_ids = prof_pubs.groupby("sciper")["id_pub"].apply(list).to_dict()

    return {
        "professors": professors,
        "publications": publications,
        "prof_pubs": prof_pubs,
        "prof_unit_merged": prof_unit_merged,
        "units": units,
        "sciper_to_pub_ids": sciper_to_pub_ids,
        "sciper_to_units": sciper_to_units,
    }


def load_publications(data: dict) -> list[Publication]:
    publications = data["publications"].copy()
    professors = data["professors"]
    prof_pubs = data["prof_pubs"]
    prof_unit_merged = data["prof_unit_merged"]

    publications = publications.rename(columns={
        "id_pub": "publication_id",
        "id_infoscience": "infoscience_url",
        "year_issued": "year",
        "openalex_id": "openalex_url",
    })

    pub_author = (
        prof_pubs
        .merge(professors[["sciper", "firstname", "lastname"]], on="sciper", how="left")
        .merge(
            prof_unit_merged[["sciper", "cf", "unit_name", "unit_type", "cf_level_2", "cf_level_3", "acronym_level_2", "acronym_level_3"]].drop_duplicates(),
            on="sciper",
            how="left",
        )
    )
    pub_author["full_name"] = pub_author["firstname"] + " " + pub_author["lastname"]

    pub_authors_by_id = (
        pub_author[["id_pub", "sciper", "firstname", "lastname", "full_name"]]
        .drop_duplicates(subset=["id_pub", "sciper"])
        .dropna(subset=["sciper"])
        .groupby("id_pub")
        .apply(
            lambda g: [
                PublicationAuthor(
                    id=f"professor:{int(r['sciper'])}",
                    name=r["full_name"],
                    sciper=str(int(r["sciper"])),
                    firstname=r["firstname"],
                    lastname=r["lastname"],
                )
                for _, r in g.iterrows()
            ],
            include_groups=False,
        )
        .to_dict()
    )

    pub_units_by_id = (
        pub_author[["id_pub", "cf", "unit_name", "unit_type", "cf_level_2", "cf_level_3", "acronym_level_2", "acronym_level_3"]]
        .drop_duplicates(subset=["id_pub", "cf"])
        .dropna(subset=["cf"])
        .groupby("id_pub")
        .apply(
            lambda g: [
                PublicationUnit(
                    id=f"unit:{int(r['cf'])}",
                    name=r["unit_name"] if pd.notna(r.get("unit_name")) else None,
                    cf=str(int(r["cf"])),
                    unit_name=r["unit_name"] if pd.notna(r.get("unit_name")) else None,
                    unit_type=r["unit_type"] if pd.notna(r.get("unit_type")) else None,
                    cf_level_2=str(int(r["cf_level_2"])) if pd.notna(r.get("cf_level_2")) else None,
                    cf_level_3=str(int(r["cf_level_3"])) if pd.notna(r.get("cf_level_3")) else None,
                    acronym_level_2=r["acronym_level_2"] if pd.notna(r.get("acronym_level_2")) else None,
                    acronym_level_3=r["acronym_level_3"] if pd.notna(r.get("acronym_level_3")) else None,
                )
                for _, r in g.iterrows()
            ],
            include_groups=False,
        )
        .to_dict()
    )

    def build_text(row, authors):
        parts = []
        if pd.notna(row["title"]):
            parts.append(str(row["title"]))
        if pd.notna(row["abstract"]) and str(row["abstract"]).strip():
            parts.append(str(row["abstract"]))
        if authors:
            parts.append("Authors: " + ", ".join(a.name for a in authors))
        return ". ".join(parts)

    records = []
    for _, row in publications.iterrows():
        pub_id = row["publication_id"]
        authors = pub_authors_by_id.get(pub_id, [])
        units = pub_units_by_id.get(pub_id, [])
        records.append(Publication(
            id=f"publication:{pub_id}",
            name=row["title"] if pd.notna(row["title"]) else None,
            text=build_text(row, authors),
            url=row["infoscience_url"] if pd.notna(row["infoscience_url"]) else (row["openalex_url"] if pd.notna(row["openalex_url"]) else None),
            publication_id=str(pub_id),
            title=row["title"] if pd.notna(row["title"]) else None,
            year=int(row["year"]) if pd.notna(row["year"]) else None,
            doi=row["doi"] if pd.notna(row["doi"]) else None,
            infoscience_url=row["infoscience_url"] if pd.notna(row["infoscience_url"]) else None,
            openalex_url=row["openalex_url"] if pd.notna(row["openalex_url"]) else None,
            abstract=row["abstract"] if pd.notna(row["abstract"]) else None,
            authors=authors,
            units=units,
        ))

    return records


def load_professors(data: dict) -> list[Professor]:
    professors = data["professors"]
    publications = data["publications"]
    sciper_to_pub_ids = data["sciper_to_pub_ids"]
    sciper_to_units = data["sciper_to_units"]

    pub_by_id = publications.set_index("id_pub")

    records = []
    for _, prof in professors.iterrows():
        sciper = int(prof["sciper"])

        units = [
            ProfessorUnit(
                id=f"unit:{int(r['cf'])}",
                name=r["unit_name"] if pd.notna(r.get("unit_name")) else None,
                cf=str(int(r["cf"])),
                unit_name=r["unit_name"] if pd.notna(r.get("unit_name")) else None,
                unit_type=r["unit_type"] if pd.notna(r.get("unit_type")) else None,
                acronym_level_2=r["acronym_level_2"] if pd.notna(r.get("acronym_level_2")) else None,
                acronym_level_3=r["acronym_level_3"] if pd.notna(r.get("acronym_level_3")) else None,
                role=r["role"] if pd.notna(r.get("role")) else None,
            )
            for r in sciper_to_units.get(sciper, [])
        ]

        valid_pub_ids = [i for i in sciper_to_pub_ids.get(sciper, []) if i in pub_by_id.index]
        prof_publications = []
        pub_texts = []
        if valid_pub_ids:
            for pub_id, pub_row in pub_by_id.loc[valid_pub_ids].sort_values("year_issued", ascending=False).iterrows():
                prof_publications.append(ProfessorPublication(
                    id=f"publication:{pub_id}",
                    name=str(pub_row["title"]) if pd.notna(pub_row["title"]) else None,
                    publication_id=str(pub_id),
                    title=str(pub_row["title"]) if pd.notna(pub_row["title"]) else None,
                    year=int(pub_row["year_issued"]) if pd.notna(pub_row["year_issued"]) else None,
                    doi=pub_row["doi"] if pd.notna(pub_row.get("doi")) else None,
                ))
                if len(pub_texts) < 10:
                    p = []
                    if pd.notna(pub_row["title"]):
                        p.append(str(pub_row["title"]))
                    if pd.notna(pub_row.get("abstract")) and str(pub_row.get("abstract", "")).strip():
                        p.append(str(pub_row["abstract"]))
                    if p:
                        pub_texts.append(". ".join(p))

        name = f"{prof['firstname']} {prof['lastname']}"
        units_str = ", ".join(u.name for u in units if u.name)
        text_parts = [f"Professor {name}"]
        if units_str:
            text_parts.append(f"Units: {units_str}")
        if pub_texts:
            text_parts.append("Publications: " + " | ".join(pub_texts))
        text = "\n".join(text_parts)

        records.append(Professor(
            id=f"professor:{sciper}",
            name=name,
            text=text,
            url=f"mailto:{prof['email']}" if pd.notna(prof["email"]) else None,
            sciper=str(sciper),
            email=prof["email"] if pd.notna(prof["email"]) else None,
            firstname=prof["firstname"],
            lastname=prof["lastname"],
            class_acc=str(prof["class_acc"]) if pd.notna(prof["class_acc"]) else None,
            creation_date=str(prof["creation_date"]) if pd.notna(prof["creation_date"]) else None,
            units=units,
            publications=prof_publications,
        ))

    return records


def load_units(data: dict) -> list[Unit]:
    units = data["units"]
    publications = data["publications"]
    prof_unit_merged = data["prof_unit_merged"]
    sciper_to_pub_ids = data["sciper_to_pub_ids"]
    professors = data["professors"].set_index("sciper")

    pub_by_id = publications.set_index("id_pub")

    unit_to_profs = (
        prof_unit_merged
        .groupby("cf")
        .apply(lambda g: g[["sciper", "role"]].to_dict("records"), include_groups=False)
        .to_dict()
    )

    records = []
    for _, unit in units.iterrows():
        cf = int(unit["cf"])

        professors_list = []
        all_pub_ids = set()
        for pr in unit_to_profs.get(cf, []):
            sciper = int(pr["sciper"])
            name = firstname = lastname = None
            if sciper in professors.index:
                p = professors.loc[sciper]
                firstname, lastname = p["firstname"], p["lastname"]
                name = f"{firstname} {lastname}"
            professors_list.append(UnitProfessor(
                id=f"professor:{sciper}",
                name=name,
                sciper=str(sciper),
                firstname=firstname,
                lastname=lastname,
                role=pr["role"],
            ))
            all_pub_ids.update(sciper_to_pub_ids.get(sciper, []))

        valid_pub_ids = [i for i in all_pub_ids if i in pub_by_id.index]
        unit_publications = []
        pub_texts = []
        if valid_pub_ids:
            for pub_id, pub_row in pub_by_id.loc[valid_pub_ids].sort_values("year_issued", ascending=False).iterrows():
                unit_publications.append(UnitPublication(
                    id=f"publication:{pub_id}",
                    name=str(pub_row["title"]) if pd.notna(pub_row["title"]) else None,
                    publication_id=str(pub_id),
                    title=str(pub_row["title"]) if pd.notna(pub_row["title"]) else None,
                    year=int(pub_row["year_issued"]) if pd.notna(pub_row["year_issued"]) else None,
                    doi=pub_row["doi"] if pd.notna(pub_row.get("doi")) else None,
                ))
                if len(pub_texts) < 10:
                    p = []
                    if pd.notna(pub_row["title"]):
                        p.append(str(pub_row["title"]))
                    if pd.notna(pub_row.get("abstract")) and str(pub_row.get("abstract", "")).strip():
                        p.append(str(pub_row["abstract"]))
                    if p:
                        pub_texts.append(". ".join(p))

        unit_name_str = unit["unit_name"] if pd.notna(unit["unit_name"]) else None
        text_parts = [unit_name_str] if unit_name_str else []
        if pub_texts:
            text_parts.append("Publications: " + " | ".join(pub_texts))
        unit_text = "\n".join(text_parts) if text_parts else None

        records.append(Unit(
            id=f"unit:{cf}",
            name=unit_name_str,
            text=unit_text,
            cf=str(cf),
            unit_name=unit_name_str,
            unit_type=unit["unit_type"] if pd.notna(unit["unit_type"]) else None,
            cf_level_2=str(int(unit["cf_level_2"])) if pd.notna(unit["cf_level_2"]) else None,
            cf_level_3=str(int(unit["cf_level_3"])) if pd.notna(unit["cf_level_3"]) else None,
            acronym_level_2=str(unit["acronym_level_2"]) if pd.notna(unit["acronym_level_2"]) else None,
            acronym_level_3=str(unit["acronym_level_3"]) if pd.notna(unit["acronym_level_3"]) else None,
            professors=professors_list,
            publications=unit_publications,
        ))

    return records


def load_all() -> tuple[list[Publication], list[Professor], list[Unit]]:
    data = _load_csvs()
    publications = load_publications(data)
    professors = load_professors(data)
    units = load_units(data)
    return publications, professors, units


if __name__ == "__main__":
    publications, professors, units = load_all()
    print(f"Loaded {len(publications)} publications, {len(professors)} professors, {len(units)} units")
    if publications:
        print(f"Sample publication:")
        print(publications[0].model_dump())
    if professors:
        print(f"Sample professor:")
        print(professors[0].model_dump())
    if units:
        print(f"Sample unit:")
        print(units[0].model_dump())
