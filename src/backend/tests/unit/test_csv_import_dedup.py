"""TASK-42: atomic CSV commit and cross-batch duplicate detection.

Two layers are tested without a database:
- the service (preview -> commit -> re-upload) against an in-memory repository
  whose commit_csv_import_batch behaves like the real one (claim + inserts,
  all or nothing);
- the real repository method against a fake engine that, like Postgres,
  discards every change of a transaction that ends with an exception.
"""

import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.copilot_tools import _get_recent_transactions
from app.errors import AppError
from app.models import CsvImportCommitRequest, TransactionCreate, TransactionListItem
from app.repository._base import BaseRepositoryMixin
from app.repository._transactions import TransactionsMixin
from app.repository._utilities import UtilitiesMixin
from app.services.csv_service import CsvImportService

ASSETS = {"IE00TEST0001": 7, "IE00TEST0002": 8}

HEADER = "operazione;isin;segno;quantita;prezzo;divisa;descrizione;controvalore;commissioni amministrato"
BUY_ROW = "04/08/2026;IE00TEST0001;A;31;100,00;EUR;Acquisto;;2,95"
DIVIDEND_ROW = "15/09/2026;IE00TEST0002;;1;0;EUR;Dividendo;918,29;"
SELL_ROW = "20/09/2026;IE00TEST0001;V;5;110,00;EUR;Vendita;;2,95"

FILE = "\n".join([HEADER, BUY_ROW, DIVIDEND_ROW, SELL_ROW])


class _InMemoryImportRepo:
    """Repository double: batches and transactions in memory, commit all-or-nothing."""

    def __init__(self) -> None:
        self.transactions: list[TransactionListItem] = []
        self.batches: dict[int, dict] = {}
        self.fail_on_row: int | None = None

    # --- lookups used by the preview ---
    def search_assets(self, query):
        query = query.upper()
        return [{"id": aid, "isin": isin, "name": isin} for isin, aid in ASSETS.items() if isin == query]

    def get_portfolio_base_currency(self, portfolio_id, user_id=None):
        return "EUR"

    def list_transactions(self, portfolio_id, user_id):
        return sorted(self.transactions, key=lambda t: (t.trade_at, t.id), reverse=True)

    def find_committed_csv_import_batches(self, portfolio_id, user_id, filename, source_sha256):
        found = []
        for bid, batch in sorted(self.batches.items(), reverse=True):
            if batch["status"] != "committed" or batch["portfolio_id"] != portfolio_id:
                continue
            same_content = batch["preview_data"].get("source_sha256") == source_sha256
            if batch["original_filename"] == filename or same_content:
                found.append({
                    "id": bid,
                    "original_filename": batch["original_filename"],
                    "committed_at": batch["committed_at"],
                    "same_content": same_content,
                })
        return found

    # --- batches ---
    def create_csv_import_batch(self, *, portfolio_id, user_id, filename, preview_data, **_kwargs):
        batch_id = len(self.batches) + 1
        self.batches[batch_id] = {
            "id": batch_id,
            "portfolio_id": portfolio_id,
            "status": "pending",
            "original_filename": filename,
            "committed_at": None,
            # Stored as JSON, like the jsonb column.
            "preview_data": json.loads(json.dumps(preview_data)),
        }
        return batch_id

    def get_csv_import_batch(self, batch_id, user_id):
        batch = self.batches.get(batch_id)
        return copy.deepcopy(batch) if batch else None

    def commit_csv_import_batch(self, batch_id, user_id, rows):
        saved = (copy.deepcopy(self.batches), list(self.transactions))
        try:
            batch = self.batches[batch_id]
            if batch["status"] != "pending":
                return None
            batch["status"] = "committed"
            batch["committed_at"] = datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
            ids = []
            for row_number, payload in rows:
                if row_number == self.fail_on_row:
                    raise ValueError(f"Riga {row_number}: errore simulato")
                tx = TransactionListItem(id=len(self.transactions) + 5000, **payload.model_dump())
                self.transactions.append(tx)
                ids.append(tx.id)
            return ids
        except Exception:
            self.batches, self.transactions = saved
            raise


