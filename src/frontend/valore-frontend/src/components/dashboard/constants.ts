export const ALLOCATION_COLORS = [
  '#228be6', '#15aabf', '#12b886', '#82c91e', '#fab005', '#fd7e14', '#e64980',
  '#7950f2', '#4c6ef5', '#20c997',
];

export const DASHBOARD_WINDOWS = [
  { label: '1g', value: '1', days: 1 },
  { label: '1s', value: '7', days: 7 },
  { label: '30g', value: '30', days: 30 },
  { label: '90g', value: '90', days: 90 },
  { label: '1a', value: '365', days: 365 },
] as const;

export const STORAGE_KEYS = {
  selectedPortfolioId: 'valore365.dashboard.selectedPortfolioId',
  chartWindow: 'valore365.dashboard.chartWindow',
  activeTab: 'valore365.dashboard.activeTab',
} as const;
