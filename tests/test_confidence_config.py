import pytest

from src.review.confidence_config import confidence_config_path, load_confidence_config


def test_load_confidence_config_reads_editable_scope2_yaml():
    config = load_confidence_config("config/confidence/scope2_confidence.yaml")

    assert config.document_confidence_threshold == 0.60
    assert config.critical_threshold == 0.80
    assert config.optional_threshold == 0.60
    assert config.noncritical_threshold == 0.30
    assert config.blank_high_confidence_threshold == 0.90
    assert "account_number" in config.critical_fields
    assert "legal_entity" in config.optional_fields
    assert "invoice_date" in config.noncritical_fields
    assert config.review_statuses["review_required"] == "REVIEW_REQUIRED"
    assert config.field_statuses["blocked"] == "BLOCKED"
    assert config.field_tags["low_confidence"] == "LOW_CONFIDENCE"
    assert config.field_tags["blank_high_confidence"] == "BLANK_HIGH_CONFIDENCE"
    assert config.mapping_checks == {"enabled": False, "fields": []}


def test_confidence_config_path_uses_invoice_type():
    path = confidence_config_path("config", "scope2")

    assert path.as_posix() == "config/confidence/scope2_confidence.yaml"


def test_load_confidence_config_requires_thresholds(tmp_path):
    config_file = tmp_path / "confidence.yaml"
    config_file.write_text(
        "\n".join([
            "thresholds:",
            "  critical: 0.80",
            "  optional: 0.60",
            "critical_fields:",
            "  - supplier",
            "",
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="noncritical"):
        load_confidence_config(config_file)
