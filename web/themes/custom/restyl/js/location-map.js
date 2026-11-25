(function (Drupal, once) {
  Drupal.behaviors.restylLocationMap = {
    attach(context) {
      once('restylLocationMap', '.site-location-map__canvas', context).forEach((container) => {
        const latitude = Number(container.dataset.latitude);
        const longitude = Number(container.dataset.longitude);

        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          console.error('Invalid coordinates for the RESTYL location map.');
          return;
        }

        if (!window.L) {
          const fallback = document.createElement('p');
          const link = document.createElement('a');
          fallback.className = 'site-location-map__fallback';
          link.href = 'https://www.google.com/maps?q=50.7333270%2C15.0560791';
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = 'Otevřít adresu společnosti RESTYL v Google Maps';
          fallback.append(link);
          container.replaceChildren(fallback);
          console.error('Leaflet did not load for the RESTYL location map.');
          return;
        }

        const map = window.L.map(container, { scrollWheelZoom: false })
          .setView([latitude, longitude], 14);

        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 19,
        }).addTo(map);

        const marker = window.L.marker([latitude, longitude], {
          alt: 'RESTYL, Hodkovická 669, Liberec',
          icon: window.L.divIcon({
            className: 'site-location-map__marker-icon',
            html: '<span class="site-location-map__marker-mark" aria-hidden="true"><span></span><span></span><span></span></span>',
            iconSize: [102, 102],
            iconAnchor: [51, 51],
          }),
          title: 'RESTYL, Hodkovická 669, Liberec',
        }).addTo(map);

        marker.bindPopup('RESTYL<br>Hodkovická 669, Liberec XXIII-Doubí');
      });
    },
  };
})(Drupal, once);
