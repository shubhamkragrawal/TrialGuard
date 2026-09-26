(function () {
  "use strict";

  const pageNames = new Set(["overview", "report", "evaluation", "boundary"]);
  const pages = Array.from(document.querySelectorAll("[data-page]"));
  const routeLinks = Array.from(document.querySelectorAll("[data-route]"));
  const toast = document.querySelector("[data-toast]");
  let toastTimer;

  function routeFromHash() {
    const route = window.location.hash.slice(1).split("/")[0];
    return pageNames.has(route) ? route : "overview";
  }

  function setActivePage(route, options) {
    const settings = options || {};

    pages.forEach(function (page) {
      const active = page.dataset.page === route;
      page.classList.toggle("is-active", active);
      page.setAttribute("aria-hidden", active ? "false" : "true");
    });

    routeLinks.forEach(function (link) {
      if (link.dataset.route === route) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });

    document.title =
      route === "overview"
        ? "TrialGuard · Evidence-linked trial review"
        : route === "report"
          ? "Prepared report · TrialGuard"
          : route === "evaluation"
            ? "Evaluation · TrialGuard"
            : "Intended use · TrialGuard";

    if (!settings.keepScroll) {
      window.scrollTo({ top: 0, behavior: "auto" });
    }
  }

  function showToast(message) {
    if (!toast) {
      return;
    }

    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 2600);
  }

  routeLinks.forEach(function (link) {
    link.addEventListener("click", function (event) {
      const route = link.dataset.route;
      if (!pageNames.has(route)) {
        return;
      }

      event.preventDefault();
      if (window.location.hash === "#" + route) {
        setActivePage(route);
      } else {
        window.location.hash = route;
      }
    });
  });

  window.addEventListener("hashchange", function () {
    setActivePage(routeFromHash());
  });

  const copyButton = document.querySelector("[data-copy-link]");
  if (copyButton) {
    copyButton.addEventListener("click", async function () {
      const reportUrl = new URL(window.location.href);
      reportUrl.hash = "report";

      try {
        await navigator.clipboard.writeText(reportUrl.toString());
        showToast("Prepared-report link copied.");
      } catch (_error) {
        showToast("Copy was unavailable. Use the address bar to copy this link.");
      }
    });
  }

  document.addEventListener("click", function (event) {
    const link = event.target.closest('a[href^="#"]');
    if (!link || link.hasAttribute("data-route")) {
      return;
    }

    const target = document.querySelector(link.getAttribute("href"));
    if (!target) {
      return;
    }

    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  setActivePage(routeFromHash(), { keepScroll: true });
})();
