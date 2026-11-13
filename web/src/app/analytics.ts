import { useEffect } from "react";
import { useLocation } from "react-router-dom";

declare global {
  interface Window {
    dataLayer?: Record<string, unknown>[];
  }
}

const GTM_ID = import.meta.env.VITE_GTM_ID?.trim() ?? "";
const GTM_SCRIPT_ID = "gtm-script";

export const analyticsEnabled =
  GTM_ID !== "" && import.meta.env.VITE_ANALYTICS_ENABLED?.trim() === "true";

export function initAnalytics() {
  if (!analyticsEnabled || document.getElementById(GTM_SCRIPT_ID)) {
    return;
  }

  const dataLayer = (window.dataLayer = window.dataLayer ?? []);
  dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });

  const script = document.createElement("script");
  script.id = GTM_SCRIPT_ID;
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtm.js?id=${GTM_ID}`;
  document.head.appendChild(script);
}

export function trackPageView(pagePath: string) {
  if (!analyticsEnabled) {
    return;
  }

  window.dataLayer?.push({
    event: "page_view",
    page_path: pagePath,
    page_location: window.location.href,
    page_title: document.title,
  });
}

export function usePageViews() {
  const { pathname, search } = useLocation();

  useEffect(() => {
    trackPageView(`${pathname}${search}`);
  }, [pathname, search]);
}
