import { AssetsService } from './assets.service';
import { CreateAssetDto } from './dto/create-asset.dto';
import { ReadAssetDto } from './dto/read-asset.dto';
export declare class AssetsController {
    private readonly assetsService;
    constructor(assetsService: AssetsService);
    create(createAssetDto: CreateAssetDto): Promise<ReadAssetDto>;
    search(query: string): Promise<ReadAssetDto[]>;
    findOne(id: string): Promise<ReadAssetDto>;
}
