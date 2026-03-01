import csv
import io
import logging
import re
from datetime import datetime

from .models import (
    AssetCreate,
    AssetEnsureRequest,
    CsvImportCommitResponse,
    CsvImportPreviewResponse,
    CsvImportPreviewRow,
    TransactionCreate,
)
from .repository import PortfolioRepository

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["operazione", "isin", "segno", "quantita", "prezzo"]
SEGNO_MAP = {"A": "buy", "V": "sell"}
FEE_COLUMNS = [
    "commissioni fondi sw/ingr/uscita",
    "commissioni fondi banca corrispondente",
    "spese fondi sgr",
    "commissioni amministrato",
]


def _parse_italian_number(s: str) -> float | None:
    """Parse Italian formatted number: 1.159,77 → 1159.77"""
    s = s.strip()
    if not s:
        return None
    # Remove thousands separators (dots) and replace decimal comma with dot
    s = s.replace(".", "").replace(",", ".")
    return float(s)


class CsvImportService:
    def __init__(self, repo: PortfolioRepository) -> None:
        self.repo = repo

    def parse_and_validate(
        self, portfolio_id: int, user_id: str, file_content: str, filename: str | None = None
    ) -> CsvImportPreviewResponse:
        reader = csv.DictReader(io.StringIO(file_content))
        if reader.fieldnames is None:
            raise ValueError("File CSV vuoto o intestazioni mancanti")

        normalized_fields = [f.strip().lower() for f in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS if c not in normalized_fields]
        if missing:
            raise ValueError(f"Colonne obbligatorie mancanti: {', '.join(missing)}")

        rows: list[CsvImportPreviewRow] = []
        valid_count = 0
        error_count = 0

        for idx, raw_row in enumerate(reader, start=1):
            row_data = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
            errors: list[str] = []

            # Parse operazione (date dd/mm/yyyy)
            operazione_str = row_data.get("operazione", "")
            parsed_trade_at: str | None = None
            if not operazione_str:
                errors.append("operazione obbligatorio")
            else:
                try:
                    for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                        try:
                            dt = datetime.strptime(operazione_str, fmt)
                            parsed_trade_at = dt.isoformat()
                            break
                        except ValueError:
                            continue
                    if parsed_trade_at is None:
                        errors.append(f"Formato data non riconosciuto: {operazione_str}")
                except Exception:
                    errors.append(f"Formato data non valido: {operazione_str}")

            # Parse ISIN
            isin = row_data.get("isin", "").strip().upper()
            if not isin:
                errors.append("isin obbligatorio")

            # Parse segno → side
            segno = row_data.get("segno", "").strip().upper()
            side = SEGNO_MAP.get(segno)
            if side is None:
                errors.append(f"segno non valido: '{segno}'. Valori ammessi: A (acquisto), V (vendita)")

            # Parse quantita (Italian number format)
            quantity: float | None = None
            quantita_str = row_data.get("quantita", "")
            if not quantita_str:
                errors.append("quantita obbligatorio")
            else:
                try:
                    quantity = _parse_italian_number(quantita_str)
                    if quantity is not None and quantity <= 0:
                        errors.append("quantita deve essere > 0")
                except ValueError:
                    errors.append(f"quantita non numerico: {quantita_str}")

            # Parse prezzo (Italian number format)
            price: float | None = None
            prezzo_str = row_data.get("prezzo", "")
            if not prezzo_str:
                errors.append("prezzo obbligatorio")
            else:
                try:
                    price = _parse_italian_number(prezzo_str)
                    if price is not None and price < 0:
                        errors.append("prezzo deve essere >= 0")
                except ValueError:
                    errors.append(f"prezzo non numerico: {prezzo_str}")

            # Parse divisa → trade_currency
            trade_currency = row_data.get("divisa", "").strip().upper() or None

            # Parse cambio (exchange rate) - stored in notes for reference
            cambio: float | None = None
            cambio_str = row_data.get("cambio", "")
            if cambio_str:
                try:
                    cambio = _parse_italian_number(cambio_str)
                except ValueError:
                    pass  # cambio is optional, skip if unparseable

            # Sum all fee columns
            fees: float = 0.0
            for fee_col in FEE_COLUMNS:
                fee_str = row_data.get(fee_col, "")
                if fee_str:
                    try:
                        fee_val = _parse_italian_number(fee_str)
                        if fee_val is not None:
                            fees += abs(fee_val)
                    except ValueError:
                        errors.append(f"commissione non numerica ({fee_col}): {fee_str}")
            fees_result = fees if fees > 0 else None

            # Build notes from descrizione + titolo + cambio
            titolo = row_data.get("titolo", "").strip() or None
            descrizione = row_data.get("descrizione", "").strip() or None
            notes_parts: list[str] = []
            if descrizione:
                notes_parts.append(descrizione)
            if titolo:
                notes_parts.append(f"Titolo: {titolo}")
            if cambio is not None and cambio != 1.0:
                notes_parts.append(f"Cambio: {cambio}")
            notes = "; ".join(notes_parts) if notes_parts else None

            # Try to resolve asset by ISIN
            asset_id: int | None = None
            asset_name: str | None = None
            if isin and not errors:
                try:
                    matches = self.repo.search_assets(isin)
                    # Match by ISIN field
                    exact = next(
                        (m for m in matches if str(m.get("isin", "")).upper() == isin),
                        None,
                    )
                    if exact:
                        asset_id = int(exact["id"])
                        asset_name = exact.get("name")
                except Exception:
                    pass

            is_valid = len(errors) == 0
            if is_valid:
                valid_count += 1
            else:
                error_count += 1

            rows.append(CsvImportPreviewRow(
                row_number=idx,
                valid=is_valid,
                errors=errors,
                trade_at=parsed_trade_at,
                isin=isin or None,
                titolo=titolo,
                side=side,
                quantity=quantity,
                price=price,
                fees=fees_result,
                taxes=None,
                trade_currency=trade_currency,
                notes=notes,
                asset_id=asset_id,
                asset_name=asset_name,
            ))

        # Save batch to DB
        preview_data = [r.model_dump() for r in rows]
        batch_id = self.repo.create_csv_import_batch(
            portfolio_id=portfolio_id,
            user_id=user_id,
            filename=filename,
            total_rows=len(rows),
            valid_rows=valid_count,
            error_rows=error_count,
            preview_data=preview_data,
        )

        return CsvImportPreviewResponse(
            batch_id=batch_id,
            filename=filename,
            total_rows=len(rows),
            valid_rows=valid_count,
            error_rows=error_count,
            rows=rows,
        )

    def commit_batch(self, batch_id: int, user_id: str) -> CsvImportCommitResponse:
        batch = self.repo.get_csv_import_batch(batch_id, user_id)
        if batch is None:
            raise ValueError("Batch CSV non trovato")
        if batch["status"] != "pending":
            raise ValueError(f"Batch non in stato pending (stato attuale: {batch['status']})")

        preview_data = batch["preview_data"]
        if not isinstance(preview_data, list):
            raise ValueError("Dati preview non validi")

        portfolio_id = int(batch["portfolio_id"])
        committed = 0
        errors: list[str] = []

        for row_data in preview_data:
            if not row_data.get("valid", False):
                continue

            try:
                # Resolve asset by ISIN
                isin = str(row_data.get("isin", "")).strip().upper()
                asset_id = row_data.get("asset_id")
                side = str(row_data.get("side", "")).lower()

                if asset_id is None and isin:
                    # Try to find asset by ISIN
                    matches = self.repo.search_assets(isin)
                    exact = next(
                        (m for m in matches if str(m.get("isin", "")).upper() == isin),
                        None,
                    )
                    if exact:
                        asset_id = int(exact["id"])
                    else:
                        # Auto-create asset with ISIN
                        base_ccy = self.repo.get_portfolio_base_currency(portfolio_id)
                        titolo = row_data.get("titolo") or isin
                        try:
                            asset = self.repo.create_asset(AssetCreate(
                                symbol=isin,
                                name=titolo,
                                asset_type="stock",
                                quote_currency=base_ccy,
                                isin=isin,
                            ))
                            asset_id = asset.id
                        except ValueError:
                            # Asset may have been created by a previous row
                            matches = self.repo.search_assets(isin)
                            exact = next(
                                (m for m in matches if str(m.get("isin", "")).upper() == isin),
                                None,
                            )
                            if exact:
                                asset_id = int(exact["id"])
                            else:
                                errors.append(f"Riga {row_data.get('row_number')}: impossibile risolvere asset ISIN {isin}")
                                continue

                trade_at_str = row_data.get("trade_at", "")
                trade_at = datetime.fromisoformat(trade_at_str)
                trade_currency = row_data.get("trade_currency") or self.repo.get_portfolio_base_currency(portfolio_id)

                self.repo.create_transaction(
                    TransactionCreate(
                        portfolio_id=portfolio_id,
                        asset_id=asset_id,
                        side=side,
                        trade_at=trade_at,
                        quantity=float(row_data["quantity"]),
                        price=float(row_data["price"]),
                        fees=float(row_data.get("fees") or 0),
                        taxes=float(row_data.get("taxes") or 0),
                        trade_currency=trade_currency,
                        notes=row_data.get("notes"),
                    ),
                    user_id,
                )
                committed += 1
            except Exception as exc:
                errors.append(f"Riga {row_data.get('row_number')}: {exc}")

        self.repo.commit_csv_import_batch(batch_id, user_id)

        return CsvImportCommitResponse(
            batch_id=batch_id,
            committed_transactions=committed,
            errors=errors,
        )
