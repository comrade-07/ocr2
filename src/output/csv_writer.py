from pathlib import Path
import pandas as pd


def _remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.drop_duplicates().copy()


def write_csv(
    records: list[dict],
    output_dir: str | Path,
    filename: str,
    columns: list[str] | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename
    df = _remove_duplicates(pd.DataFrame(records, columns=columns))
    try:
        # Include the UTF-8 BOM so Excel detects the encoding correctly when a
        # CSV is opened directly, preserving accents and other Unicode text.
        df.to_csv(target, index=False, encoding="utf-8-sig")
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot write CSV output to {target}. "
            "Close the CSV if it is open in Excel or another app, then run the pipeline again."
        ) from exc
    return target
