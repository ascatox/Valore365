import { Entity, Column, PrimaryGeneratedColumn } from 'typeorm';

@Entity()
export class Asset {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ length: 32 })
  symbol: string;

  @Column({ length: 255, nullable: true })
  name: string;

  @Column({ type: 'enum', enum: ['stock', 'etf', 'crypto', 'bond', 'cash', 'fund'] })
  asset_type: string;

  @Column({ length: 16, nullable: true })
  exchange_code: string;

  @Column({ length: 255, nullable: true })
  exchange_name: string;

  @Column({ length: 3 })
  quote_currency: string;

  @Column({ length: 12, nullable: true })
  isin: string;

  @Column({ default: true })
  active: boolean;
}
