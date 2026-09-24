# Authentification Keycloak dans une app CNP

Guide développeur du service d'authentification Keycloak injectable dans les apps
CNP ([ADR-0026](../adr/0026-keycloak-app-auth.md)). S'adresse aux équipes qui
activent Keycloak sur leur app — scaffoldée ou importée (onboarded) — et veulent
savoir quelles variables leur arrivent, comment administrer leur realm, et comment
valider un token côté code.

## Fonctionnement

- **Un realm Keycloak par app et par environnement** : `{app_slug}-dev` et
  `{app_slug}-prod`, sur l'instance Keycloak partagée de la plateforme
  (`{KEYCLOAK_PUBLIC_URL}`). Réaliser une action en dev (créer un user de test,
  changer un rôle) n'a aucun impact sur le realm prod, et inversement.
- **Un client par app** dans chaque realm, portant le nom du `slug` de l'app :
  *public* + PKCE si votre app est une SPA (template `react-vite`), *confidential*
  (avec `client_secret`) sinon.
- **Console d'admin déléguée** : `{KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/`.
  Un membre Owner/Maintainer de l'app peut s'y connecter pour administrer *ce realm
  uniquement* (créer des users, ajuster des rôles, personnaliser le thème de login…)
  — jamais les autres realms de la plateforme.
- **Accès console V1** : compte local au realm, mot de passe temporaire à usage
  unique (`UPDATE_PASSWORD` requis à la première connexion). Le login fédéré via
  GitLab (SSO) est une évolution future, pas encore disponible.
- **Recréation d'un realm supprimé : jamais automatique.** Si le realm est
  supprimé (volontairement via la console, ou par erreur), CNP ne le recrée pas de
  lui-même — il détecte l'absence (`status: missing`) et affiche un bouton
  "Recréer" (portail) ou la commande `cnp keycloak reprovision` (CLI). Recréer
  produit un realm **vierge** : nouveaux users, nouveau `client_secret`, aucune
  récupération des anciennes données. En dev, Owner ou Maintainer peuvent recréer ;
  en prod, Owner uniquement.

## Activer Keycloak sur votre app

- **À la création** : cocher "Authentication" à l'étape Services du wizard, ou
  `cnp app scaffold --keycloak` / `cnp app onboard --keycloak`.
- **Après coup** sur une app existante : bouton "Activate Keycloak" dans l'onglet
  Settings du portail, ou `cnp keycloak enable --app <slug>` (Owner/Maintainer).
  Provisionne dev **et** prod en une fois.

## Variables injectées

Une fois le realm provisionné, ces clés apparaissent dans les variables
d'environnement de votre app (mêmes onglets dev/prod que le reste des variables,
badge **"managed by CNP"** — non modifiables manuellement, l'API refuse toute
tentative avec un `409`) :

| Variable              | Présente pour                  | Description |
|------------------------|--------------------------------|--------------|
| `OIDC_ISSUER_URL`      | tous les clients                | `{KEYCLOAK_PUBLIC_URL}/realms/{app_slug}-{env}` — URL du realm, sert aussi de base à la découverte OIDC (`{issuer}/.well-known/openid-configuration`) et aux JWKS (`{issuer}/protocol/openid-connect/certs`) |
| `OIDC_CLIENT_ID`       | tous les clients                | = `{app_slug}` |
| `OIDC_CLIENT_SECRET`   | clients confidential uniquement | absent pour un client public (SPA) — PKCE ne l'utilise pas |

