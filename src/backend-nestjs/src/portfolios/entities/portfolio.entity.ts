import { Entity, Column, PrimaryGeneratedColumn } from 'typeorm';

@Entity()
export class Portfolio {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ length: 255 })
  name: string;

  @Column({ length: 3 })
  base_currency: string;
}
