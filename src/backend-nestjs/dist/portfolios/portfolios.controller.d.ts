import { PortfoliosService } from './portfolios.service';
import { CreatePortfolioDto } from './dto/create-portfolio.dto';
import { ReadPortfolioDto } from './dto/read-portfolio.dto';
export declare class PortfoliosController {
    private readonly portfoliosService;
    constructor(portfoliosService: PortfoliosService);
    create(createPortfolioDto: CreatePortfolioDto): Promise<ReadPortfolioDto>;
    findAll(): Promise<ReadPortfolioDto[]>;
    findOne(id: string): Promise<ReadPortfolioDto>;
}
