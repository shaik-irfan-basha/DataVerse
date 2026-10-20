/**
 * DataVerse Product Website — Google Analytics 4 (GA4) Integration (analytics.js)
 * Measurement ID: G-H7BHJ4W523
 *
 * PRIVACY & SECURITY INVARIANT:
 * Under NO circumstance are personal names, email addresses, uploaded file contents,
 * database schema names, user query texts, generated SQL, or API keys sent to Google Analytics.
 * Only anonymized structural event names and coarse categories are recorded.
 */

const GA_MEASUREMENT_ID = 'G-H7BHJ4W523';

(function initGoogleAnalytics() {
  if (window.__dv_ga_initialized) return;
  window.__dv_ga_initialized = true;

  // Initialize dataLayer
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = gtag;

  gtag('js', new Date());
  gtag('config', GA_MEASUREMENT_ID, {
    anonymize_ip: true,
    send_page_view: true
  });

  // Inject gtag.js script if not already present
  if (!document.querySelector(`script[src*="${GA_MEASUREMENT_ID}"]`)) {
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
    document.head.appendChild(script);
  }
})();

/**
 * Privacy-safe custom event helper.
 * Strips all personal, file, query, or SQL parameters.
 */
export function trackEvent(eventName, params = {}) {
  if (typeof window.gtag === 'function') {
    // Whitelist safe event names and attributes only
    const sanitizedParams = {
      event_category: String(params.event_category || 'general').slice(0, 50),
      event_label: String(params.event_label || '').slice(0, 50),
      transport_type: 'beacon'
    };
    window.gtag('event', eventName, sanitizedParams);
  }
}

export function trackDemoLaunch(source = 'hero') {
  trackEvent('demo_launched', { event_category: 'engagement', event_label: source });
}

export function trackDownloadClick(fileType = 'installer') {
  trackEvent('download_installer_clicked', { event_category: 'downloads', event_label: fileType });
}

export function trackSupportSubmitted(category = 'general') {
  trackEvent('support_form_submitted', { event_category: 'support', event_label: category });
}

// Bind clicks on standard data-track elements
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-track="demo-launch"]').forEach(el => {
    el.addEventListener('click', () => {
      const source = el.getAttribute('data-track-source') || 'button';
      trackDemoLaunch(source);
    });
  });

  document.querySelectorAll('[data-track="download-installer"]').forEach(el => {
    el.addEventListener('click', () => {
      trackDownloadClick('v1.0-exe');
    });
  });
});
