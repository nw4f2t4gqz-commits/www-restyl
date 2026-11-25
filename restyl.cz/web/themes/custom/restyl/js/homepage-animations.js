(function () {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const carousel = document.querySelector('.site-main .owl-carousel');

  if (carousel) {
    const slides = Array.from(carousel.children).filter((slide) => slide.matches('li.row'));

    if (slides.length > 1) {
      let hovered = false;
      let focused = false;

      carousel.tabIndex = 0;
      carousel.setAttribute('aria-label', 'Vedení firmy');
      carousel.addEventListener('mouseenter', () => {
        hovered = true;
      });
      carousel.addEventListener('mouseleave', () => {
        hovered = false;
      });
      carousel.addEventListener('focusin', () => {
        focused = true;
      });
      carousel.addEventListener('focusout', (event) => {
        if (!carousel.contains(event.relatedTarget)) {
          focused = false;
        }
      });

      window.setInterval(() => {
        const maxScroll = carousel.scrollWidth - carousel.clientWidth;
        if (document.hidden || hovered || focused || reducedMotion.matches || maxScroll <= 1) {
          return;
        }

        const atEnd = carousel.scrollLeft >= maxScroll - 1;
        carousel.scrollTo({
          left: atEnd ? 0 : Math.min(carousel.scrollLeft + carousel.clientWidth, maxScroll),
          behavior: 'smooth',
        });
      }, 4000);
    }
  }

  if (reducedMotion.matches) {
    return;
  }

  const counters = Array.from(document.querySelectorAll('.site-main h2 > span')).filter((counter) => {
    return /^\d+$/.test(counter.textContent.trim())
      && counter.parentElement?.nextElementSibling?.matches('h4');
  });

  if (!counters.length) {
    return;
  }

  const durations = [1000, 2000, 3000];
  const counterTargets = new Map();
  const animateCounter = (counter, target, duration) => {
    const startTime = performance.now();
    const update = (now) => {
      if (reducedMotion.matches) {
        counter.textContent = String(target);
        return;
      }

      const progress = Math.min((now - startTime) / duration, 1);
      const easedProgress = 1 - ((1 - progress) ** 3);
      counter.textContent = String(Math.round(target * easedProgress));

      if (progress < 1) {
        window.requestAnimationFrame(update);
      } else {
        counter.textContent = String(target);
      }
    };

    window.requestAnimationFrame(update);
  };

  counters.forEach((counter, index) => {
    const target = Number(counter.textContent.trim());
    if (!Number.isSafeInteger(target) || target < 0) {
      return;
    }

    counterTargets.set(counter, {
      target,
      duration: durations[index] || 2000,
    });
    counter.textContent = '0';
  });

  if (!('IntersectionObserver' in window)) {
    counterTargets.forEach(({ target, duration }, counter) => {
      animateCounter(counter, target, duration);
    });
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      const counter = entry.target;
      const { target, duration } = counterTargets.get(counter);
      observer.unobserve(counter);
      animateCounter(counter, target, duration);
    });
  }, { threshold: 0.25 });

  counterTargets.forEach((_value, counter) => {
    observer.observe(counter);
  });
})();
