import { Controller, Get, Post, Body, Param, Query, UseGuards } from '@nestjs/common';
import { AssetsService } from './assets.service';
import { CreateAssetDto } from './dto/create-asset.dto';
import { ReadAssetDto } from './dto/read-asset.dto';
import { AuthGuard } from '../auth/auth.guard';

@UseGuards(AuthGuard)
@Controller('assets')
export class AssetsController {
  constructor(private readonly assetsService: AssetsService) {}

  @Post()
  create(@Body() createAssetDto: CreateAssetDto): Promise<ReadAssetDto> {
    return this.assetsService.create(createAssetDto);
  }

  @Get('search')
  search(@Query('q') query: string): Promise<ReadAssetDto[]> {
    return this.assetsService.search(query);
  }

  @Get(':id')
  findOne(@Param('id') id: string): Promise<ReadAssetDto> {
    return this.assetsService.findOne(+id);
  }
}
