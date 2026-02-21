import { IsString, IsNotEmpty, MinLength, MaxLength } from 'class-validator';

export class CreatePortfolioDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  name: string;

  @IsString()
  @IsNotEmpty()
  @MinLength(3)
  @MaxLength(3)
  base_currency: string;
}
