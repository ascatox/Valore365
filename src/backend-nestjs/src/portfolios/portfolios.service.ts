import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Portfolio } from './entities/portfolio.entity';
import { CreatePortfolioDto } from './dto/create-portfolio.dto';
import { ReadPortfolioDto } from './dto/read-portfolio.dto';

@Injectable()
export class PortfoliosService {
  constructor(
    @InjectRepository(Portfolio)
    private readonly portfolioRepository: Repository<Portfolio>,
  ) {}

  async create(createPortfolioDto: CreatePortfolioDto): Promise<ReadPortfolioDto> {
    const portfolio = this.portfolioRepository.create(createPortfolioDto);
    return this.portfolioRepository.save(portfolio);
  }

  async findOne(id: number): Promise<ReadPortfolioDto> {
    const portfolio = await this.portfolioRepository.findOne({ where: { id } });
    if (!portfolio) {
      throw new NotFoundException('Portfolio not found');
    }
    return portfolio;
  }

  async findAll(): Promise<ReadPortfolioDto[]> {
    return this.portfolioRepository.find();
  }
}
