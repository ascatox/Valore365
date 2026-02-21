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
var _a, _b, _c;
Object.defineProperty(exports, "__esModule", { value: true });
exports.TransactionsService = void 0;
const common_1 = require("@nestjs/common");
const typeorm_1 = require("@nestjs/typeorm");
const typeorm_2 = require("typeorm");
const transaction_entity_1 = require("./entities/transaction.entity");
const asset_entity_1 = require("../assets/entities/asset.entity");
const portfolio_entity_1 = require("../portfolios/entities/portfolio.entity");
let TransactionsService = class TransactionsService {
    transactionRepository;
    assetRepository;
    portfolioRepository;
    constructor(transactionRepository, assetRepository, portfolioRepository) {
        this.transactionRepository = transactionRepository;
        this.assetRepository = assetRepository;
        this.portfolioRepository = portfolioRepository;
    }
    async create(createTransactionDto) {
        const { asset_id, portfolio_id, ...rest } = createTransactionDto;
        const asset = await this.assetRepository.findOne({ where: { id: asset_id } });
        if (!asset) {
            throw new common_1.NotFoundException('Asset not found');
        }
        const portfolio = await this.portfolioRepository.findOne({ where: { id: portfolio_id } });
        if (!portfolio) {
            throw new common_1.NotFoundException('Portfolio not found');
        }
        const transaction = this.transactionRepository.create({
            ...rest,
            asset,
            portfolio,
        });
        return this.transactionRepository.save(transaction);
    }
    async findByPortfolio(portfolioId) {
        return this.transactionRepository.find({
            where: { portfolio: { id: portfolioId } },
            relations: ['asset'],
        });
    }
};
exports.TransactionsService = TransactionsService;
exports.TransactionsService = TransactionsService = __decorate([
    (0, common_1.Injectable)(),
    __param(0, (0, typeorm_1.InjectRepository)(transaction_entity_1.Transaction)),
    __param(1, (0, typeorm_1.InjectRepository)(asset_entity_1.Asset)),
    __param(2, (0, typeorm_1.InjectRepository)(portfolio_entity_1.Portfolio)),
    __metadata("design:paramtypes", [typeof (_a = typeof typeorm_2.Repository !== "undefined" && typeorm_2.Repository) === "function" ? _a : Object, typeof (_b = typeof typeorm_2.Repository !== "undefined" && typeorm_2.Repository) === "function" ? _b : Object, typeof (_c = typeof typeorm_2.Repository !== "undefined" && typeorm_2.Repository) === "function" ? _c : Object])
], TransactionsService);
//# sourceMappingURL=transactions.service.js.map