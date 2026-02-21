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
exports.Transaction = void 0;
const typeorm_1 = require("typeorm");
const asset_entity_1 = require("../../assets/entities/asset.entity");
const portfolio_entity_1 = require("../../portfolios/entities/portfolio.entity");
let Transaction = class Transaction {
    id;
    asset;
    portfolio;
    transaction_type;
    quantity;
    price_per_unit;
    timestamp;
};
exports.Transaction = Transaction;
__decorate([
    (0, typeorm_1.PrimaryGeneratedColumn)(),
    __metadata("design:type", Number)
], Transaction.prototype, "id", void 0);
__decorate([
    (0, typeorm_1.ManyToOne)(() => asset_entity_1.Asset),
    __metadata("design:type", asset_entity_1.Asset)
], Transaction.prototype, "asset", void 0);
__decorate([
    (0, typeorm_1.ManyToOne)(() => portfolio_entity_1.Portfolio),
    __metadata("design:type", portfolio_entity_1.Portfolio)
], Transaction.prototype, "portfolio", void 0);
__decorate([
    (0, typeorm_1.Column)({ type: 'enum', enum: ['buy', 'sell'] }),
    __metadata("design:type", String)
], Transaction.prototype, "transaction_type", void 0);
__decorate([
    (0, typeorm_1.Column)('decimal'),
    __metadata("design:type", Number)
], Transaction.prototype, "quantity", void 0);
__decorate([
    (0, typeorm_1.Column)('decimal'),
    __metadata("design:type", Number)
], Transaction.prototype, "price_per_unit", void 0);
__decorate([
    (0, typeorm_1.Column)(),
    __metadata("design:type", Date)
], Transaction.prototype, "timestamp", void 0);
exports.Transaction = Transaction = __decorate([
    (0, typeorm_1.Entity)()
], Transaction);
//# sourceMappingURL=transaction.entity.js.map