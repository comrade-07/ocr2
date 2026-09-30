from pathlib import Path

from src.core.path_settings import (
    bronze_output_dir,
    category_checkpoint_dirs_enabled,
    category_checkpoint_output_dir,
    gold_output_dir,
    manual_data_entry_upload_dir,
    silver_excel_output_dir,
)


def test_category_checkpoint_output_dir_uses_category_folder_when_enabled():
    settings = {
        "paths": {
            "review_checkpoint_output": "data/output/checkpoints",
            "category_checkpoint_dirs": True,
        }
    }

    assert category_checkpoint_dirs_enabled(settings) is True
    assert category_checkpoint_output_dir(settings, "scope2") == Path("data/output/checkpoints/scope2")


def test_category_checkpoint_output_dir_uses_category_folder_by_default():
    settings = {
        "paths": {
            "review_checkpoint_output": "data/output/checkpoints",
        }
    }

    assert category_checkpoint_dirs_enabled(settings) is True
    assert category_checkpoint_output_dir(settings, "scope2") == Path("data/output/checkpoints/scope2")


def test_category_checkpoint_output_dir_uses_base_folder_when_disabled():
    settings = {
        "paths": {
            "review_checkpoint_output": "data/output/checkpoints",
            "category_checkpoint_dirs": False,
        }
    }

    assert category_checkpoint_dirs_enabled(settings) is False
    assert category_checkpoint_output_dir(settings, "scope2") == Path("data/output/checkpoints")


def test_category_checkpoint_output_dir_accepts_string_false():
    settings = {
        "paths": {
            "review_checkpoint_output": "data/output/checkpoints",
            "category_checkpoint_dirs": "false",
        }
    }

    assert category_checkpoint_dirs_enabled(settings) is False
    assert category_checkpoint_output_dir(settings, "scope2") == Path("data/output/checkpoints")


def test_waste_specific_paths_are_isolated_from_scope2_paths():
    settings = {
        "paths": {
            "bronze_output": "data/bronze",
            "silver_excel_output": "data/silver",
            "review_checkpoint_output": "data/output/checkpoints",
            "manual_data_entry_uploads": "data/manual_uploads",
            "gold_output": "data/gold",
            "bronze_output_waste": "data/bronze/waste",
            "silver_excel_output_waste": "data/silver/waste",
            "review_checkpoint_output_waste": "data/output/checkpoints/waste",
            "manual_data_entry_uploads_waste": "data/manual_uploads/waste",
            "gold_output_waste": "data/gold/waste",
        }
    }

    assert bronze_output_dir(settings, "scope2") == Path("data/bronze")
    assert silver_excel_output_dir(settings, "scope2") == Path("data/silver")
    assert category_checkpoint_output_dir(settings, "scope2") == Path("data/output/checkpoints/scope2")
    assert manual_data_entry_upload_dir(settings, "scope2") == Path("data/manual_uploads")
    assert gold_output_dir(settings, "scope2") == Path("data/gold")

    assert bronze_output_dir(settings, "waste") == Path("data/bronze/waste")
    assert silver_excel_output_dir(settings, "waste") == Path("data/silver/waste")
    assert category_checkpoint_output_dir(settings, "waste") == Path("data/output/checkpoints/waste")
    assert manual_data_entry_upload_dir(settings, "waste") == Path("data/manual_uploads/waste")
    assert gold_output_dir(settings, "waste") == Path("data/gold/waste")
