/* eslint-disable @typescript-eslint/no-unsafe-assignment */
import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import * as amqp from 'amqplib';
import { v4 as uuidv4 } from 'uuid';
import {
  IClassificationPayload,
  IClassificationResponse,
} from './interfaces/classification-payload.interface';

@Injectable()
export class RabbitmqService implements OnModuleInit, OnModuleDestroy {
  private connection: amqp.ChannelModel;
  private channel: amqp.Channel;

  async onModuleInit() {
    this.connection = await amqp.connect({
      hostname: process.env.RABBITMQ_HOST,
      port: Number(process.env.RABBITMQ_PORT),
      username: process.env.RABBITMQ_USER,
      password: process.env.RABBITMQ_PASSWORD,
      vhost: process.env.RABBITMQ_VHOST,
    });
    this.channel = await this.connection.createChannel();
  }

  async onModuleDestroy() {
    await this.channel.close();
    await this.connection.close();
  }

  async classificarGestante(
    dados: IClassificationPayload,
  ): Promise<IClassificationResponse> {
    const { queue: replyQueue } = await this.channel.assertQueue('', {
      exclusive: true,
      autoDelete: true,
    });

    const correlationId = uuidv4();

    this.channel.sendToQueue(
      'maternar.classificar',
      Buffer.from(JSON.stringify(dados)),
      {
        correlationId,
        replyTo: replyQueue,
        contentType: 'application/json',
      },
    );

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Timeout: worker não respondeu em 10s'));
      }, 10000);

      this.channel
        .consume(
          replyQueue,
          (msg) => {
            if (msg?.properties.correlationId === correlationId) {
              clearTimeout(timeout);
              const resultado = JSON.parse(msg.content.toString());
              resolve(resultado);
            }
          },
          { noAck: true },
        )
        .catch((err) => {
          clearTimeout(timeout);
          reject(err instanceof Error ? err : new Error(String(err)));
        });
    });
  }
}
