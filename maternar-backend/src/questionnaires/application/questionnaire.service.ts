import { Injectable, NotFoundException, HttpStatus } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { DatabaseService } from '../../database/database.service';
import { CreateQuestionnaireDto } from '../http/questionnaire.dto';
import { PregnancyService } from '../../pregnancies/application/pregnancy.service';
import { RabbitmqService } from '../../integrations/rabbitmq/rabbitmq.service';
import { IClassificationPayload } from '../../integrations/rabbitmq/interfaces/classification-payload.interface';
import { ApiException } from '../../common/api-exception';

@Injectable()
export class QuestionnaireService {
  constructor(
    private readonly prisma: DatabaseService,
    private readonly pregnancyService: PregnancyService,
    private readonly rabbitmqService: RabbitmqService,
  ) {}

  /**
   * Registra a resposta, processa o envio para a mensageria/IA e atualiza com os resultados.
   */
  async submitQuestionnaire(
    userId: string,
    pregnancyId: string,
    dto: CreateQuestionnaireDto,
  ) {
    const pregnancy =
      await this.pregnancyService.findPregnancyById(pregnancyId);

    if (!pregnancy || pregnancy.userId !== userId) {
      throw new NotFoundException(
        'Gestação não encontrada ou não pertence a este usuário.',
      );
    }

    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: { location: true },
    });

    if (!user) {
      throw new NotFoundException('Usuário não encontrado.');
    }

    // 1. Salva a resposta parcial no banco
    const response = await this.prisma.questionnaireResponse.create({
      data: {
        pregnancyId: pregnancyId,
        currentWeight: dto.currentWeight,
        currentAppointments: dto.currentAppointments,
        hadNewComplications: dto.hadNewComplications,
        antiHivFlag: dto.antiHivFlag,
      },
    });

    // 2. Monta o payload para a IA cruzando dados do check-in com dados do perfil
    const imcPreGestacional =
      user.preGestationalWeight && user.height
        ? Number(user.preGestationalWeight) / Number(user.height) ** 2
        : 0;

    const payload: IClassificationPayload = {
      nu_peso: Number(dto.currentWeight),
      nu_altura: Number(user.height) || 1.6,
      nu_imc_pre_gestacional: imcPreGestacional,
      raca_cor: user.raceColor,
      escolaridade: user.educationLevel,
      cod_municipio: user.location?.ibgeCode || '0000000',
      flag_anti_hiv: dto.antiHivFlag || 0,
    };

    // 3. Envia para o RabbitMQ e aguarda (com fallback em caso de falha da mensageria)
    try {
      const classificacao =
        await this.rabbitmqService.classificarGestante(payload);

      // 4. Atualiza a resposta e a gestação com os dados do cluster retornado
      await this.prisma.questionnaireResponse.update({
        where: { id: response.id },
        data: {
          clusterId: classificacao.cluster_id,
          clusterName: classificacao.cluster_nome_app,
          calculatedImc: classificacao.metricas.nu_imc_calculado,
          riskLevel: classificacao.nivel_risco,
          hexColor: classificacao.cor_hex,
          recommendations:
            classificacao.recomendacoes as unknown as Prisma.InputJsonValue,
          metrics: classificacao.metricas as unknown as Prisma.InputJsonValue,
        },
      });

      await this.prisma.pregnancy.update({
        where: { id: pregnancyId },
        data: {
          currentClusterId: classificacao.cluster_id,
          currentClusterName: classificacao.cluster_nome_app,
          currentRiskLevel: classificacao.nivel_risco,
          currentHexColor: classificacao.cor_hex,
        },
      });

      return {
        id: response.id,
        message: 'Questionário classificado com sucesso!',
        cluster: classificacao,
        responseDate: response.responseDate,
      };
    } catch (error) {
      throw new ApiException(
        HttpStatus.SERVICE_UNAVAILABLE,
        'CLASSIFICATION_TIMEOUT',
        'Questionário salvo. A classificação ocorrerá em instantes devido a alta demanda.',
      );
    }
  }

  async findAllByPregnancy(userId: string, pregnancyId: string) {
    const pregnancy =
      await this.pregnancyService.findPregnancyById(pregnancyId);

    if (!pregnancy || pregnancy.userId !== userId) {
      throw new NotFoundException(
        'Gestação não encontrada ou não pertence a este usuário.',
      );
    }

    const responses = await this.prisma.questionnaireResponse.findMany({
      where: { pregnancyId },
      orderBy: { responseDate: 'desc' },
    });

    return responses.map((res) => ({
      ...res,
      currentWeight: Number(res.currentWeight),
      calculatedImc: res.calculatedImc ? Number(res.calculatedImc) : null,
    }));
  }
}
