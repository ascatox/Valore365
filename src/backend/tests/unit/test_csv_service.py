import io

import openpyxl

from app.services.csv_service import (
    BANK_EXPORT_COLUMNS,
    CsvImportService,
    _parse_italian_number,
    _prepare_fineco_csv_content,
    _read_xlsx_rows,
)


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


REDUCED_FINECO_HEADER = [
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
    "Commissioni amministrato",
]


def test_read_xlsx_rows_detects_fineco_header_without_fund_fee_columns():
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["Dossier n.: 00000000"])
    worksheet.append(["Intestazione Dossier: MARIO ROSSI"])
    worksheet.append([""])
    worksheet.append(["RISULTATO RICERCA MOVIMENTI TITOLI"])
    worksheet.append([""])
    worksheet.append(REDUCED_FINECO_HEADER)
    worksheet.append([])
    worksheet.append(
        ["13/10/2026", "15/10/2026", "Compravendita titoli", "ISHS EUR CO 1-5 EUR", "IE00B4L60045", "A", 375, "EUR", 105.23067, 1, 39461.5, 19]
    )
    worksheet.append(
        ["13/10/2026", "15/10/2026", "Compravendita titoli", "VAN FTSE ALL USD-AC", "IE00BK5BQT80", "V", 1, "EUR", 153.89, 1, 153.89, 19]
    )

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    rows = _read_xlsx_rows(buffer.getvalue(), skip_rows=7, broker="fineco")

    assert len(rows) == 2
    assert rows[0]["Isin"] == "IE00B4L60045"
    assert rows[1]["Isin"] == "IE00BK5BQT80"


def test_read_xlsx_rows_keeps_three_decimal_numeric_cells_as_decimals():
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(REDUCED_FINECO_HEADER)
    worksheet.append(
        ["01/03/2026", "04/03/2026", "Compravendita titoli", "ETF TEST", "IE00TEST0001", "A", 10, "EUR", 105.123, 1, 1051.23, 2.5]
    )

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    rows = _read_xlsx_rows(buffer.getvalue(), broker="fineco")

    assert _parse_italian_number(rows[0]["Prezzo"]) == 105.123
    assert _parse_italian_number(rows[0]["Quantita"]) == 10
    assert _parse_italian_number(rows[0]["Controvalore"]) == 1051.23


def test_prepare_fineco_csv_content_detects_header_without_fund_fee_columns():
    content = "\n".join(
        [
            "Dossier n.: 00000000",
            "RISULTATO RICERCA MOVIMENTI TITOLI",
            ";".join(REDUCED_FINECO_HEADER),
            "13/10/2026;15/10/2026;Compravendita titoli;ETF;IE00B4L60045;A;375;EUR;105,23;1;39461,5;19",
        ]
    )

    normalized = _prepare_fineco_csv_content(content, skip_rows=7)

    assert normalized.splitlines()[0] == ";".join(REDUCED_FINECO_HEADER)
    assert len(normalized.splitlines()) == 2


class _FakeRepo:
    pass


def test_parse_public_portfolio_file_aggregates_fineco_rows_into_positions():
    service = CsvImportService(_FakeRepo())
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
            "05/03/2026;06/03/2026;ACQUISTO;ETF TEST;IE00TEST0001;A;5;EUR;100,00;1;500,00;0;0;0;2,95",
            "08/03/2026;09/03/2026;VENDITA;ETF TEST;IE00TEST0001;V;2;EUR;100,00;1;200,00;0;0;0;2,95",
        ]
    )

    response = service.parse_public_portfolio_file(
        file_content=content,
        filename="fineco.csv",
        broker="fineco",
    )

    assert response.total_rows == 3
    assert response.valid_rows == 3
    assert response.error_rows == 0
    assert len(response.positions) == 1
    assert response.positions[0].identifier == "IE00TEST0001"
    assert response.positions[0].value == 1300.0
    assert "IE00TEST0001 1300.00" in response.raw_text
