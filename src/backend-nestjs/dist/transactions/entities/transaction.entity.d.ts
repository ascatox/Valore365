import { Asset } from '../../assets/entities/asset.entity';
import { Portfolio } from '../../portfolios/entities/portfolio.entity';
export declare class Transaction {
    id: number;
    asset: Asset;
    portfolio: Portfolio;
    transaction_type: string;
    quantity: number;
    price_per_unit: number;
    timestamp: Date;
}
