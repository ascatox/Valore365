import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CsvColumnMapping, CsvImportPreviewResponse } from '../../../services/api';
import { CsvImportModal } from './CsvImportModal';

const uploadCsvImportPreviewMock = vi.fn();
const commitCsvImportMock = vi.fn();
const cancelCsvImportMock = vi.fn();

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock);
window.HTMLElement.prototype.scrollIntoView = vi.fn();

vi.mock('../../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../../services/api')>('../../../services/api');
  return {
    ...actual,
    uploadCsvImportPreview: (...args: unknown[]) => uploadCsvImportPreviewMock(...args),
    commitCsvImport: (...args: unknown[]) => commitCsvImportMock(...args),
    cancelCsvImport: (...args: unknown[]) => cancelCsvImportMock(...args),
  };
});

const proposedMapping: CsvColumnMapping = {
  trade_at: 'Data operazione',
  isin: 'ISIN',
  side: 'Tipo',
  quantity: 'Quantita',
  price: 'Importo unitario',
  trade_currency: 'Valuta',
  fees: null,
  name: 'Descrizione',
  date_format: 'DD/MM/YYYY',
};
const columns = ['Data operazione', 'Tipo', 'ISIN', 'Descrizione', 'Quantita', 'Importo unitario', 'Importo totale', 'Valuta'];

function previewResponse(overrides: Partial<CsvImportPreviewResponse>): CsvImportPreviewResponse {
  return {
    batch_id: 10,
    filename: 'altro-broker.csv',
    total_rows: 1,
    valid_rows: 1,
    error_rows: 0,
    rows: [
      {
        row_number: 1,
        valid: true,
        errors: [],
        trade_at: '2026-03-02T00:00:00',
        isin: 'IE00B4L5Y983',
        titolo: 'ISHARES CORE MSCI WORLD',
        side: 'buy',
        quantity: 10,
        price: 85.5,
        fees: null,
        taxes: null,
        trade_currency: 'EUR',
        notes: null,
        asset_id: null,
        asset_name: null,
      },
    ],
    column_mapping: null,
    ...overrides,
  };
}

async function uploadFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['contenuto'], 'altro-broker.csv', { type: 'text/csv' });
  await userEvent.upload(input, file);
  return file;
}

// The Select input; its listbox is labelled by the same label, so getByLabelText alone is ambiguous.
const field = (name: string) => screen.getByRole('textbox', { name });

function renderModal() {
  return render(
    <MantineProvider env="test">
      <MemoryRouter>
        <CsvImportModal opened onClose={() => {}} portfolioId={1} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe('CsvImportModal column mapping', () => {
  beforeEach(() => {
    uploadCsvImportPreviewMock.mockReset();
    commitCsvImportMock.mockReset();
    cancelCsvImportMock.mockReset().mockResolvedValue({ status: 'ok' });
  });

  it('shows no mapping editor for a recognised format', async () => {
    uploadCsvImportPreviewMock.mockResolvedValue(previewResponse({}));
    renderModal();

    await uploadFile();

    expect(await screen.findByRole('button', { name: /Importa 1 transazioni/ })).toBeEnabled();
    expect(screen.queryByText('Colonne del file')).not.toBeInTheDocument();
    expect(screen.queryByText('Formato non riconosciuto')).not.toBeInTheDocument();
  });

  it('shows the proposed mapping and lets the user correct it before anything is saved', async () => {
    const user = userEvent.setup({ delay: null });
    uploadCsvImportPreviewMock.mockResolvedValueOnce(
      previewResponse({ column_mapping: { source: 'ai', mapping: proposedMapping, columns } }),
    );
    renderModal();

    const file = await uploadFile();

    expect(await screen.findByText('Colonne del file')).toBeInTheDocument();
    expect(screen.getAllByText('Formato non riconosciuto').length).toBeGreaterThan(0);
    expect(field('Prezzo')).toHaveValue('Importo unitario');
    expect(field('ISIN')).toHaveValue('ISIN');
    const applyButton = screen.getByRole('button', { name: 'Applica associazione' });
    const commitButton = screen.getByRole('button', { name: /Importa 1 transazioni/ });
    expect(applyButton).toBeDisabled();
    expect(commitButton).toBeEnabled();

    // Correcting a field blocks the import until the preview is rebuilt with the new mapping.
    await user.click(field('Prezzo'));
    await user.click(await screen.findByRole('option', { name: 'Importo totale' }));
    expect(field('Prezzo')).toHaveValue('Importo totale');
    expect(applyButton).toBeEnabled();
    expect(commitButton).toBeDisabled();

    uploadCsvImportPreviewMock.mockResolvedValueOnce(
      previewResponse({
        batch_id: 11,
        valid_rows: 1,
        column_mapping: {
          source: 'user',
          mapping: { ...proposedMapping, price: 'Importo totale' },
          columns,
        },
      }),
    );
    await user.click(applyButton);

    await waitFor(() => expect(uploadCsvImportPreviewMock).toHaveBeenCalledTimes(2));
    expect(uploadCsvImportPreviewMock).toHaveBeenLastCalledWith(
      1,
      file,
      'fineco',
      { ...proposedMapping, price: 'Importo totale' },
    );
    // The superseded pending batch is discarded; the new one is committed only on the explicit click.
    await waitFor(() => expect(cancelCsvImportMock).toHaveBeenCalledWith(10));
    expect(await screen.findByText('Associazione delle colonne modificata')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Applica associazione' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Importa 1 transazioni/ })).toBeEnabled();
    expect(commitCsvImportMock).not.toHaveBeenCalled();
  }, 15000);

  it('keeps the current preview and shows the reason when the corrected mapping is rejected', async () => {
    const user = userEvent.setup({ delay: null });
    uploadCsvImportPreviewMock.mockResolvedValueOnce(
      previewResponse({ column_mapping: { source: 'ai', mapping: proposedMapping, columns } }),
    );
    renderModal();
    await uploadFile();
    await screen.findByText('Colonne del file');

    await user.click(field('Quantità'));
    await user.click(await screen.findByRole('option', { name: 'Descrizione' }));
    uploadCsvImportPreviewMock.mockRejectedValueOnce(
      new Error("La colonna 'Descrizione' non contiene valori validi per il campo quantita"),
    );
    await user.click(screen.getByRole('button', { name: 'Applica associazione' }));

    expect(await screen.findByText(/non contiene valori validi per il campo quantita/)).toBeInTheDocument();
    expect(cancelCsvImportMock).not.toHaveBeenCalled();
    expect(commitCsvImportMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Importa 1 transazioni/ })).toBeDisabled();
  }, 15000);
});
