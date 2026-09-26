(() => {
  "use strict";

  const input = document.querySelector("[data-nct-input]");
  const form = document.querySelector("[data-assessment-form]");
  const submitLabel = document.querySelector("[data-submit-label]");
  const toast = document.querySelector("[data-toast]");

  const normalizeNctId = (value) => {
    const compact = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    const withoutPrefix = compact.startsWith("NCT") ? compact.slice(3) : compact;
    const digits = withoutPrefix.replace(/\D/g, "").slice(0, 8);
    return compact || digits ? `NCT${digits}` : "";
  };

  const announce = (message) => {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(announce.timeout);
    announce.timeout = window.setTimeout(() => {
      toast.hidden = true;
    }, 2800);
  };

  if (input) {
    input.value = normalizeNctId(input.value);

    input.addEventListener("input", () => {
      const cursorAtEnd = input.selectionStart === input.value.length;
      input.value = normalizeNctId(input.value);
      if (cursorAtEnd) input.setSelectionRange(input.value.length, input.value.length);
      input.setCustomValidity("");
    });

    input.addEventListener("invalid", () => {
      if (input.validity.valueMissing) {
        input.setCustomValidity("Enter a ClinicalTrials.gov NCT ID.");
      } else if (input.validity.patternMismatch) {
        input.setCustomValidity("Enter the eight digits after NCT.");
      }
    });
  }

  document.querySelectorAll("[data-demo-id]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!input) return;
      input.value = button.dataset.demoId || "";
      const mode = button.dataset.demoMode;
      const radio = mode
        ? document.querySelector(`input[name="mode"][value="${CSS.escape(mode)}"]`)
        : null;
      if (radio) radio.checked = true;
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      announce(`Loaded ${input.value}. Review the framing, then build the review.`);
    });
  });

  if (form) {
    form.addEventListener("submit", (event) => {
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
        return;
      }

      form.classList.add("is-submitting");
      form.setAttribute("aria-busy", "true");
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      if (submitLabel) submitLabel.textContent = "Building checked review…";
    });

    window.addEventListener("pageshow", () => {
      form.classList.remove("is-submitting");
      form.removeAttribute("aria-busy");
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = false;
      if (submitLabel) submitLabel.textContent = "Build evidence review";
    });
  }

  document.querySelectorAll("[data-copy-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        announce("Run link copied.");
      } catch {
        announce("Could not copy automatically. Copy the URL from your browser.");
      }
    });
  });
})();
