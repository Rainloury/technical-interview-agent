package top.rainstone.technicalinterviewagent;

import android.net.Uri;

final class AppConfig {
    static final String SITE_URL = "https://it.rainstone.top";
    static final String SITE_HOST = "it.rainstone.top";
    static final String SITE_SCHEME = "https";

    private AppConfig() {}

    static boolean isSiteUri(Uri uri) {
        return uri != null && isSiteUrl(uri.toString());
    }

    static String siteUrlForIntent(Uri uri) {
        return uri == null ? SITE_URL + "/" : siteUrlForPath(uri.toString());
    }

    static boolean isSiteUrl(String rawUrl) {
        UrlParts parts = UrlParts.parse(rawUrl);
        return parts != null
                && SITE_SCHEME.equalsIgnoreCase(parts.scheme)
                && SITE_HOST.equalsIgnoreCase(parts.host);
    }

    static String siteUrlForPath(String rawUrl) {
        UrlParts parts = UrlParts.parse(rawUrl);
        if (parts == null || !SITE_SCHEME.equalsIgnoreCase(parts.scheme)
                || !SITE_HOST.equalsIgnoreCase(parts.host)
                || parts.path.isEmpty()
                || "/".equals(parts.path)) {
            return SITE_URL + "/";
        }
        return SITE_URL + parts.path + parts.querySuffix;
    }

    static final class UrlParts {
        final String scheme;
        final String host;
        final String path;
        final String querySuffix;

        private UrlParts(String scheme, String host, String path, String querySuffix) {
            this.scheme = scheme;
            this.host = host;
            this.path = path;
            this.querySuffix = querySuffix;
        }

        static UrlParts parse(String rawUrl) {
            if (rawUrl == null) {
                return null;
            }
            int schemeEnd = rawUrl.indexOf("://");
            if (schemeEnd <= 0) {
                return null;
            }
            String scheme = rawUrl.substring(0, schemeEnd);
            int authorityStart = schemeEnd + 3;
            int authorityEnd = rawUrl.length();
            for (char delimiter : new char[] {'/', '?', '#'}) {
                int index = rawUrl.indexOf(delimiter, authorityStart);
                if (index >= 0 && index < authorityEnd) {
                    authorityEnd = index;
                }
            }
            String authority = rawUrl.substring(authorityStart, authorityEnd);
            int at = authority.lastIndexOf('@');
            String hostAndPort = at >= 0 ? authority.substring(at + 1) : authority;
            String host = hostAndPort;
            int port = hostAndPort.lastIndexOf(':');
            if (port > 0 && hostAndPort.indexOf(':') == port) {
                host = hostAndPort.substring(0, port);
            }
            String remainder = rawUrl.substring(authorityEnd);
            int fragment = remainder.indexOf('#');
            if (fragment >= 0) {
                remainder = remainder.substring(0, fragment);
            }
            int query = remainder.indexOf('?');
            String path = query >= 0 ? remainder.substring(0, query) : remainder;
            String querySuffix = query >= 0 ? remainder.substring(query) : "";
            return new UrlParts(scheme, host, path, querySuffix);
        }
    }
}
