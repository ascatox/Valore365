import { IsString, IsNotEmpty, IsOptional, IsEnum, IsBoolean, MinLength, MaxLength } from 'class-validator';

export class CreateAssetDto {
  @IsString()
  @IsNotEmpty()
  @MinLength(1)
  @MaxLength(32)
  symbol: string;

  @IsString()
  @IsOptional()
  @MaxLength(255)
  name: string;

  @IsEnum(['stock', 'etf', 'crypto', 'bond', 'cash', 'fund'])
  asset_type: string;

  @IsString()
  @IsOptional()
  @MaxLength(16)
  exchange_code: string;

  @IsString()
  @IsOptional()
  @MaxLength(255)
  exchange_name: string;

  @IsString()
  @IsNotEmpty()
  @MinLength(3)
  @MaxLength(3)
  quote_currency: string;

  @IsString()
  @IsOptional()
  @MinLength(12)
  @MaxLength(12)
  isin: string;

  @IsBoolean()
  @IsOptional()
  active: boolean;
}
