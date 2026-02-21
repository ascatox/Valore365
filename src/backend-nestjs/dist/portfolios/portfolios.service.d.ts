import { Repository } from 'typeorm';
import { Portfolio } from './entities/portfolio.entity';
import { CreatePortfolioDto } from './dto/create-portfolio.dto';
import { ReadPortfolioDto } from './dto/read-portfolio.dto';
export declare class PortfoliosService {
    private readonly portfolioRepository;
    constructor(portfolioRepository: Repository<Portfolio>);
    create(createPortfolioDto: CreatePortfolioDto): Promise<ReadPortfolioDto>;
    findOne(id: number): Promise<ReadPortfolioDto>;
    findAll(): Promise<ReadPortfolioDto[]>;
}
