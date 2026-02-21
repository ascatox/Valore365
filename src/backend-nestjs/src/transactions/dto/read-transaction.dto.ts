import { ReadAssetDto } from '../../assets/dto/read-asset.dto';

export class ReadTransactionDto {
  id: number;
  asset: ReadAssetDto;
  transaction_type: string;
  quantity: number;
  price_per_unit: number;
  timestamp: Date;
}
