import csv
import io
import logging
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

EXPECTED_COLUMNS = ["trade_at", "symbol", "side", "quantity", "price", "fees", "taxes", "trade_currency", "notes"]
VALID_SIDES = {"buy", "sell", "deposit", "withdrawal", "dividend", "fee", "interest"}


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
        missing = [c for c in ["trade_at", "symbol", "side", "quantity", "price"] if c not in normalized_fields]
        if missing:
            raise ValueError(f"Colonne obbligatorie mancanti: {', '.join(missing)}")

        rows: list[CsvImportPreviewRow] = []
        valid_count = 0
        error_count = 0

        for idx, raw_row in enumerate(reader, start=1):
            row_data = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
            errors: list[str] = []

            # Parse trade_at
            trade_at_str = row_data.get("trade_at", "")
            parsed_trade_at: str | None = None
            if not trade_at_str:
                errors.append("trade_at obbligatorio")
            else:
                try:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
                        try:
                            dt = datetime.strptime(trade_at_str, fmt)
                            parsed_trade_at = dt.isoformat()
                            break
                        except ValueError:
                            continue
                    if parsed_trade_at is None:
                        errors.append(f"Formato data non riconosciuto: {trade_at_str}")
                except Exception:
                    errors.append(f"Formato data non valido: {trade_at_str}")

            # Parse symbol
            symbol = row_data.get("symbol", "").strip().upper()
            if not symbol:
                errors.append("symbol obbligatorio")

            # Parse side
            side = row_data.get("side", "").strip().lower()
            if side not in VALID_SIDES:
                errors.append(f"side non valido: {side}. Valori ammessi: {', '.join(sorted(VALID_SIDES))}")

            # Parse quantity
            quantity: float | None = None
            quantity_str = row_data.get("quantity", "")
            if not quantity_str:
                errors.append("quantity obbligatorio")
            else:
                try:
                    quantity = float(quantity_str.replace(",", "."))
                    if quantity <= 0:
                        errors.append("quantity deve essere > 0")
                except ValueError:
                    errors.append(f"quantity non numerico: {quantity_str}")

            # Parse price
            price: float | None = None
            price_str = row_data.get("price", "")
            if not price_str:
                errors.append("price obbligatorio")
            else:
                try:
                    price = float(price_str.replace(",", "."))
                    if price < 0:
                        errors.append("price deve essere >= 0")
                except ValueError:
                    errors.append(f"price non numerico: {price_str}")

            # Parse optional fields
            fees: float | None = None
            fees_str = row_data.get("fees", "")
            if fees_str:
                try:
                    fees = float(fees_str.replace(",", "."))
                except ValueError:
                    errors.append(f"fees non numerico: {fees_str}")

            taxes: float | None = None
            taxes_str = row_data.get("taxes", "")
            if taxes_str:
                try:
                    taxes = float(taxes_str.replace(",", "."))
                except ValueError:
                    errors.append(f"taxes non numerico: {taxes_str}")

            trade_currency = row_data.get("trade_currency", "").strip().upper() or None
            notes = row_data.get("notes", "").strip() or None

            # Try to resolve asset
            asset_id: int | None = None
            asset_name: str | None = None
            if symbol and not errors:
                try:
                    matches = self.repo.search_assets(symbol)
                    exact = next((m for m in matches if str(m.get("symbol", "")).upper() == symbol), None)
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
                symbol=symbol or None,
                side=side or None,
                quantity=quantity,
                price=price,
                fees=fees,
                taxes=taxes,
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
                # Ensure asset exists
                symbol = str(row_data.get("symbol", "")).strip().upper()
                asset_id = row_data.get("asset_id")
                side = str(row_data.get("side", "")).lower()
                is_cash = side in {"deposit", "withdrawal", "dividend", "fee", "interest"}

                if asset_id is None and not is_cash and symbol:
                    # Auto-create asset
                    base_ccy = self.repo.get_portfolio_base_currency(portfolio_id)
                    try:
                        asset = self.repo.create_asset(AssetCreate(
                            symbol=symbol,
                            name=symbol,
                            asset_type="stock",
                            quote_currency=base_ccy,
                        ))
                        asset_id = asset.id
                    except ValueError:
                        matches = self.repo.search_assets(symbol)
                        exact = next((m for m in matches if str(m.get("symbol", "")).upper() == symbol), None)
                        if exact:
                            asset_id = int(exact["id"])
                        else:
                            errors.append(f"Riga {row_data.get('row_number')}: impossibile risolvere asset {symbol}")
                            continue

                trade_at_str = row_data.get("trade_at", "")
                trade_at = datetime.fromisoformat(trade_at_str)
                trade_currency = row_data.get("trade_currency") or self.repo.get_portfolio_base_currency(portfolio_id)

                self.repo.create_transaction(
                    TransactionCreate(
                        portfolio_id=portfolio_id,
                        asset_id=asset_id if not is_cash else (asset_id or None),
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
