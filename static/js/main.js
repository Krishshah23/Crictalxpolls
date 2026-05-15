function updateThemeIcon() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) {
        return;
    }
    const isLight = document.documentElement.classList.contains("light");
    toggle.textContent = isLight ? "☽" : "☀";
}

function toggleTheme() {
    const isLight = document.documentElement.classList.toggle("light");
    document.documentElement.classList.toggle("dark", !isLight);
    localStorage.setItem("cx-theme", isLight ? "light" : "dark");
    updateThemeIcon();
}

function initTheme() {
    const saved = localStorage.getItem("cx-theme");
    const preferred = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    const theme = saved || preferred;
    document.documentElement.classList.add(theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    updateThemeIcon();
}

function updatePollBars() {
    const container = document.getElementById("polls");
    if (!container) {
        return;
    }

    const matchId = container.getAttribute("data-match-id");
    fetch(`/api/match/${matchId}/polls`)
        .then((response) => response.json())
        .then((data) => {
            data.polls.forEach((poll) => {
                const pollCard = container.querySelector(`[data-poll-id="${poll.poll_id}"]`);
                if (!pollCard) {
                    return;
                }

                const total = poll.total || 0;
                Object.keys(poll.counts).forEach((option) => {
                    const optionCard = pollCard.querySelector(`[data-option="${option}"]`);
                    if (!optionCard) {
                        return;
                    }

                    const count = poll.counts[option];
                    const percent = total ? Math.round((count / total) * 100) : 0;
                    const fill = optionCard.querySelector(".poll-bar");
                    const countLabel = optionCard.querySelector(".vote-count");
                    const percentLabel = optionCard.querySelector(".percent-label");

                    fill.style.width = `${percent}%`;
                    countLabel.textContent = `${count} votes`;
                    if (percentLabel) {
                        percentLabel.textContent = `${percent}%`;
                    }
                });
            });
        })
        .catch(() => {});
}

setInterval(updatePollBars, 20000);
window.addEventListener("load", updatePollBars);
window.addEventListener("load", () => {
    initTheme();
    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
        toggle.addEventListener("click", toggleTheme);
    }
});

window.addEventListener("load", () => {
    const cards = document.querySelectorAll(".card, .match-card");
    cards.forEach((card, index) => {
        card.style.animationDelay = `${Math.min(index * 0.05, 0.6)}s`;
        card.classList.add("animate-in");
    });
});

window.addEventListener("load", () => {
    const filter = document.querySelector("[data-results-filter]");
    const search = document.querySelector("[data-results-search]");
    const groups = document.querySelectorAll("[data-results-group]");
    if (!filter || !search || groups.length === 0) {
        return;
    }

    const applyFilters = () => {
        const status = filter.value;
        const term = search.value.trim().toLowerCase();
        groups.forEach((group) => {
            const matchStatus = group.getAttribute("data-match-status") || "";
            const matchName = group.getAttribute("data-match-name") || "";
            const statusMatch = status === "all" || matchStatus === status;
            const termMatch = !term || matchName.includes(term);
            group.style.display = statusMatch && termMatch ? "block" : "none";
        });
    };

    filter.addEventListener("change", applyFilters);
    search.addEventListener("input", applyFilters);
    applyFilters();
});

window.addEventListener("load", () => {
    const toggle = document.querySelector("[data-nav-toggle]");
    const menu = document.querySelector("[data-nav-menu]");
    if (toggle && menu) {
        toggle.addEventListener("click", () => {
            menu.classList.toggle("active");
        });
    }
});

function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 250);
    }, 2200);
}

