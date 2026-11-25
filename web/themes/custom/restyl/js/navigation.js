(function () {
  const menu = document.querySelector('.site-navigation__disclosure');
  if (!menu) {
    return;
  }

  const desktop = window.matchMedia('(min-width: 1200px)');
  const updateMenu = () => {
    menu.open = desktop.matches;
  };

  updateMenu();
  desktop.addEventListener('change', updateMenu);
})();
