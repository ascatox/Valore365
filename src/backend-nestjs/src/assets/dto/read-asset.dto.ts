import { Exclude } from 'class-transformer';

export class ReadAssetDto {
  id: number;
  symbol: string;
  name: string;
  asset_type: string;
  exchange_code: string;
  exchange_name: string;
  quote_currency: string;
  isin: string;
  active: boolean;
}
