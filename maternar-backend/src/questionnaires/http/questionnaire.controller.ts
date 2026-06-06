import {
  Body,
  Controller,
  Get,
  Param,
  ParseUUIDPipe,
  Post,
  UseGuards,
} from '@nestjs/common';
import { QuestionnaireService } from '../application/questionnaire.service';
import { JwtAuthGuard } from '../../auth/http/guards/jwt-auth.guard';
import { CreateQuestionnaireDto } from './questionnaire.dto';
import { CurrentUser } from '../../auth/http/decorators/current-user.decorator';

@Controller('questionnaires')
export class QuestionnaireController {
  constructor(private readonly questionnaireService: QuestionnaireService) {}

  @Post(':pregnancyId/submit')
  @UseGuards(JwtAuthGuard)
  async submit(
    @CurrentUser('sub') userId: string,
    @Param('pregnancyId', ParseUUIDPipe) pregnancyId: string,
    @Body() dto: CreateQuestionnaireDto,
  ) {
    return this.questionnaireService.submitQuestionnaire(
      userId,
      pregnancyId,
      dto,
    );
  }

  @Get('pregnancy/:pregnancyId')
  @UseGuards(JwtAuthGuard)
  async findAllByPregnancy(
    @CurrentUser('sub') userId: string,
    @Param('pregnancyId', ParseUUIDPipe) pregnancyId: string,
  ) {
    return this.questionnaireService.findAllByPregnancy(userId, pregnancyId);
  }
}