Ces variables transitent **uniquement par Vault** (`secret/apps/{group}/{app}/{env}`,
même secret que vos propres variables d'environnement, ADR-0025) puis par ESO vers le
`Secret` Kubernetes `{app_slug}-env` de votre namespace — jamais en clair dans un
repo git.

## Prérequis côté chart Helm

Pour que ces variables atteignent réellement votre pod, le `Deployment` de votre
chart doit consommer le Secret `{app_slug}-env` via `envFrom`, et porter l'annotation
Stakater Reloader pour redémarrer le pod quand ce Secret change :

```yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"   # sur le Deployment, pas le pod template
spec:
  template:
    spec:
      containers:
        - name: ...
          envFrom:
            - secretRef:
                name: {{ include "app.name" . }}-env   # = {app_slug}-env
                optional: true   # le pod démarre même si Vault/ESO n'ont encore rien synchronisé
          env: ...   # vos variables existantes, inchangées
```

**Apps scaffoldées** (`cnp-templates/{python-fastapi,node-express,go,react-vite}`) :
déjà en place dans le chart depuis la correction 4K-15 Lot 1b — rien à faire, sauf si
votre app a été scaffoldée **avant** ce correctif (le template n'est copié qu'une
fois) : ajoutez le bloc ci-dessus vous-même dans `chart/templates/deployment.yaml`.

**Apps importées (onboarded)** : CNP ne réécrit pas votre chart. Au provisioning, une
vérification best-effort cherche `envFrom` référençant `{app_slug}-env` dans
`chart/templates/*.yaml` de votre repo ; si elle échoue, un avertissement
`chart_missing_envfrom` apparaît dans le portail (onglet Settings) et via
`cnp keycloak status` — ajoutez le bloc ci-dessus vous-même pour le faire
disparaître. Aucune MR automatique n'est ouverte pour vous (V1).

## Valider un token côté code

Un access token Keycloak a par défaut `aud: account` — inutilisable pour une
validation locale stricte. Le realm de votre app est configuré automatiquement avec
un protocol mapper `audience` qui force `aud` à contenir `OIDC_CLIENT_ID` : vérifiez
toujours `iss`, `aud` et `exp`, jamais seulement la signature.

### Python / FastAPI

```python
import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

issuer = os.environ["OIDC_ISSUER_URL"]
client_id = os.environ["OIDC_CLIENT_ID"]
jwks_client = PyJWKClient(f"{issuer}/protocol/openid-connect/certs")
bearer = HTTPBearer()

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(creds.credentials)
        return jwt.decode(
            creds.credentials, signing_key.key,
            algorithms=["RS256"], audience=client_id, issuer=issuer,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
```

(Implémentation complète, dormante par défaut : `src/auth.py` du template
`cnp-templates/python-fastapi`.)

### Node.js / Express

```js
import { createRemoteJWKSet, jwtVerify } from "jose";

const issuer = process.env.OIDC_ISSUER_URL;
const clientId = process.env.OIDC_CLIENT_ID;
const jwks = createRemoteJWKSet(new URL(`${issuer}/protocol/openid-connect/certs`));

export async function requireAuth(req, res, next) {
  const [scheme, token] = (req.headers.authorization || "").split(" ");
  if (scheme !== "Bearer" || !token) return res.status(401).json({ error: "Not authenticated" });
  try {
    const { payload } = await jwtVerify(token, jwks, { issuer, audience: clientId });
    req.user = payload;
    next();
  } catch (err) {
    res.status(401).json({ error: `Invalid token: ${err.message}` });
  }
}
```

(Implémentation complète : `src/auth.js` du template `cnp-templates/node-express`.)

### Go

```go
import "github.com/coreos/go-oidc/v3/oidc"

provider, err := oidc.NewProvider(ctx, os.Getenv("OIDC_ISSUER_URL"))
verifier := provider.Verifier(&oidc.Config{ClientID: os.Getenv("OIDC_CLIENT_ID")})

idToken, err := verifier.Verify(ctx, bearerToken)   // vérifie iss/aud/exp/signature
var claims map[string]any
_ = idToken.Claims(&claims)
```

(Implémentation complète : `auth.go` du template `cnp-templates/go` — la découverte
OIDC est faite en lazy, à la première requête authentifiée, pas au démarrage du
process.)

### Java / Spring Boot

Avec `spring-boot-starter-oauth2-resource-server` :

```properties
# application.properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${OIDC_ISSUER_URL}
```

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

Spring résout automatiquement le JWKS et vérifie `iss`/`exp`/signature depuis
`issuer-uri`. Ajoutez un validateur d'audience explicite (Spring ne le fait pas par
défaut) :

```java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(System.getenv("OIDC_ISSUER_URL"));
    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(System.getenv("OIDC_ISSUER_URL")),
        new JwtClaimValidator<List<String>>("aud", aud -> aud.contains(System.getenv("OIDC_CLIENT_ID")))
    ));
    return decoder;
}
```

### SPA (React, ou tout front statique)

Le template `react-vite` embarque déjà [`oidc-client-ts`](https://github.com/authts/oidc-client-ts)
(Authorization Code + PKCE, client public) — voir `src/auth.js`. Points clés si vous
partez d'un autre starter :

```js
import { UserManager, WebStorageStateStore } from "oidc-client-ts";

const userManager = new UserManager({
  authority: window.__CNP_AUTH_CONFIG__.oidcIssuerUrl,  // config *runtime*, pas build-time
  client_id: window.__CNP_AUTH_CONFIG__.oidcClientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  response_type: "code",
  scope: "openid profile email",
  userStore: new WebStorageStateStore({ store: window.localStorage }),
});

await userManager.signinRedirect();   // login
await userManager.getUser();          // session courante
```

**Important** : `OIDC_ISSUER_URL`/`OIDC_CLIENT_ID` ne doivent **pas** être lus via
une variable d'environnement figée au build (`import.meta.env.*`) — le même artefact
JS est déployé en dev et en prod, avec des realms différents. Le template
`react-vite` génère un `config.js` **au démarrage du conteneur** (script
`docker-entrypoint.sh`, avant que nginx serve quoi que ce soit) à partir des
variables d'environnement du pod, chargé par `index.html` avant le bundle React.

## CLI

```bash
cnp keycloak status --app <slug>              # statut dev + prod
cnp keycloak enable --app <slug>              # activer sur une app existante
cnp keycloak console --app <slug> --env dev   # accès console temporaire (une fois)
cnp keycloak reprovision --app <slug> --env dev --yes  # recréer un realm supprimé
```

Voir [la référence CLI](../cli.md#authentification-keycloak-cnp-keycloak-4k-15-adr-0026)
pour le détail des options.

## Limites connues (V1)

- Pas de SSO GitLab pour la console Keycloak (mot de passe temporaire uniquement).
- Mode "credentials + doc" pour les apps importées (mode A) : aucune vérification
  que votre code valide réellement les tokens, seule la présence d'`envFrom` dans le
  chart est vérifiée (best-effort, avertissement seulement).
- Pas d'instance Keycloak dédiée par app — une instance partagée pour toute la
  plateforme (voir [ADR-0026](../adr/0026-keycloak-app-auth.md) pour la justification
  et les évolutions envisagées).
