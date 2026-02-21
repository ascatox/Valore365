import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';
import { PortfoliosService } from './portfolios.service';
import { CreatePortfolioDto } from './dto/create-portfolio.dto';
import { ReadPortfolioDto } from './dto/read-portfolio.dto';
import { AuthGuard } from '../auth/auth.guard';

@UseGuards(AuthGuard)
@Controller('portfolios')
export class PortfoliosController {
  constructor(private readonly portfoliosService: PortfoliosService) {}

  @Post()
  create(@Body() createPortfolioDto: CreatePortfolioDto): Promise<ReadPortfolioDto> {
    return this.portfoliosService.create(createPortfolioDto);
  }

  @Get()
  findAll(): Promise<ReadPortfolioDto[]> {
    return this.portfoliosService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string): Promise<ReadPortfolioDto> {
    return this.portfoliosService.findOne(+id);
  }
}
