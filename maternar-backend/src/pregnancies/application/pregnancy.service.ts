import { Injectable } from '@nestjs/common';

import { CreatePregnancyDto } from '../http/pregnancy.dto';
import { DatabaseService } from '../../database/database.service';

@Injectable()
export class PregnancyService {
  constructor(private readonly prisma: DatabaseService) {}

  async create(userId: string, dto: CreatePregnancyDto) {
    let estimatedDueDate: Date | null = null;

    if (dto.dumStartDate) {
      const dumDate = new Date(dto.dumStartDate);
      estimatedDueDate = new Date(dumDate.setDate(dumDate.getDate() + 280));
    }

    const pregnancy = await this.prisma.pregnancy.create({
      data: {
        userId,
        estimatedDueDate,
        dumStartDate: dto.dumStartDate ? new Date(dto.dumStartDate) : null,
      },
    });

    return {
      id: pregnancy.id,
      dumStartDate: pregnancy.dumStartDate,
      estimatedDueDate: pregnancy.estimatedDueDate,
      status: pregnancy.status,
      createdAt: pregnancy.createdAt,
    };
  }

  async findPregnancyById(id: string) {
    return await this.prisma.pregnancy.findUnique({
      where: { id },
    });
  }

  async findAllByUser(userId: string) {
    return await this.prisma.pregnancy.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
      select: {
        id: true,
        dumStartDate: true,
        estimatedDueDate: true,
        status: true,
        currentClusterName: true,
        createdAt: true,
      },
    });
  }
}
