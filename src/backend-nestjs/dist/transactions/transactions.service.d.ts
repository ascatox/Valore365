import { Repository } from 'typeorm';
import { Transaction } from './entities/transaction.entity';
import { CreateTransactionDto } from './dto/create-transaction.dto';
import { ReadTransactionDto } from './dto/read-transaction.dto';
import { Asset } from '../assets/entities/asset.entity';
import { Portfolio } from '../portfolios/entities/portfolio.entity';
export declare class TransactionsService {
    private readonly transactionRepository;
    private readonly assetRepository;
    private readonly portfolioRepository;
    constructor(transactionRepository: Repository<Transaction>, assetRepository: Repository<Asset>, portfolioRepository: Repository<Portfolio>);
    create(createTransactionDto: CreateTransactionDto): Promise<ReadTransactionDto>;
    findByPortfolio(portfolioId: number): Promise<ReadTransactionDto[]>;
}
