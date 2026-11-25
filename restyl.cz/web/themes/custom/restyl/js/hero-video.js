(function () {
  const theme = document.querySelector('[data-restyl-theme-path]');
  const layers = document.querySelectorAll(
    '.rev_slider_wrapper .rs-background-video-layer, .layout-container:has(#user-login-form) .page-title-band',
  );
  if (!theme || !layers.length) {
    return;
  }

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const updateVideo = (layer) => {
    const existing = layer.querySelector('video');
    if (reducedMotion.matches) {
      if (existing) {
        existing.pause();
        existing.remove();
      }
      return;
    }
    if (existing) {
      return;
    }

    const video = document.createElement('video');
    video.autoplay = true;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.setAttribute('aria-hidden', 'true');
    video.addEventListener('playing', () => {
      video.classList.add('is-playing');
    });
    video.addEventListener('pause', () => {
      video.classList.remove('is-playing');
    });
    ['webm', 'mp4'].forEach((format) => {
      const source = document.createElement('source');
      source.src = `${theme.dataset.restylThemePath}/images/home-hero.${format}`;
      source.type = `video/${format}`;
      video.appendChild(source);
    });
    video.addEventListener('error', () => {
      console.warn('RESTYL: Úvodní video nelze načíst; zobrazuje se náhradní obrázek.');
    });
    layer.appendChild(video);
  };

  const updateVideos = () => {
    layers.forEach(updateVideo);
  };

  updateVideos();
  reducedMotion.addEventListener('change', updateVideos);
})();
