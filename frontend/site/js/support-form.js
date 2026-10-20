/**
 * DataVerse Product Website — Support & Feedback Form Handler (support-form.js)
 * Formspree Endpoint: https://formspree.io/f/xzedwwlv
 * Form Name: DataVerse
 */

import { trackSupportSubmitted } from './analytics.js';

const FORMSPREE_ENDPOINT = 'https://formspree.io/f/xzedwwlv';

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('support-form');
  const alertSuccess = document.getElementById('form-alert-success');
  const alertError = document.getElementById('form-alert-error');
  const submitBtn = document.getElementById('btn-submit-support');

  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Reset alert states
    if (alertSuccess) alertSuccess.style.display = 'none';
    if (alertError) alertError.style.display = 'none';

    // 1. Client-side Validation
    let hasError = false;

    // Email validation
    const emailInput = form.querySelector('[name="email"]');
    const emailGroup = emailInput?.closest('.form-group');
    const emailVal = (emailInput?.value || '').trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!emailVal || !emailRegex.test(emailVal)) {
      emailGroup?.classList.add('has-error');
      hasError = true;
    } else {
      emailGroup?.classList.remove('has-error');
    }

    // Category validation
    const categorySelect = form.querySelector('[name="category"]');
    const categoryGroup = categorySelect?.closest('.form-group');
    const categoryVal = (categorySelect?.value || '').trim();

    if (!categoryVal) {
      categoryGroup?.classList.add('has-error');
      hasError = true;
    } else {
      categoryGroup?.classList.remove('has-error');
    }

    // Message validation
    const messageInput = form.querySelector('[name="message"]');
    const messageGroup = messageInput?.closest('.form-group');
    const messageVal = (messageInput?.value || '').trim();

    if (!messageVal || messageVal.length < 5) {
      messageGroup?.classList.add('has-error');
      hasError = true;
    } else {
      messageGroup?.classList.remove('has-error');
    }

    // Honeypot anti-spam check
    const honeypot = form.querySelector('[name="_gotcha"]');
    if (honeypot && honeypot.value) {
      // Silently discard spam bots
      if (alertSuccess) {
        alertSuccess.textContent = "Thank you! Your feedback has been received.";
        alertSuccess.style.display = 'block';
      }
      form.reset();
      return;
    }

    if (hasError) {
      const firstError = form.querySelector('.has-error input, .has-error select, .has-error textarea');
      firstError?.focus();
      return;
    }

    // 2. Submit via Fetch to Formspree
    const originalBtnText = submitBtn ? submitBtn.innerHTML : 'Send Message';
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.setAttribute('aria-disabled', 'true');
      submitBtn.innerHTML = `
        <svg class="spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
          <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
          <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path>
        </svg>
        <span>Sending Message...</span>
      `;
    }

    try {
      const formData = new FormData(form);

      const response = await fetch(FORMSPREE_ENDPOINT, {
        method: 'POST',
        body: formData,
        headers: {
          'Accept': 'application/json'
        }
      });

      if (response.ok) {
        // Success
        if (alertSuccess) {
          alertSuccess.style.display = 'flex';
          alertSuccess.focus();
        }
        form.reset();
        trackSupportSubmitted(categoryVal);
      } else {
        const data = await response.json().catch(() => ({}));
        const errorMsg = (data.errors && data.errors.map(err => err.message).join(', ')) ||
                         data.error ||
                         'Unable to send message to Formspree. Please verify your connection or try again.';
        if (alertError) {
          alertError.textContent = errorMsg;
          alertError.style.display = 'flex';
          alertError.focus();
        }
      }
    } catch (err) {
      if (alertError) {
        alertError.textContent = 'A network error occurred while reaching Formspree. Please check your internet connection.';
        alertError.style.display = 'flex';
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.removeAttribute('aria-disabled');
        submitBtn.innerHTML = originalBtnText;
      }
    }
  });

  // Clear validation on input
  form.querySelectorAll('input, select, textarea').forEach(input => {
    input.addEventListener('input', () => {
      input.closest('.form-group')?.classList.remove('has-error');
    });
  });
});
