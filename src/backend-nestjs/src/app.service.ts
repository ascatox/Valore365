import { Injectable } from '@nestjs/common';

@Injectable()
export class AppService {
  health(): { status: string } {
    return { status: 'ok' };
  }
}
