import argparse
from src.pipeline.run_gold_pipeline import run_gold_pipeline
from src.pipeline.run_pipeline import run_pipeline
from src.pipeline.run_silver_pipeline import run_silver_pipeline
from src.review.categories import valid_category_keys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run invoice processing pipeline.")
    parser.add_argument("--input", dest="input_dir", default=None, help="Folder containing raw JSON files")
    parser.add_argument(
        "--category",
        choices=valid_category_keys(),
        default=None,
        help="ESG data category to process",
    )
    args = parser.parse_args()

    try:
        bronze_output = run_pipeline(input_dir=args.input_dir, invoice_type=args.category)
        silver_output = run_silver_pipeline(invoice_type=args.category)
        gold_output = run_gold_pipeline(invoice_type=args.category)
    except PermissionError as exc:
        raise SystemExit(str(exc)) from None
    print(f"Pipeline completed. Bronze CSV output: {bronze_output}")
    print(f"Pipeline completed. Silver reviewed, normalized, and curated outputs were built.")
    print(f"Pipeline completed. Silver normalized Excel output: {silver_output}")
    print(f"Pipeline completed. Gold template Excel output: {gold_output}")


if __name__ == "__main__":
    main()
