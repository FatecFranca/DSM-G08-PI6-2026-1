import { HttpStatus, Injectable } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ApiException } from '../../common/api-exception';
import { UserService } from '../../users/application/user.service';
import { AuthenticatedUserPayload } from '../domain/auth.types';
import { LoginLocalDto } from '../http/auth.dto';
import * as bcrypt from 'bcrypt';

@Injectable()
export class AuthService {
  private readonly jwtExpirationTimeInSeconds = 604800;

  constructor(
    private readonly userService: UserService,
    private readonly jwtService: JwtService,
  ) {}

  async signIn({ email, password }: LoginLocalDto) {
    const user = await this.userService.findUserByEmail(email);

    if (!user || !(await bcrypt.compare(password, user.password))) {
      throw new ApiException(
        HttpStatus.UNAUTHORIZED,
        'INVALID_CREDENTIALS',
        'Credenciais inválidas.',
      );
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { password: _, ...safeUser } = user;

    const jwtPayload: Omit<AuthenticatedUserPayload, 'iat' | 'exp'> = {
      sub: safeUser.id,
      email: safeUser.email,
      name: safeUser.name,
    };

    const token = await this.jwtService.signAsync(jwtPayload, {
      expiresIn: this.jwtExpirationTimeInSeconds,
    });

    return { access_token: token, expiresIn: this.jwtExpirationTimeInSeconds };
  }
}