window.addEventListener("load", () => {
    document.querySelectorAll("[data-share-button]").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest(".match-card");
            const shareTextEl = card ? card.querySelector("[data-share-text]") : null;
            const rawText = shareTextEl ? shareTextEl.textContent : "";
            const text = rawText
                .split("\n")
                .map((line) => line.trim())
                .filter((line) => line.length > 0)
                .join("\n");
            if (!text) {
                showToast("Nothing to share yet.", "error");
                return;
            }

            if (navigator.share) {
                try {
                    await navigator.share({ text });
                    showToast("Shared.");
                    return;
                } catch (err) {
                    showToast("Share canceled.", "error");
                    return;
                }
            }

            if (navigator.clipboard) {
                try {
                    await navigator.clipboard.writeText(text);
                    showToast("Copied to clipboard.");
                    return;
                } catch (err) {
                    showToast("Copy failed.", "error");
                    return;
                }
            }

            const fallback = document.createElement("textarea");
            fallback.value = text;
            fallback.setAttribute("readonly", "true");
            fallback.style.position = "absolute";
            fallback.style.left = "-9999px";
            document.body.appendChild(fallback);
            fallback.select();
            try {
                document.execCommand("copy");
                showToast("Copied to clipboard.");
            } catch (err) {
                showToast("Copy failed.", "error");
            }
            fallback.remove();
        });
    });

    document.querySelectorAll("[data-share-image]").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest(".match-card");
            const shareCard = card ? card.querySelector("[data-share-card]") : null;
            if (!card || !shareCard || !window.html2canvas) {
                showToast("Image sharing not available.", "error");
                return;
            }

            const originalTransform = card.style.transform;
            card.style.transform = "none";
            shareCard.classList.add("share-ready");
            const canvas = await window.html2canvas(shareCard, {
                backgroundColor: "#0a0a0a",
                scale: 2,
            });
            shareCard.classList.remove("share-ready");
            card.style.transform = originalTransform;

            const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
            if (!blob) {
                showToast("Image capture failed.", "error");
                return;
            }

            const file = new File([blob], "crictalx-results.png", { type: "image/png" });
            if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
                try {
                    await navigator.share({ files: [file], title: "Crictalx Results" });
                    showToast("Shared.");
                    return;
                } catch (err) {
                    showToast("Share canceled.", "error");
                    return;
                }
            }

            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "crictalx-results.png";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            showToast("Image downloaded.");
        });
    });

    document.querySelectorAll("[data-share-theme-toggle]").forEach((toggle) => {
        const options = toggle.querySelectorAll("[data-theme-option]");
        options.forEach((option) => {
            option.addEventListener("click", () => {
                const theme = option.getAttribute("data-theme-value") || "bold";
                const card = toggle.closest(".match-card");
                const shareCard = card ? card.querySelector("[data-share-card]") : null;
                if (!shareCard) {
                    return;
                }
                shareCard.setAttribute("data-share-theme", theme);
                options.forEach((btn) => btn.classList.toggle("active", btn === option));
            });
        });
    });
});

window.addEventListener("load", () => {
    const header = document.querySelector(".site-header");
    if (!header) {
        return;
    }

    const syncHeaderHeight = () => {
        document.documentElement.style.setProperty("--header-height", `${header.offsetHeight}px`);
    };

    const onScroll = () => {
        header.classList.toggle("shrink", window.scrollY > 20);
        syncHeaderHeight();
    };

    syncHeaderHeight();
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", syncHeaderHeight);
});

