import { Repository } from 'typeorm';
import { Asset } from './entities/asset.entity';
import { CreateAssetDto } from './dto/create-asset.dto';
import { ReadAssetDto } from './dto/read-asset.dto';
export declare class AssetsService {
    private readonly assetRepository;
    constructor(assetRepository: Repository<Asset>);
    create(createAssetDto: CreateAssetDto): Promise<ReadAssetDto>;
    findOne(id: number): Promise<ReadAssetDto>;
    search(query: string): Promise<ReadAssetDto[]>;
}
