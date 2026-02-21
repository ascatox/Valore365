import { Injectable, NotFoundException, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Asset } from './entities/asset.entity';
import { CreateAssetDto } from './dto/create-asset.dto';
import { ReadAssetDto } from './dto/read-asset.dto';

@Injectable()
export class AssetsService {
  constructor(
    @InjectRepository(Asset)
    private readonly assetRepository: Repository<Asset>,
  ) {}

  async create(createAssetDto: CreateAssetDto): Promise<ReadAssetDto> {
    try {
      const asset = this.assetRepository.create(createAssetDto);
      return await this.assetRepository.save(asset);
    } catch (error) {
      if (error.code === '23505') { // Unique violation
        throw new ConflictException('Asset with this symbol already exists.');
      }
      throw error;
    }
  }

  async findOne(id: number): Promise<ReadAssetDto> {
    const asset = await this.assetRepository.findOne({ where: { id } });
    if (!asset) {
      throw new NotFoundException('Asset not found');
    }
    return asset;
  }

  async search(query: string): Promise<ReadAssetDto[]> {
    return this.assetRepository
      .createQueryBuilder('asset')
      .where('asset.symbol ILIKE :query OR asset.name ILIKE :query', { query: `%${query}%` })
      .getMany();
  }
}
