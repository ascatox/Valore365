import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';
import { TransactionsService } from './transactions.service';
import { CreateTransactionDto } from './dto/create-transaction.dto';
import { ReadTransactionDto } from './dto/read-transaction.dto';
import { AuthGuard } from '../auth/auth.guard';

@UseGuards(AuthGuard)
@Controller('transactions')
export class TransactionsController {
  constructor(private readonly transactionsService: TransactionsService) {}

  @Post()
  create(@Body() createTransactionDto: CreateTransactionDto): Promise<ReadTransactionDto> {
    return this.transactionsService.create(createTransactionDto);
  }

  @Get('portfolio/:id')
  findByPortfolio(@Param('id') id: string): Promise<ReadTransactionDto[]> {
    return this.transactionsService.findByPortfolio(+id);
  }
}
