import { Entity, Column, PrimaryGeneratedColumn, ManyToOne } from 'typeorm';
import { Asset } from '../../assets/entities/asset.entity';
import { Portfolio } from '../../portfolios/entities/portfolio.entity';

@Entity()
export class Transaction {
  @PrimaryGeneratedColumn()
  id: number;

  @ManyToOne(() => Asset)
  asset: Asset;

  @ManyToOne(() => Portfolio)
  portfolio: Portfolio;

  @Column({ type: 'enum', enum: ['buy', 'sell'] })
  transaction_type: string;

  @Column('decimal')
  quantity: number;

  @Column('decimal')
  price_per_unit: number;

  @Column()
  timestamp: Date;
}
