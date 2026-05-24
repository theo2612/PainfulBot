"""Cloudflare Access JWT verification.

Cloudflare Access fronts protected routes with an authentication challenge
(Google, OTP email, etc.) and, once the user passes, sets a signed JWT on every
request to the origin — both as the `Cf-Access-Jwt-Assertion` header and the
`CF_Authorization` cookie. Origin code verifies the JWT against Cloudflare's
public JWKS to confirm the request is from an authorized human.

Docs: https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
"""

import logging
from typing import Optional

import jwt
from jwt import PyJWKClient

log = logging.getLogger('cf_access')


class CFAccessVerifier:
    def __init__(self, team_domain: str, aud: str):
        self.team_domain = team_domain.strip().rstrip('/').replace('https://', '')
        self.aud = aud.strip()
        self.issuer = f'https://{self.team_domain}'
        self.jwks_url = f'{self.issuer}/cdn-cgi/access/certs'
        # PyJWKClient caches keys and refreshes on miss; 1h lifespan is fine
        # since CF rotates keys roughly every 6 weeks.
        self._jwks_client = PyJWKClient(self.jwks_url, lifespan=3600)

    def verify(self, token: Optional[str]) -> Optional[dict]:
        """Return claims dict on success, None on any failure (expired, bad
        signature, wrong audience, wrong issuer, malformed)."""
        if not token:
            return None
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=['RS256'],
                audience=self.aud,
                issuer=self.issuer,
            )
        except Exception as e:
            log.warning('CF Access verify failed: %s', e)
            return None