@pytest.fixture
def repo():
    return _InMemoryImportRepo()


@pytest.fixture
def service(repo):
    return CsvImportService(repo)


def _preview(service, content=FILE, filename="Lista Titoli (2).csv"):
    return service.parse_and_validate(portfolio_id=1, user_id="u", file_content=content, filename=filename)


def test_first_upload_has_no_duplicates_and_commits_everything(service, repo):
    preview = _preview(service)

    assert preview.valid_rows == 3
    assert preview.duplicate_rows == 0
    assert preview.warnings == []
    assert all(row.duplicate_of == [] for row in preview.rows)

    result = service.commit_batch(preview.batch_id, "u")

    assert result.committed_transactions == 3
    assert result.skipped_duplicates == 0
    assert len(repo.transactions) == 3
    assert repo.batches[preview.batch_id]["status"] == "committed"


def test_second_commit_of_the_same_batch_fails_and_inserts_nothing(service, repo):
    preview = _preview(service)
    service.commit_batch(preview.batch_id, "u")

    with pytest.raises(AppError) as exc_info:
        service.commit_batch(preview.batch_id, "u")

    assert exc_info.value.status_code == 409
    assert "già stato confermato" in exc_info.value.message
    assert len(repo.transactions) == 3


def test_commit_lost_to_a_concurrent_one_is_a_conflict(service, repo, monkeypatch):
    """The status check passes (both read 'pending'), the conditional claim decides."""
    preview = _preview(service)
    stale = repo.get_csv_import_batch(preview.batch_id, "u")
    service.commit_batch(preview.batch_id, "u")
    reads = iter([stale])  # first read is stale, later ones see the committed batch
    monkeypatch.setattr(repo, "get_csv_import_batch", lambda bid, uid: next(reads, repo.batches[bid]))

    with pytest.raises(AppError) as exc_info:
        service.commit_batch(preview.batch_id, "u")

    assert exc_info.value.status_code == 409
    assert len(repo.transactions) == 3


def test_failure_mid_commit_rolls_back_and_keeps_the_batch_pending(service, repo):
    preview = _preview(service)
    repo.fail_on_row = 2

    with pytest.raises(AppError) as exc_info:
        service.commit_batch(preview.batch_id, "u")

    assert exc_info.value.status_code == 400
    assert "nessuna transazione salvata" in exc_info.value.message
    assert "Riga 2" in exc_info.value.message
    assert repo.transactions == []
    assert repo.batches[preview.batch_id]["status"] == "pending"

    # Once the cause is gone the same batch can be committed.
    repo.fail_on_row = None
    assert service.commit_batch(preview.batch_id, "u").committed_transactions == 3


def test_reupload_of_the_same_file_flags_every_row_and_skips_them(service, repo):
    first = _preview(service)
    service.commit_batch(first.batch_id, "u")
    existing_ids = sorted(t.id for t in repo.transactions)

    second = _preview(service)

    assert second.duplicate_rows == 3
    assert sorted(i for row in second.rows for i in row.duplicate_of) == existing_ids
    assert len(second.warnings) == 1
    assert "già stato importato" in second.warnings[0]

    result = service.commit_batch(second.batch_id, "u")

    assert result.committed_transactions == 0
    assert result.skipped_duplicates == 3
    assert result.skipped_duplicate_rows == [1, 2, 3]
    assert len(repo.transactions) == 3
    assert repo.batches[second.batch_id]["status"] == "committed"


def test_same_filename_with_different_content_warns_by_name(service, repo):
    first = _preview(service, content="\n".join([HEADER, BUY_ROW]))
    service.commit_batch(first.batch_id, "u")

    second = _preview(service, content="\n".join([HEADER, DIVIDEND_ROW]))

    assert second.duplicate_rows == 0
    assert len(second.warnings) == 1
    assert "stesso nome" in second.warnings[0]


def test_identical_rows_inside_a_file_are_not_duplicates_of_each_other(service, repo):
    preview = _preview(service, content="\n".join([HEADER, BUY_ROW, BUY_ROW]))

    assert preview.duplicate_rows == 0
    assert service.commit_batch(preview.batch_id, "u").committed_transactions == 2


