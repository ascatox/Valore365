import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { expressJwtSecret } from 'jwks-rsa';
import { promisify } from 'util';
import * as jwt from 'jsonwebtoken';

@Injectable()
export class AuthGuard implements CanActivate {
  private readonly clerkJwksUrl: string;

  constructor(private readonly configService: ConfigService) {
    this.clerkJwksUrl = this.configService.get<string>('CLERK_JWKS_URL';
  }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest();
    const token = this.extractTokenFromHeader(request);

    if (!token) {
      throw new UnauthorizedException('No token provided');
    }

    try {
      const decoded = await this.verifyToken(token);
      request.user = decoded;
    } catch (error) {
      throw new UnauthorizedException('Invalid token');
    }

    return true;
  }

  private extractTokenFromHeader(request: any): string | undefined {
    const [type, token] = request.headers.authorization?.split(' ') ?? [];
    return type === 'Bearer' ? token : undefined;
  }

  private async verifyToken(token: string): Promise<any> {
    const getKey = promisify(expressJwtSecret({ jwksUri: this.clerkJwksUrl, cache: true, rateLimit: true }));
    const publicKey = await getKey(jwt.decode(token, { complete: true }).header);
    return jwt.verify(token, publicKey);
  }
}