function updateCountdowns() {
    document.querySelectorAll("[data-countdown]").forEach((card) => {
        const ts = parseInt(card.getAttribute("data-countdown"), 10);
        const label = card.querySelector("[data-countdown-label]");
        if (!ts || !label) {
            return;
        }

        const diff = ts * 1000 - Date.now();
        if (diff <= 0) {
            label.textContent = "Live";
            return;
        }

        const totalSeconds = Math.floor(diff / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        label.textContent = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    });
}

setInterval(updateCountdowns, 1000);
window.addEventListener("load", updateCountdowns);

function updatePollLocks() {
    document.querySelectorAll("[data-lock-ts]").forEach((card) => {
        const ts = parseInt(card.getAttribute("data-lock-ts"), 10);
        const lockedAttr = card.getAttribute("data-locked") === "true";
        const label = card.querySelector("[data-lock-label]");
        if (!ts || !label) {
            return;
        }

        const diff = ts * 1000 - Date.now();
        if (lockedAttr || diff <= 0) {
            label.textContent = "🔒 Poll closed";
            label.classList.remove("urgent");
            card.classList.add("locked");
            card.setAttribute("data-locked", "true");
            return;
        }

        const totalSeconds = Math.floor(diff / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        label.textContent = `🔒 Locks in ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
        label.classList.toggle("urgent", diff <= 5 * 60 * 1000);
    });
}

setInterval(updatePollLocks, 1000);
window.addEventListener("load", updatePollLocks);

window.addEventListener("load", () => {
    document.querySelectorAll("[data-confidence]").forEach((block) => {
        const input = block.closest(".poll-card")?.querySelector("[data-confidence-input]");
        const warning = block.querySelector("[data-confidence-warning]");
        const buttons = block.querySelectorAll("[data-confidence-value]");

        const setConfidence = (value) => {
            if (input) {
                input.value = value;
            }
            buttons.forEach((btn) => {
                btn.classList.toggle("active", btn.getAttribute("data-confidence-value") === String(value));
            });
            if (!warning) {
                return;
            }
            if (value === 2) {
                warning.textContent = "2× — correct earns +4 pts, wrong costs −1 pt";
            } else if (value === 3) {
                warning.textContent = "3× — correct earns +6 pts, wrong costs −2 pts";
            } else {
                warning.textContent = "";
            }
        };

        buttons.forEach((btn) => {
            btn.addEventListener("click", () => {
                const value = parseInt(btn.getAttribute("data-confidence-value"), 10) || 1;
                setConfidence(value);
            });
        });

        const initial = input ? parseInt(input.value, 10) || 1 : 1;
        setConfidence(initial);
    });
});

window.addEventListener("load", () => {
    document.querySelectorAll("[data-toast]").forEach((toast) => {
        toast.classList.add("show");
        setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => toast.remove(), 250);
        }, 2200);
    });
});

window.addEventListener("load", () => {
    const modal = document.getElementById("user-modal");
    const modalContent = document.getElementById("modal-content");
    const modalClose = document.getElementById("user-modal-close");
    if (!modal || !modalContent || !modalClose) {
        return;
    }

    const openModal = (payload) => {
        modalContent.innerHTML = payload;
        modal.classList.add("open");
    };

    document.querySelectorAll("[data-user-modal]").forEach((row) => {
        row.addEventListener("click", () => {
            const name = row.getAttribute("data-user-name") || "Player";
            const username = row.getAttribute("data-user-username") || "";
            
            const currentUsername = document.querySelector(".nav-username")?.textContent?.trim() || "";
            if (currentUsername && username === currentUsername) {
                window.location.href = "/profile";
                return;
            }

            const points = row.getAttribute("data-user-points") || "0";
            const wins = row.getAttribute("data-user-wins") || "0";
            const rank = row.getAttribute("data-user-rank") || "-";
            const avatar = row.getAttribute("data-user-avatar") || "";
            const historyRaw = row.getAttribute("data-user-history") || "[]";
            let history = [];
            try {
                history = JSON.parse(historyRaw);
            } catch (err) {
                history = [];
            }

            const historyHtml = history.length
                ? history
                      .map(
                          (item, index) => `
                    <div style="flex:1;background:#0d0d0d;border:1px solid #1e1e1e;border-radius:8px;padding:0.75rem;text-align:center">
                        <div class="text-xs text-dim">${item.date || `Match ${index + 1}`}</div>
                        <div class="mono fw-bold text-acid">${item.points}</div>
                        ${item.label ? `<div class=\"text-xs text-dim\" style=\"margin-top:4px\">${item.label}</div>` : ""}
                    </div>
                `
                      )
                      .join("")
                : "<div class=\"text-dim text-sm\">No match history yet.</div>";

            openModal(`
                <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem;margin-top:0.5rem">
                    <div class="rank-avatar" style="width:60px;height:60px;font-size:1.4rem;">
                        ${avatar ? `<img src=\"${avatar}\" alt=\"${name}\" style=\"width:100%;height:100%;object-fit:cover\">` : name[0] ? name[0].toUpperCase() : "?"}
                    </div>
                    <div>
                        <div class="bebas" style="font-size:1.6rem;letter-spacing:2px">${name}</div>
                        <div class="text-sm text-dim">@${username} · Rank #${rank}</div>
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1.5rem">
                    <div class="stat-pill"><div class="stat-label">Total Points</div><div class="stat-value text-acid" style="font-size:1.6rem">${points}</div></div>
                    <div class="stat-pill"><div class="stat-label">Wins</div><div class="stat-value text-gold" style="font-size:1.6rem">${wins}</div></div>
                </div>
                <div class="tag mb-2">Match History</div>
                <div style="display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap">
                    ${historyHtml}
                </div>
            `);
        });
    });

    modalClose.addEventListener("click", () => {
        modal.classList.remove("open");
    });
    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            modal.classList.remove("open");
        }
    });
});

window.addEventListener("load", () => {
    const bar = document.querySelector("[data-vote-bar]");
    const barSubmit = document.querySelector("[data-vote-bar-submit]");
    const barLabel = document.querySelector("[data-submit-label]");
    const form = document.querySelector("[data-match-form]");
    if (!form || !bar || !barSubmit) {
        return;
    }

    const hasVotes = form.getAttribute("data-has-votes") === "true";

    if (bar.classList.contains("disabled")) {
        barSubmit.disabled = true;
        return;
    }

    const pollCards = form.querySelectorAll("[data-poll-card]");

    const updateSubmitState = () => {
        let hasChange = false;
        let hasSelection = false;
        pollCards.forEach((card) => {
            if (card.getAttribute("data-submitted") === "true") {
                return;
            }
            const pollBlock = card.closest("[data-poll-id]");
            const original = pollBlock ? pollBlock.getAttribute("data-original-option") : "";
            const originalConfidence = pollBlock ? pollBlock.getAttribute("data-original-confidence") : "1";
            const selected = card.querySelector("input[type='radio']:checked");
            const selectedValue = selected ? selected.value : "";
            const confidenceInput = card.querySelector("[data-confidence-input]");
            const currentConfidence = confidenceInput ? confidenceInput.value : originalConfidence;
            if (selectedValue) {
                hasSelection = true;
            }
            if (selectedValue && selectedValue !== original) {
                hasChange = true;
            }
            if (currentConfidence !== originalConfidence) {
                hasChange = true;
            }
        });

        if (hasVotes) {
            barSubmit.disabled = !hasChange;
        } else {
            barSubmit.disabled = !hasSelection;
        }
        bar.classList.toggle("active", hasSelection && !bar.classList.contains("disabled"));
        if (barLabel) {
            if (hasVotes && !hasChange) {
                barLabel.textContent = "Picks saved. Update to change.";
            } else {
                barLabel.textContent = hasChange ? "Update your picks" : "Ready to submit your picks?";
            }
        }
        barSubmit.textContent = hasChange ? "Update Picks" : "Submit Picks";
    };

    pollCards.forEach((card) => {
        const options = card.querySelectorAll(".poll-opt");
        const resetBars = () => {
            options.forEach((item) => {
                const fill = item.querySelector(".poll-bar");
                const percent = item.querySelector(".percent-label");
                if (fill) {
                    fill.style.width = "0%";
                }
                if (percent) {
                    percent.textContent = "0%";
                }
            });
        };

        options.forEach((opt) => {
            opt.addEventListener("click", () => {
                options.forEach((item) => item.classList.remove("selected"));
                opt.classList.add("selected");
                const input = opt.querySelector("input[type='radio']");
                if (input && !input.disabled) {
                    input.checked = true;
                }
                resetBars();
                const fill = opt.querySelector(".poll-bar");
                const percent = opt.querySelector(".percent-label");
                if (fill) {
                    fill.style.width = "100%";
                }
                if (percent) {
                    percent.textContent = "100%";
                }
                updateSubmitState();
            });
        });

        const confidenceButtons = card.querySelectorAll("[data-confidence-value]");
        confidenceButtons.forEach((btn) => {
            btn.addEventListener("click", updateSubmitState);
        });
    });

    updateSubmitState();
});
