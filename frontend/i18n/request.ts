import { getRequestConfig } from 'next-intl/server';
import { cookies, headers } from 'next/headers';
import { defaultLocale, locales, type Locale } from './config';

export default getRequestConfig(async () => {
  // Try to get locale from cookie first (user preference)
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get('NEXT_LOCALE')?.value as Locale | undefined;

  if (cookieLocale && locales.includes(cookieLocale)) {
    return {
      locale: cookieLocale,
      messages: (await import(`../messages/${cookieLocale}.json`)).default,
    };
  }

  // Fall back to browser Accept-Language header
  const headersList = await headers();
  const acceptLanguage = headersList.get('accept-language') || '';

  // Parse Accept-Language header and find best match
  const browserLocales = acceptLanguage
    .split(',')
    .map((lang) => {
      const [locale, q = '1'] = lang.trim().split(';q=');
      return { locale: locale.trim(), quality: parseFloat(q) };
    })
    .sort((a, b) => b.quality - a.quality);

  for (const { locale: browserLocale } of browserLocales) {
    // Check exact match
    if (locales.includes(browserLocale as Locale)) {
      return {
        locale: browserLocale as Locale,
        messages: (await import(`../messages/${browserLocale}.json`)).default,
      };
    }
    // Check language prefix match (e.g., 'zh' -> 'zh-CN')
    const langPrefix = browserLocale.split('-')[0];
    const matchedLocale = locales.find((l) => l.startsWith(langPrefix));
    if (matchedLocale) {
      return {
        locale: matchedLocale,
        messages: (await import(`../messages/${matchedLocale}.json`)).default,
      };
    }
  }

  // Default fallback
  return {
    locale: defaultLocale,
    messages: (await import(`../messages/${defaultLocale}.json`)).default,
  };
});
