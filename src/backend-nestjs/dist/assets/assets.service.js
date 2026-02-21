"use strict";
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};
var __param = (this && this.__param) || function (paramIndex, decorator) {
    return function (target, key) { decorator(target, key, paramIndex); }
};
var _a;
Object.defineProperty(exports, "__esModule", { value: true });
exports.AssetsService = void 0;
const common_1 = require("@nestjs/common");
const typeorm_1 = require("@nestjs/typeorm");
const typeorm_2 = require("typeorm");
const asset_entity_1 = require("./entities/asset.entity");
let AssetsService = class AssetsService {
    assetRepository;
    constructor(assetRepository) {
        this.assetRepository = assetRepository;
    }
    async create(createAssetDto) {
        try {
            const asset = this.assetRepository.create(createAssetDto);
            return await this.assetRepository.save(asset);
        }
        catch (error) {
            if (error.code === '23505') {
                throw new common_1.ConflictException('Asset with this symbol already exists.');
            }
            throw error;
        }
    }
    async findOne(id) {
        const asset = await this.assetRepository.findOne({ where: { id } });
        if (!asset) {
            throw new common_1.NotFoundException('Asset not found');
        }
        return asset;
    }
    async search(query) {
        return this.assetRepository
            .createQueryBuilder('asset')
            .where('asset.symbol ILIKE :query OR asset.name ILIKE :query', { query: `%${query}%` })
            .getMany();
    }
};
exports.AssetsService = AssetsService;
exports.AssetsService = AssetsService = __decorate([
    (0, common_1.Injectable)(),
    __param(0, (0, typeorm_1.InjectRepository)(asset_entity_1.Asset)),
    __metadata("design:paramtypes", [typeof (_a = typeof typeorm_2.Repository !== "undefined" && typeorm_2.Repository) === "function" ? _a : Object])
], AssetsService);
//# sourceMappingURL=assets.service.js.map