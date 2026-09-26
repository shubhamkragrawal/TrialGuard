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

  const reportChat = document.querySelector("[data-report-chat]");

  if (reportChat) {
    const runId = reportChat.dataset.runId || "";
    const turnLimit = Number.parseInt(reportChat.dataset.turnLimit || "5", 10);
    const chatForm = reportChat.querySelector("[data-chat-form]");
    const chatInput = reportChat.querySelector("[data-chat-input]");
    const chatSubmit = reportChat.querySelector("[data-chat-submit]");
    const chatSubmitLabel = reportChat.querySelector("[data-chat-submit-label]");
    const chatLog = reportChat.querySelector("[data-chat-log]");
    const chatState = reportChat.querySelector("[data-chat-state]");
    const chatCount = reportChat.querySelector("[data-chat-count]");
    const chatFormError = reportChat.querySelector("[data-chat-form-error]");
    const chatLimit = reportChat.querySelector("[data-chat-limit]");
    const chatLimitMessage = reportChat.querySelector("[data-chat-limit-message]");
    let completedTurns = 0;
    let requestPending = false;
    let retryNotice = null;

    const asArray = (value) => (Array.isArray(value) ? value : []);

    const statusValue = (item) => {
      if (!item || typeof item !== "object") return "";
      return String(item.status || item.result || "").toLowerCase().replaceAll("_", "-");
    };

    const responseMessage = (payload, response) => {
      const detail = payload && payload.detail;
      const error = payload && payload.error;
      const candidate =
        (typeof detail === "string" && detail) ||
        (detail && (detail.message || detail.detail)) ||
        (typeof error === "string" && error) ||
        (error && (error.message || error.detail)) ||
        (payload && (payload.message || payload.title));

      if (candidate) return String(candidate);
      if (response.status === 404) return "This report is no longer available. Start a new review and try again.";
      if (response.status === 429) return "The chat is receiving too many requests. Wait a moment, then retry.";
      return "TrialGuard could not answer that question. Please try again.";
    };

    const isTurnLimitResponse = (payload, response, message) => {
      const code = String(
        (payload && (payload.code || payload.error_code)) ||
        (payload && payload.error && payload.error.code) ||
        "",
      ).toLowerCase();
      const searchable = `${code} ${message}`.toLowerCase();
      return (
        (searchable.includes("turn") && searchable.includes("limit")) ||
        searchable.includes("maximum questions") ||
        searchable.includes("conversation complete") ||
        (response.status === 409 && searchable.includes("limit"))
      );
    };

    const createMessage = (role, text) => {
      const article = document.createElement("article");
      article.className = `chat-message chat-message--${role}`;

      const avatar = document.createElement("div");
      avatar.className = "chat-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = role === "assistant" ? "TG" : "You";

      const content = document.createElement("div");
      content.className = "chat-message__content";

      const author = document.createElement("span");
      author.className = "chat-message__author";
      author.textContent = role === "assistant" ? "TrialGuard" : "You";

      const bubble = document.createElement("div");
      bubble.className = "chat-bubble";

      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      bubble.append(paragraph);
      content.append(author, bubble);
      article.append(avatar, content);
      return { article, bubble };
    };

    const scrollToLatestMessage = () => {
      window.requestAnimationFrame(() => {
        chatLog.scrollTo({
          top: chatLog.scrollHeight,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        });
      });
    };

    const safeSourceUrl = (value) => {
      if (typeof value !== "string" || !value.trim()) return null;
      try {
        const url = new URL(value);
        return ["http:", "https:"].includes(url.protocol) ? url.href : null;
      } catch {
        return null;
      }
    };

    const appendEvidenceLinks = (container, evidenceIds) => {
      const uniqueIds = [...new Set(asArray(evidenceIds).filter((id) => typeof id === "string" && id.trim()))];
      if (!uniqueIds.length) return;

      const group = document.createElement("div");
      group.className = "chat-reference-group";

      const label = document.createElement("span");
      label.className = "chat-reference-label";
      label.textContent = "Evidence";
      group.append(label);

      uniqueIds.forEach((evidenceId) => {
        const cleanId = evidenceId.trim();
        const target = document.getElementById(`evidence-${cleanId}`);
        const reference = document.createElement(target ? "a" : "span");
        reference.className = "chat-reference";
        reference.textContent = cleanId;
        if (target) reference.href = `#${encodeURIComponent(target.id)}`;
        group.append(reference);
      });

      container.append(group);
    };

    const appendSourceLinks = (container, sources) => {
      const normalized = asArray(sources)
        .map((source, index) => {
          if (typeof source === "string") {
            return {
              label: source.startsWith("http") ? `Source ${index + 1}` : source,
              url: safeSourceUrl(source),
            };
          }
          if (!source || typeof source !== "object") return null;
          return {
            label: String(
              source.label ||
              source.nct_id ||
              source.title ||
              source.evidence_id ||
              source.id ||
              `Source ${index + 1}`,
            ),
            url: safeSourceUrl(source.url || source.source_url || source.href),
          };
        })
        .filter((source) => source && source.url);

      const uniqueSources = normalized.filter(
        (source, index, allSources) => allSources.findIndex((item) => item.url === source.url) === index,
      );
      if (!uniqueSources.length) return;

      const group = document.createElement("div");
      group.className = "chat-reference-group";

      const label = document.createElement("span");
      label.className = "chat-reference-label";
      label.textContent = "Sources";
      group.append(label);

      uniqueSources.forEach((source) => {
        const link = document.createElement("a");
        link.className = "chat-reference chat-reference--source";
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.label;
        link.setAttribute("aria-label", `${source.label} (opens in a new tab)`);
        group.append(link);
      });

      container.append(group);
    };

    const appendAnswerMetadata = (container, payload) => {
      const checks = asArray(payload.checks);
      const trace = Array.isArray(payload.trace)
        ? payload.trace
        : payload.trace && typeof payload.trace === "object"
          ? [payload.trace]
          : [];
      const usage = payload.usage && typeof payload.usage === "object" ? payload.usage : {};
      const statuses = checks.map(statusValue).filter(Boolean);
      const checksFailed = statuses.some((status) => ["failed", "fail", "blocked", "error"].includes(status));
      const checksPassed = statuses.length > 0 && statuses.every((status) => ["passed", "pass"].includes(status));
      const tokenCount = Number(
        usage.total_tokens ||
        usage.totalTokens ||
        (Number(usage.input_tokens || usage.inputTokens || 0) + Number(usage.output_tokens || usage.outputTokens || 0)),
      );
      const durationMs = trace.reduce(
        (total, event) => total + Number((event && (event.duration_ms || event.durationMs)) || 0),
        0,
      );

      if (!statuses.length && !tokenCount && !durationMs) return;

      const metadata = document.createElement("div");
      metadata.className = "chat-answer-meta";

      if (statuses.length) {
        const checkSummary = document.createElement("span");
        checkSummary.className = checksFailed ? "chat-answer-meta__warning" : "chat-answer-meta__passed";
        checkSummary.textContent = checksPassed
          ? `${statuses.length} checks passed`
          : checksFailed
            ? "Check requires attention"
            : "Checks completed with limits";
        metadata.append(checkSummary);
      }

      if (tokenCount > 0) {
        const tokens = document.createElement("span");
        tokens.textContent = `${tokenCount.toLocaleString()} tokens`;
        metadata.append(tokens);
      }

      if (durationMs > 0) {
        const duration = document.createElement("span");
        duration.textContent = `${(durationMs / 1000).toFixed(1)} s`;
        metadata.append(duration);
      }

      container.append(metadata);
    };

    const setBusy = (busy) => {
      requestPending = busy;
      chatForm.setAttribute("aria-busy", String(busy));
      chatInput.disabled = busy;
      chatSubmit.disabled = busy;
      reportChat.classList.toggle("is-chat-loading", busy);
      chatSubmitLabel.textContent = busy ? "Checking answer…" : "Ask TrialGuard";
    };

    const updateTurnState = () => {
      const noun = turnLimit === 1 ? "question" : "questions";
      chatState.textContent = `${completedTurns} of ${turnLimit} ${noun} used`;
    };

    const showTurnLimit = (message) => {
      setBusy(false);
      completedTurns = Math.max(completedTurns, turnLimit);
      updateTurnState();
      chatInput.disabled = true;
      chatSubmit.disabled = true;
      chatForm.hidden = true;
      chatLimitMessage.textContent =
        message || `This bounded ${turnLimit}-question conversation is complete. Start a new review to investigate another trial.`;
      chatLimit.hidden = false;
      chatLimit.focus({ preventScroll: true });
      scrollToLatestMessage();
    };

    const appendLoadingMessage = () => {
      const { article, bubble } = createMessage("assistant", "");
      article.classList.add("chat-message--loading");
      article.setAttribute("role", "status");
      article.setAttribute("aria-label", "TrialGuard is checking the report");

      const loading = document.createElement("span");
      loading.className = "chat-typing";
      loading.setAttribute("aria-hidden", "true");
      loading.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));

      const loadingText = document.createElement("span");
      loadingText.className = "visually-hidden";
      loadingText.textContent = "Checking the report and cited evidence…";
      bubble.replaceChildren(loading, loadingText);
      chatLog.append(article);
      scrollToLatestMessage();
      return article;
    };

    const appendRetryNotice = (message, retry) => {
      const notice = document.createElement("div");
      notice.className = "chat-notice chat-notice--error";
      notice.setAttribute("role", "alert");

      const copy = document.createElement("span");
      copy.textContent = message;

      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry";
      button.addEventListener("click", () => {
        notice.remove();
        retryNotice = null;
        retry();
      });

      notice.append(copy, button);
      chatLog.append(notice);
      retryNotice = notice;
      scrollToLatestMessage();
    };

    const askQuestion = async (message, appendUserMessage = true) => {
      if (requestPending || !message || completedTurns >= turnLimit) return;
      if (retryNotice) {
        retryNotice.remove();
        retryNotice = null;
      }
      chatFormError.hidden = true;

      if (appendUserMessage) {
        chatLog.append(createMessage("user", message).article);
      }
      const loadingMessage = appendLoadingMessage();
      setBusy(true);

      try {
        const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/chat`, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ message }),
        });

        let payload = {};
        try {
          payload = await response.json();
        } catch {
          payload = {};
        }

        if (!response.ok) {
          const messageText = responseMessage(payload, response);
          if (isTurnLimitResponse(payload, response, messageText)) {
            loadingMessage.remove();
            showTurnLimit(messageText);
            return;
          }
          throw new Error(messageText);
        }

        if (!payload || typeof payload.answer !== "string" || !payload.answer.trim()) {
          throw new Error("TrialGuard returned an empty answer. Please retry.");
        }

        const answer = createMessage("assistant", payload.answer.trim());
        const references = document.createElement("div");
        references.className = "chat-references";
        appendEvidenceLinks(references, payload.evidence_ids);
        appendSourceLinks(references, payload.sources);
        if (references.childElementCount) answer.bubble.append(references);
        appendAnswerMetadata(answer.bubble, payload);
        loadingMessage.replaceWith(answer.article);

        completedTurns = Math.max(completedTurns + 1, Number(payload.turn) || 0);
        updateTurnState();
        if (completedTurns >= turnLimit) {
          setBusy(false);
          showTurnLimit();
          return;
        }
        scrollToLatestMessage();
      } catch (error) {
        loadingMessage.remove();
        const messageText = error instanceof Error ? error.message : "TrialGuard could not answer that question.";
        appendRetryNotice(messageText, () => askQuestion(message, false));
      } finally {
        if (completedTurns < turnLimit && !chatForm.hidden) {
          setBusy(false);
          chatInput.focus({ preventScroll: true });
        }
      }
    };

    if (!runId || !chatForm || !chatInput || !chatSubmit || !chatLog) {
      if (chatForm) chatForm.hidden = true;
      if (chatLimit) {
        chatLimitMessage.textContent = "Chat is unavailable because this report does not have an active run reference.";
        chatLimit.hidden = false;
      }
    } else {
      chatInput.addEventListener("input", () => {
        chatCount.textContent = `${chatInput.value.length} / ${chatInput.maxLength}`;
        chatFormError.hidden = true;
      });

      chatInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          chatForm.requestSubmit();
        }
      });

      chatForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const message = chatInput.value.trim();
        if (!message) {
          chatFormError.textContent = "Enter a question about this report.";
          chatFormError.hidden = false;
          chatInput.focus();
          return;
        }

        chatInput.value = "";
        chatCount.textContent = `0 / ${chatInput.maxLength}`;
        askQuestion(message);
      });

      updateTurnState();
    }
  }
})();
