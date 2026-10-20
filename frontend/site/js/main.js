/**
 * DataVerse Product Website — Main Interactive Script (main.js)
 * Handles mobile drawer toggle, FAQ accordions, and header scroll state.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Mobile Menu Toggle
  const header = document.querySelector('.site-header');
  const menuToggle = document.querySelector('.menu-toggle');

  if (menuToggle && header) {
    menuToggle.addEventListener('click', () => {
      const isOpen = header.classList.toggle('menu-open');
      menuToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

    // Close on navigation click
    header.querySelectorAll('.site-nav a').forEach(link => {
      link.addEventListener('click', () => {
        header.classList.remove('menu-open');
        menuToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // 2. FAQ Accordion Handling
  const faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(item => {
    const questionBtn = item.querySelector('.faq-question');
    if (questionBtn) {
      questionBtn.addEventListener('click', () => {
        const isOpen = item.classList.contains('open');

        // Close all other open items for clean reading
        faqItems.forEach(other => {
          if (other !== item) {
            other.classList.remove('open');
            const otherBtn = other.querySelector('.faq-question');
            if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
          }
        });

        // Toggle current
        item.classList.toggle('open', !isOpen);
        questionBtn.setAttribute('aria-expanded', !isOpen ? 'true' : 'false');
      });
    }
  });

  // 3. Header Scroll Shadow
  window.addEventListener('scroll', () => {
    if (window.scrollY > 20) {
      header?.classList.add('scrolled');
    } else {
      header?.classList.remove('scrolled');
    }
  }, { passive: true });
});
