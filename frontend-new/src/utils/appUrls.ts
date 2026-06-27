const CNP_BASE_DOMAIN = 'cloud-native-plat4k.me';

export function appUrl(slug: string, env: 'dev' | 'prod'): string {
  return env === 'prod'
    ? `https://${slug}.${CNP_BASE_DOMAIN}`
    : `https://dev.${slug}.${CNP_BASE_DOMAIN}`;
}
