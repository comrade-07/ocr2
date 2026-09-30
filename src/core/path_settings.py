from pathlib import Path


def _category_path(paths: dict, base_key: str, category_key: str | None) -> str | None:
    if category_key:
        category_value = paths.get(f"{base_key}_{category_key}")
        if category_value is not None:
            return category_value
    return paths.get(base_key)


def bronze_output_dir(settings: dict, category_key: str | None = None) -> Path:
    paths = settings.get("paths", {})
    return Path(_category_path(paths, "bronze_output", category_key) or paths.get("csv_output", "data/bronze"))


def silver_excel_output_dir(settings: dict, category_key: str | None = None) -> Path:
    paths = settings.get("paths", {})
    return Path(
        _category_path(paths, "silver_excel_output", category_key)
        or paths.get("silver_output", "data/silver")
    )


def checkpoint_output_dir(settings: dict, category_key: str | None = None) -> Path:
    paths = settings.get("paths", {})
    return Path(
        _category_path(paths, "review_checkpoint_output", category_key)
        or paths.get("checkpoint_output", "data/output/checkpoints")
    )


def category_checkpoint_dirs_enabled(settings: dict) -> bool:
    value = settings.get("paths", {}).get("category_checkpoint_dirs", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def category_checkpoint_output_dir(settings: dict, category_key: str) -> Path:
    paths = settings.get("paths", {})
    category_path_key = f"review_checkpoint_output_{category_key}"
    if category_path_key in paths:
        return checkpoint_output_dir(settings, category_key)

    checkpoint_dir = checkpoint_output_dir(settings)
    if category_checkpoint_dirs_enabled(settings):
        return checkpoint_dir / category_key
    return checkpoint_dir


def manual_data_entry_upload_dir(settings: dict, category_key: str | None = None) -> Path:
    paths = settings.get("paths", {})
    return Path(_category_path(paths, "manual_data_entry_uploads", category_key) or "data/manual_uploads")


def gold_output_dir(settings: dict, category_key: str | None = None) -> Path:
    paths = settings.get("paths", {})
    return Path(_category_path(paths, "gold_output", category_key) or "data/gold")
