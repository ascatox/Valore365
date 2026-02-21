import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Transaction } from './entities/transaction.entity';
import { CreateTransactionDto } from './dto/create-transaction.dto';
import { ReadTransactionDto } from './dto/read-transaction.dto';
import { Asset } from '../assets/entities/asset.entity';
import { Portfolio } from '../portfolios/entities/portfolio.entity';

@Injectable()
export class TransactionsService {
  constructor(
    @InjectRepository(Transaction)
    private readonly transactionRepository: Repository<Transaction>,
    @InjectRepository(Asset)
    private readonly assetRepository: Repository<Asset>,
    @InjectRepository(Portfolio)
    private readonly portfolioRepository: Repository<Portfolio>,
  ) {}

  async create(createTransactionDto: CreateTransactionDto): Promise<ReadTransactionDto> {
    const { asset_id, portfolio_id, ...rest } = createTransactionDto;

    const asset = await this.assetRepository.findOne({ where: { id: asset_id } });
    if (!asset) {
      throw new NotFoundException('Asset not found');
    }

    const portfolio = await this.portfolioRepository.findOne({ where: { id: portfolio_id } });
    if (!portfolio) {
      throw new NotFoundException('Portfolio not found');
    }

    const transaction = this.transactionRepository.create({
      ...rest,
      asset,
      portfolio,
    });

    return this.transactionRepository.save(transaction);
  }

  async findByPortfolio(portfolioId: number): Promise<ReadTransactionDto[]> {
    return this.transactionRepository.find({
      where: { portfolio: { id: portfolioId } },
      relations: ['asset'],
    });
  }
}
