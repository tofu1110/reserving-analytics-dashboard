"""Chain ladder reserving by line of business.

Reads the industry triangles built by the SQL pipeline, applies the
volume-weighted chain ladder to cumulative paid and reported incurred losses,
reconciles the paid factors against the SQL calculation, and writes the
results to data/processed/ for Power BI.

No tail factor is applied: development is assumed complete after lag 10.
"""

from pathlib import Path

import chainladder as cl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"

MEASURES = {"cum_paid": "Paid", "reported_incurred": "Reported incurred"}
N_LAGS = 10
TOLERANCE = 1e-9


def load_triangle() -> cl.Triangle:
    df = pd.read_csv(DATA_DIR / "fact_triangle.csv")
    return cl.Triangle(
        df,
        origin="accident_year",
        development="calendar_year",
        columns=list(MEASURES),
        index=["lob"],
        cumulative=True,
    )


def tidy(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Turn a chainladder frame into a long table: lob, accident_year, ..., measure, value."""
    df = frame.reset_index()
    df["accident_year"] = df["origin"].dt.year
    id_cols = [c for c in df.columns if c in ("lob", "accident_year", "development")]
    long = df.melt(id_vars=id_cols, value_vars=list(MEASURES),
                   var_name="measure", value_name=value_name)
    long["measure"] = long["measure"].map(MEASURES)
    return long


def factor_table(dev: cl.Development) -> pd.DataFrame:
    ata = tidy(dev.ldf_.to_frame(keepdims=True), "ata_factor")
    cdf = tidy(dev.cdf_.to_frame(keepdims=True), "cdf_to_ultimate")
    factors = ata.merge(cdf, on=["lob", "accident_year", "development", "measure"])
    factors["from_lag"] = factors["development"] // 12
    factors["to_lag"] = factors["from_lag"] + 1
    return (factors[["lob", "measure", "from_lag", "to_lag", "ata_factor", "cdf_to_ultimate"]]
            .sort_values(["lob", "measure", "from_lag"])
            .reset_index(drop=True))


def results_table(tri: cl.Triangle, model: cl.Chainladder) -> pd.DataFrame:
    latest = tidy(tri.latest_diagonal.to_frame(keepdims=True), "latest")
    ultimate = tidy(model.ultimate_.to_frame(keepdims=True), "ultimate")
    keys = ["lob", "accident_year", "measure"]
    results = latest[keys + ["latest"]].merge(ultimate[keys + ["ultimate"]], on=keys)
    results["reserve"] = results["ultimate"] - results["latest"]
    results["dev_lag_latest"] = 1997 - results["accident_year"] + 1
    return results.sort_values(keys).reset_index(drop=True)


def full_triangle_table(tri: cl.Triangle, model: cl.Chainladder) -> pd.DataFrame:
    """Observed upper triangle plus chain ladder projections, lags 1-10."""
    full = tidy(model.full_triangle_.to_frame(keepdims=True), "value")
    full["dev_lag"] = full["development"] // 12
    full = full[full["dev_lag"].between(1, N_LAGS)].copy()
    full["calendar_year"] = full["accident_year"] + full["dev_lag"] - 1
    full["is_projected"] = full["calendar_year"] > 1997
    return (full[["lob", "measure", "accident_year", "dev_lag", "calendar_year",
                  "value", "is_projected"]]
            .sort_values(["lob", "measure", "accident_year", "dev_lag"])
            .reset_index(drop=True))


def reconcile_with_sql(factors: pd.DataFrame) -> pd.DataFrame:
    """Check the Python paid factors against the SQL window-function factors."""
    sql = pd.read_csv(DATA_DIR / "ata_paid_sql.csv")
    py = factors.loc[factors["measure"] == "Paid", ["lob", "from_lag", "ata_factor"]]
    recon = py.merge(sql, on=["lob", "from_lag"], suffixes=("_python", "_sql"))
    recon["abs_diff"] = (recon["ata_factor_python"] - recon["ata_factor_sql"]).abs()
    if len(recon) != len(sql) or recon["abs_diff"].max() > TOLERANCE:
        raise ValueError("Paid age-to-age factors do not reconcile between Python and SQL")
    return recon


def main() -> None:
    tri = load_triangle()
    dev = cl.Development(average="volume").fit(tri)
    model = cl.Chainladder().fit(dev.transform(tri))

    factors = factor_table(dev)
    results = results_table(tri, model)
    full = full_triangle_table(tri, model)
    recon = reconcile_with_sql(factors)

    factors.to_csv(DATA_DIR / "cl_factors.csv", index=False)
    results.to_csv(DATA_DIR / "cl_results.csv", index=False)
    full.to_csv(DATA_DIR / "cl_full_triangle.csv", index=False)
    recon.to_csv(DATA_DIR / "reconciliation_ata_paid.csv", index=False)

    print(f"Reconciliation passed: {len(recon)} paid factors match SQL "
          f"(max difference {recon['abs_diff'].max():.1e})\n")

    summary = (results.groupby(["lob", "measure"])[["latest", "ultimate", "reserve"]]
               .sum().round(0).astype(int))
    print("Chain ladder results by line of business:")
    print(summary.to_string())


if __name__ == "__main__":
    main()