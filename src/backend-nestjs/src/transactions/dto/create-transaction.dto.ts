import { IsEnum, IsNumber, IsDate, IsPositive } from 'class-validator';

export class CreateTransactionDto {
  @IsNumber()
  asset_id: number;

  @IsNumber()
  portfolio_id: number;

  @IsEnum(['buy', 'sell'])
  transaction_type: string;

  @IsNumber()
  @IsPositive()
  quantity: number;

  @IsNumber()
  @IsPositive()
  price_per_unit: number;

  @IsDate()
  timestamp: Date;
}
