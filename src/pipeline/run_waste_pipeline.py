import argparse
from pathlib import Path

from src.pipeline.run_pipeline import run_pipeline
from src.pipeline.run_review_pipeline import run_review_pipeline


WASTE_CATEGORY = "waste"


def run_waste_pipeline(
    input_dir: str | Path | None = None,
    config_dir: str | Path = "config",
) -> Path:
    return run_pipeline(
        input_dir=input_dir,
        config_dir=config_dir,
        invoice_type=WASTE_CATEGORY,
    )


def rerun_waste_review(
    bronze_file: str | Path | None = None,
    config_dir: str | Path = "config",
) -> dict[str, Path]:
    return run_review_pipeline(
        config_dir=config_dir,
        bronze_file=bronze_file,
        invoice_type=WASTE_CATEGORY,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Waste bronze extraction and silver review checkpoints only.",
    )
    parser.add_argument("--input", dest="input_dir", default=None, help="Folder containing Waste raw JSON files")
    parser.add_argument("--config", dest="config_dir", default="config", help="Configuration folder")
    args = parser.parse_args()

    bronze_output = run_waste_pipeline(input_dir=args.input_dir, config_dir=args.config_dir)
    print(f"Waste bronze and review checkpoints completed. Bronze CSV output: {bronze_output}")


if __name__ == "__main__":
    main()
