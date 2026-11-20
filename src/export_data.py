"""Export the CAS Loss Reserving Database sample to flat CSV files.

Source: the `clrd` sample shipped with the chainladder package
(US Schedule P data, accident years 1988-1997, valued at 1997-12-31).

Outputs
-------
data/raw/clrd_long.csv
    One row per company x line of business x accident year x development lag.
data/processed/dim_lob.csv
    Line-of-business lookup table.
"""

from pathlib import Path

import chainladder as cl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

LOB_NAMES = {
    "comauto": "Commercial Auto Liability",
    "medmal": "Medical Malpractice",
    "othliab": "Other Liability",
    "ppauto": "Private Passenger Auto Liability",
    "prodliab": "Products Liability",
    "wkcomp": "Workers' Compensation",
}

MEASURES = {
    "CumPaidLoss": "cum_paid",
    "IncurLoss": "incurred",
    "BulkLoss": "bulk_ibnr",
    "EarnedPremNet": "earned_premium_net",
}


def load_long() -> pd.DataFrame:
    """Load clrd and reshape the triangles into a long table."""
    tri = cl.load_sample("clrd")[list(MEASURES)]
    df = tri.to_frame(keepdims=True).reset_index()

    df = df.rename(columns={"GRNAME": "company", "LOB": "lob", **MEASURES})
    df["accident_year"] = df["origin"].dt.year
    df["dev_lag"] = df["development"] // 12  # 12, 24, ... months -> 1, 2, ... years
    df["calendar_year"] = df["accident_year"] + df["dev_lag"] - 1

    # chainladder stores triangles sparsely, so reported zeros come back as NaN.
    df[list(MEASURES.values())] = df[list(MEASURES.values())].fillna(0)

    columns = ["company", "lob", "accident_year", "dev_lag", "calendar_year",
               *MEASURES.values()]
    return (df[columns]
            .sort_values(["company", "lob", "accident_year", "dev_lag"])
            .reset_index(drop=True))


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    claims = load_long()
    claims.to_csv(RAW_DIR / "clrd_long.csv", index=False)

    dim_lob = pd.DataFrame(
        {"lob": list(LOB_NAMES), "lob_name": list(LOB_NAMES.values())}
    )
    dim_lob.to_csv(PROCESSED_DIR / "dim_lob.csv", index=False)

    # Quick summary so you can check the export worked.
    print(f"Rows exported:        {len(claims):,}")
    print(f"Companies:            {claims['company'].nunique()}")
    print(f"Company x LOB pairs:  {claims[['company', 'lob']].drop_duplicates().shape[0]}")
    print(f"Accident years:       {claims['accident_year'].min()}-{claims['accident_year'].max()}")
    print("\nRows by line of business:")
    print(claims["lob"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()