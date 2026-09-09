/* PUBLIC PAGES - view loading and navigation */
(function () {
  let landingLoaded = false;
  let rulesLoaded = false;
  const routeMap = {
    landing: '/',
    login: '/login',
    rules: '/regras-planner',
    dashboard: '/dashboard',
    teams: '/equipes',
    library: '/biblioteca',
  };
  const get = id => document.getElementById(id);
  const show = element => element?.classList.remove('hidden');
  const hide = element => element?.classList.add('hidden');

  window.hidePublicViews = function () {
    hide(get('landingView'));
    hide(get('rulesView'));
    hide(get('landingScreen'));
    hide(get('rulesScreen'));
  };

  function currentRoute() {
    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    if (path === routeMap.login) return 'login';
    if (path === routeMap.rules) return 'rules';
    if (path === routeMap.dashboard) return 'dashboard';
    if (path === routeMap.teams) return 'teams';
    if (path === routeMap.library) return 'library';
    return 'landing';
  }

  function navigate(path, replace = false) {
    if (window.location.pathname === path) return;
    window.history[replace ? 'replaceState' : 'pushState']({}, '', path);
  }

  window.setAppRoute = navigate;

  async function loadView(name, targetId) {
    const target = get(targetId);
    if (!target || target.dataset.loaded === 'true') return;
    const response = await fetch(`/views/${name}.html`, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Não foi possível carregar a view ${name}.`);
    target.innerHTML = await response.text();
    target.dataset.loaded = 'true';
  }

  async function loadLandingView() {
    if (!landingLoaded) {
      await loadView('landing', 'landingView');
      landingLoaded = true;
    }
  }

  async function loadRulesView() {
    if (!rulesLoaded) {
      await loadView('planner-rules', 'rulesView');
      rulesLoaded = true;
    }
  }

  window.showLandingScreen = async function ({ navigateTo = true, replaceRoute = false, scrollTo = '' } = {}) {
    await loadLandingView();
    if (navigateTo) navigate(routeMap.landing, replaceRoute);
    document.body.classList.add('public-mode');
    show(get('landingView'));
    hide(get('rulesView'));
    show(get('landingScreen'));
    hide(get('rulesScreen'));
    hide(get('authScreen'));
    if (scrollTo) {
      window.setTimeout(() => get(scrollTo)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
    }
  };

  window.showRulesScreen = async function ({ navigateTo = true } = {}) {
    if (!authState.authenticated) {
      window.showPublicAuth({ navigateTo: true });
      return;
    }
    try {
      await loadRulesView();
      if (navigateTo) navigate(routeMap.rules);
      document.body.classList.add('public-mode');
      hide(get('landingView'));
      show(get('rulesView'));
      hide(get('landingScreen'));
      show(get('rulesScreen'));
      hide(get('authScreen'));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      console.error(error);
    }
  };

  window.showPublicAuth = function ({ navigateTo = true } = {}) {
    if (navigateTo) navigate(routeMap.login);
    document.body.classList.remove('public-mode');
    window.hidePublicViews();
    ['sidebar', 'uploadScreen', 'adminScreen', 'teamScreen', 'customChartScreen', 'comparativeScreen', 'consolidatedScreen', 'dashboard']
      .forEach(id => hide(get(id)));
    show(get('authScreen'));
    get('emailInput')?.focus();
  };

  window.showPostLoginScreen = async function () {
    const requestedRoute = new URLSearchParams(window.location.search).get('next');
    if (requestedRoute === routeMap.rules) {
      return window.showRulesScreen({ navigateTo: true });
    }
    if (requestedRoute === routeMap.teams) {
      return window.openTeamsScreen({ navigateTo: true });
    }
    if (requestedRoute === routeMap.library) {
      return window.openLibraryScreen({ navigateTo: true });
    }
    return window.showHomeScreen({ navigateTo: true });
  };

  window.resolveInitialRoute = async function (authenticated, bootstrapRequired = false) {
    const route = currentRoute();
    if (!authenticated && bootstrapRequired) {
      return showAuthScreen(true);
    }
    if (route === 'login') {
      if (authenticated) return window.showPostLoginScreen();
      return window.showPublicAuth({ navigateTo: false });
    }
    if (route === 'rules') {
      if (authenticated) return window.showRulesScreen({ navigateTo: false });
      return window.showPublicAuth({ navigateTo: true });
    }
    if (route === 'dashboard') {
      if (authenticated) return window.showHomeScreen({ navigateTo: false });
      return window.showPublicAuth({ navigateTo: true });
    }
    if (route === 'teams') {
      if (authenticated) return window.openTeamsScreen({ navigateTo: false });
      return window.showPublicAuth({ navigateTo: true });
    }
    if (route === 'library') {
      if (authenticated) return window.showHomeScreen({ navigateTo: false });
      return window.showPublicAuth({ navigateTo: true });
    }
    return window.showLandingScreen({ navigateTo: false });
  };

  window.addEventListener('popstate', () => {
    window.resolveInitialRoute?.(authState.authenticated, authState.bootstrapRequired);
  });

  window.addEventListener('DOMContentLoaded', () => {
    loadLandingView().then(() => {
      if (currentRoute() === 'landing') window.showLandingScreen({ navigateTo: false });
    }).catch(console.error);
  });
})();
