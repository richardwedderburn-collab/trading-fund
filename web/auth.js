(function () {
  const AUTH_KEY = 'fundflow.authenticated';

  function isAuthenticated() {
    return window.localStorage.getItem(AUTH_KEY) === 'true';
  }

  function setAuthenticated(value) {
    window.localStorage.setItem(AUTH_KEY, value ? 'true' : 'false');
  }

  window.fundflowAuth = {
    isAuthenticated,
    setAuthenticated,
  };

  const path = window.location.pathname.toLowerCase();
  const isIndex = path.endsWith('/index.html') || path.endsWith('/web/') || path.endsWith('/web');

  if (!isIndex && !isAuthenticated()) {
    const base = window.location.pathname.replace(/[^/]*$/, '');
    window.location.replace(base + 'index.html?auth=required');
  }
})();
