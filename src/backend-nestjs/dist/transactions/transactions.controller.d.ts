import { TransactionsService } from './transactions.service';
import { CreateTransactionDto } from './dto/create-transaction.dto';
import { ReadTransactionDto } from './dto/read-transaction.dto';
export declare class TransactionsController {
    private readonly transactionsService;
    constructor(transactionsService: TransactionsService);
    create(createTransactionDto: CreateTransactionDto): Promise<ReadTransactionDto>;
    findByPortfolio(id: string): Promise<ReadTransactionDto[]>;
}
