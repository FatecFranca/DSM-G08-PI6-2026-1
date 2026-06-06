import { Module } from '@nestjs/common';
import { PregnancyModule } from '../pregnancies/pregnancy.module';
import { DatabaseModule } from '../database/database.module';
import { QuestionnaireService } from './application/questionnaire.service';
import { QuestionnaireController } from './http/questionnaire.controller';
import { RabbitmqModule } from '../integrations/rabbitmq/rabbitmq.module';

@Module({
  imports: [PregnancyModule, DatabaseModule, RabbitmqModule],
  controllers: [QuestionnaireController],
  providers: [QuestionnaireService],
})
export class QuestionnaireModule {}
