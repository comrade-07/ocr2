from src.transform.field_extractor import repair_utf8_mojibake


def test_repairs_windows_1252_misdecoded_utf8_text():
    assert (
        repair_utf8_mojibake("METALLUM COMÃ‰RCIO DE SUCATAS - EIRELI - 1233")
        == "METALLUM COMÉRCIO DE SUCATAS - EIRELI - 1233"
    )


def test_repairs_multiple_layers_of_misdecoded_utf8_text():
    assert repair_utf8_mojibake("COMÃƒâ€°RCIO") == "COMÉRCIO"


def test_preserves_correct_unicode_text():
    assert repair_utf8_mojibake("METALLUM COMÉRCIO – SÃO PAULO") == "METALLUM COMÉRCIO – SÃO PAULO"


def test_preserves_non_text_values():
    assert repair_utf8_mojibake(123.45) == 123.45