def test_two_legit_identical_rows_with_one_already_present_skip_only_one(service, repo):
    first = _preview(service, content="\n".join([HEADER, BUY_ROW]), filename="a.csv")
    service.commit_batch(first.batch_id, "u")

    second = _preview(service, content="\n".join([HEADER, BUY_ROW, BUY_ROW]), filename="b.csv")

    assert second.duplicate_rows == 1
    assert [bool(row.duplicate_of) for row in second.rows] == [True, False]

    result = service.commit_batch(second.batch_id, "u")

    assert result.committed_transactions == 1
    assert result.skipped_duplicates == 1
    assert len(repo.transactions) == 2


def test_include_duplicates_imports_the_flagged_rows(service, repo):
    first = _preview(service)
    service.commit_batch(first.batch_id, "u")
    second = _preview(service)

    result = service.commit_batch(second.batch_id, "u", CsvImportCommitRequest(include_duplicates=True))

    assert result.committed_transactions == 3
    assert result.skipped_duplicates == 0
    assert len(repo.transactions) == 6


def test_include_row_numbers_forces_only_the_chosen_rows(service, repo):
    first = _preview(service)
    service.commit_batch(first.batch_id, "u")
    second = _preview(service)

    result = service.commit_batch(second.batch_id, "u", CsvImportCommitRequest(include_row_numbers=[2]))

    assert result.committed_transactions == 1
    assert result.skipped_duplicate_rows == [1, 3]
    assert len(repo.transactions) == 4


def test_rows_differing_in_price_beyond_tolerance_are_not_duplicates(service, repo):
    first = _preview(service, content="\n".join([HEADER, BUY_ROW]))
    service.commit_batch(first.batch_id, "u")

    near = BUY_ROW.replace("100,00", "100,0000001")  # within 1e-6 relative
    far = BUY_ROW.replace("100,00", "100,01")
    preview = _preview(service, content="\n".join([HEADER, near, far]), filename="c.csv")

    assert [bool(row.duplicate_of) for row in preview.rows] == [True, False]


def test_commit_inserts_chronologically_so_a_sell_listed_first_follows_its_buy(service, repo):
    preview = _preview(service, content="\n".join([HEADER, SELL_ROW, BUY_ROW]))

    service.commit_batch(preview.batch_id, "u")

    assert [t.side for t in repo.transactions] == ["buy", "sell"]


def test_batches_stored_before_task_42_still_commit():
    """Pending batches created by the previous version store preview_data as a plain list."""
    repo = _InMemoryImportRepo()
    repo.batches[1] = {
        "id": 1, "portfolio_id": 1, "status": "pending", "original_filename": "old.csv", "committed_at": None,
        "preview_data": [{
            "row_number": 1, "valid": True, "trade_at": "2026-08-04T00:00:00", "isin": "IE00TEST0001",
            "side": "buy", "quantity": 1.0, "price": 10.0, "trade_currency": "EUR", "asset_id": 7,
        }],
    }

    assert CsvImportService(repo).commit_batch(1, "u").committed_transactions == 1


# --- Repository: claim + inserts in one DB transaction --------------------------------


class _Row(SimpleNamespace):
    pass


class _Result:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _TxConn:
    """Interprets the few statements involved; state changes live in the open transaction."""

    def __init__(self, state: dict, fail_on_insert: int | None) -> None:
        self.state = state
        self.fail_on_insert = fail_on_insert

    def execute(self, statement, params):
        sql = " ".join(str(statement).split()).lower()
        if sql.startswith("update csv_import_batches set status = 'committed'"):
            batch = self.state["batches"].get(params["batch_id"])
            if batch is None or batch["owner"] != params["user_id"] or batch["status"] != "pending":
                return _Result(None)
            batch["status"] = "committed"
            return _Result(_Row(id=params["batch_id"]))
        if sql.startswith("select supports_fractions"):
            return _Result({"supports_fractions": True})
        if sql.startswith("select id, trade_at, side, quantity"):
            rows = [t for t in self.state["transactions"] if t["asset_id"] == params["asset_id"]]
            return _Result(rows=rows)
        if sql.startswith("insert into transactions"):
            if len(self.state["transactions"]) + 1 == self.fail_on_insert:
                raise RuntimeError("connessione persa")
            new_id = len(self.state["transactions"]) + 1
            self.state["transactions"].append({**params, "id": new_id})
            return _Result(_Row(id=new_id))
        raise AssertionError(f"unexpected statement: {sql}")


