import io

import openpyxl

from app.services.csv_service import BANK_EXPORT_COLUMNS, _prepare_fineco_csv_content, _read_xlsx_rows


def test_prepare_fineco_csv_content_keeps_embedded_header_row():
    header = ";".join(
        [
            "Operazione",
            "Data valuta",
            "Descrizione",
            "Titolo",
            "Isin",
            "Segno",
            "Quantita",
            "Divisa",
            "Prezzo",
            "Cambio",
            "Controvalore",
            "Commissioni Fondi Sw/Ingr/Uscita",
            "Commissioni Fondi Banca Corrispondente",
            "Spese Fondi Sgr",
            "Commissioni amministrato",
        ]
    )
    content = "\n".join(
        [
            "estratto conto fineco",
            "cliente abc",
            header,
            "01/03/2026;04/03/2026;ACQUISTO;ETF TEST;IE00TEST0001;A;10;EUR;100,00;1;1000,00;0;0;0;2,95",
        ]
    )

    normalized = _prepare_fineco_csv_content(content, skip_rows=7)

    assert normalized.splitlines()[0].lower().startswith("operazione;data valuta;descrizione")


def test_prepare_fineco_csv_content_adds_header_for_headerless_export():
    content = "\n".join(
        [
            "metadata 1",
            "metadata 2",
            "metadata 3",
            "metadata 4",
            "metadata 5",
            "metadata 6",
            "metadata 7",
            "01/03/2026;04/03/2026;ACQUISTO;ETF TEST;IE00TEST0001;A;10;EUR;100,00;1;1000,00;0;0;0;2,95",
        ]
    )

    normalized = _prepare_fineco_csv_content(content, skip_rows=7)

    assert normalized.splitlines()[0] == ";".join(BANK_EXPORT_COLUMNS)


def test_read_xlsx_rows_detects_fineco_header_without_fixed_skip():
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["report fineco"])
    worksheet.append([""])
    worksheet.append(
        [
            "Operazione",
            "Data valuta",
            "Descrizione",
            "Titolo",
            "Isin",
            "Segno",
            "Quantita",
            "Divisa",
            "Prezzo",
            "Cambio",
            "Controvalore",
            "Commissioni Fondi Sw/Ingr/Uscita",
            "Commissioni Fondi Banca Corrispondente",
            "Spese Fondi Sgr",
            "Commissioni amministrato",
        ]
    )
    worksheet.append(
        [
            "01/03/2026",
            "04/03/2026",
            "ACQUISTO",
            "ETF TEST",
            "IE00TEST0001",
            "A",
            "10",
            "EUR",
            "100,00",
            "1",
            "1000,00",
            "0",
            "0",
            "0",
            "2,95",
        ]
    )

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    rows = _read_xlsx_rows(buffer.getvalue(), skip_rows=7, broker="fineco")

    assert len(rows) == 1
    assert rows[0]["Operazione"] == "01/03/2026"
