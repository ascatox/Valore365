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
Object.defineProperty(exports, "__esModule", { value: true });
exports.Asset = void 0;
const typeorm_1 = require("typeorm");
let Asset = class Asset {
    id;
    symbol;
    name;
    asset_type;
    exchange_code;
    exchange_name;
    quote_currency;
    isin;
    active;
};
exports.Asset = Asset;
__decorate([
    (0, typeorm_1.PrimaryGeneratedColumn)(),
    __metadata("design:type", Number)
], Asset.prototype, "id", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 32 }),
    __metadata("design:type", String)
], Asset.prototype, "symbol", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 255, nullable: true }),
    __metadata("design:type", String)
], Asset.prototype, "name", void 0);
__decorate([
    (0, typeorm_1.Column)({ type: 'enum', enum: ['stock', 'etf', 'crypto', 'bond', 'cash', 'fund'] }),
    __metadata("design:type", String)
], Asset.prototype, "asset_type", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 16, nullable: true }),
    __metadata("design:type", String)
], Asset.prototype, "exchange_code", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 255, nullable: true }),
    __metadata("design:type", String)
], Asset.prototype, "exchange_name", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 3 }),
    __metadata("design:type", String)
], Asset.prototype, "quote_currency", void 0);
__decorate([
    (0, typeorm_1.Column)({ length: 12, nullable: true }),
    __metadata("design:type", String)
], Asset.prototype, "isin", void 0);
__decorate([
    (0, typeorm_1.Column)({ default: true }),
    __metadata("design:type", Boolean)
], Asset.prototype, "active", void 0);
exports.Asset = Asset = __decorate([
    (0, typeorm_1.Entity)()
], Asset);
//# sourceMappingURL=asset.entity.js.map