class _TxEngine:
    """engine.begin(): commit on success, roll back (discard the copy) on exception."""

    def __init__(self, state: dict, fail_on_insert: int | None = None) -> None:
        self.state = state
        self.fail_on_insert = fail_on_insert
        self.begin_calls = 0

    def begin(self):
        engine = self
        engine.begin_calls += 1

        class _Ctx:
            def __enter__(self):
                self.work = copy.deepcopy(engine.state)
                return _TxConn(self.work, engine.fail_on_insert)

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    engine.state.clear()
                    engine.state.update(self.work)
                return False

        return _Ctx()


class _AtomicRepo(UtilitiesMixin, TransactionsMixin, BaseRepositoryMixin):
    def __init__(self, engine) -> None:
        self.engine = engine

    def _get_portfolio_for_user(self, conn, portfolio_id, user_id):
        return {"id": portfolio_id}

    def _asset_exists(self, conn, asset_id):
        return True


def _payloads():
    def tx(side, day, qty):
        return TransactionCreate(
            portfolio_id=1, asset_id=7, side=side, trade_at=datetime(2026, 8, day, tzinfo=timezone.utc),
            quantity=qty, price=100.0, trade_currency="EUR",
        )

    return [(1, tx("buy", 4, 10)), (2, tx("buy", 5, 5)), (3, tx("sell", 6, 3))]


def _state():
    return {"batches": {31: {"owner": "u", "status": "pending"}}, "transactions": []}


def test_repository_commit_claims_and_inserts_in_one_transaction():
    engine = _TxEngine(_state())
    repo = _AtomicRepo(engine)

    ids = repo.commit_csv_import_batch(31, "u", _payloads())

    assert ids == [1, 2, 3]
    assert engine.begin_calls == 1
    assert engine.state["batches"][31]["status"] == "committed"
    assert len(engine.state["transactions"]) == 3


def test_repository_second_commit_returns_none_and_adds_no_rows():
    engine = _TxEngine(_state())
    repo = _AtomicRepo(engine)
    repo.commit_csv_import_batch(31, "u", _payloads())

    assert repo.commit_csv_import_batch(31, "u", _payloads()) is None
    assert len(engine.state["transactions"]) == 3


def test_repository_failure_mid_commit_rolls_back_claim_and_rows():
    engine = _TxEngine(_state(), fail_on_insert=2)
    repo = _AtomicRepo(engine)

    with pytest.raises(RuntimeError):
        repo.commit_csv_import_batch(31, "u", _payloads())

    assert engine.state["batches"][31]["status"] == "pending"
    assert engine.state["transactions"] == []


def test_repository_validation_error_names_the_row_and_rolls_back():
    engine = _TxEngine(_state())
    repo = _AtomicRepo(engine)
    rows = _payloads()
    rows[2] = (3, rows[2][1].model_copy(update={"quantity": 99}))  # oversell

    with pytest.raises(ValueError, match="Riga 3: Quantita insufficiente"):
        repo.commit_csv_import_batch(31, "u", rows)

    assert engine.state["batches"][31]["status"] == "pending"
    assert engine.state["transactions"] == []


# --- Copilot / MCP ---------------------------------------------------------------------


def test_get_recent_transactions_exposes_the_transaction_id():
    item = TransactionListItem(
        id=5806, portfolio_id=1, asset_id=8, side="dividend", trade_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        quantity=1, price=918.29, fees=0, taxes=0, trade_currency="EUR", notes=None, symbol="EUN5.DE",
        asset_name="ETF",
    )
    repo = SimpleNamespace(list_transactions=lambda portfolio_id, user_id: [item, item.model_copy(update={"id": 5814})])

    result = _get_recent_transactions({}, repo, None, portfolio_id=1, user_id="u")

    assert [t["id"] for t in result["transactions"]] == [5806, 5814]
