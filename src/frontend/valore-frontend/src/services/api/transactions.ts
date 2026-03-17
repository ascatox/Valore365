import { apiFetch } from './client';
import type {
  TransactionCreateInput,
  TransactionRead,
  TransactionListItem,
  TransactionUpdateInput,
  CashMovementCreateInput,
  CashBalanceResponse,
  CashFlowTimelineResponse,
} from './types';

export const createTransaction = async (payload: TransactionCreateInput): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>('/transactions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioTransactions = async (portfolioId: number): Promise<TransactionListItem[]> => {
  return apiFetch<TransactionListItem[]>(`/portfolios/${portfolioId}/transactions`);
};

export const updateTransaction = async (
  transactionId: number,
  payload: TransactionUpdateInput,
): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>(`/transactions/${transactionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deleteTransaction = async (transactionId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/transactions/${transactionId}`, {
    method: 'DELETE',
  });
};

export const createCashMovement = async (payload: CashMovementCreateInput): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>('/cash-movements', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioCashBalance = async (portfolioId: number): Promise<CashBalanceResponse> => {
  return apiFetch<CashBalanceResponse>(`/portfolios/${portfolioId}/cash-balance`);
};

export const getPortfolioCashFlowTimeline = async (portfolioId: number): Promise<CashFlowTimelineResponse> => {
  return apiFetch<CashFlowTimelineResponse>(`/portfolios/${portfolioId}/cash-flow-timeline`);
};
