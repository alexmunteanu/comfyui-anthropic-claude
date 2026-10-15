// © 2026 Created with ♥ by Alex Munteanu | alexmunteanu.com
import { app } from "../../scripts/app.js";


function showInputDialog(title, callback) {
    var overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;";

    var box = document.createElement("div");
    box.style.cssText = "background:#2a2a2a;border:1px solid #555;border-radius:8px;padding:20px;min-width:320px;color:#ddd;font-family:sans-serif;";

    var label = document.createElement("div");
    label.textContent = title;
    label.style.cssText = "margin-bottom:12px;font-size:14px;";

    var input = document.createElement("input");
    input.type = "text";
    input.style.cssText = "width:100%;box-sizing:border-box;padding:8px;background:#1a1a1a;border:1px solid #555;border-radius:4px;color:#eee;font-size:14px;outline:none;";

    var btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:14px;";

    var cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "padding:6px 16px;background:#444;border:none;border-radius:4px;color:#ccc;cursor:pointer;font-size:13px;";

    var saveBtn = document.createElement("button");
    saveBtn.textContent = "Save";
    saveBtn.style.cssText = "padding:6px 16px;background:#2563eb;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:13px;";

    function close() { document.body.removeChild(overlay); }

    cancelBtn.onclick = close;
    overlay.onclick = function (e) { if (e.target === overlay) close(); };
    saveBtn.onclick = function () {
        var val = input.value.trim();
        close();
        if (val) callback(val);
    };
    input.onkeydown = function (e) {
        if (e.key === "Enter") { saveBtn.click(); }
        if (e.key === "Escape") { close(); }
    };

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    box.appendChild(label);
    box.appendChild(input);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    input.focus();
}

function showConfirmDialog(message, confirmLabel, callback) {
    var overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:10002;display:flex;align-items:center;justify-content:center;";

    var box = document.createElement("div");
    box.style.cssText = "background:#2a2a2a;border:1px solid #555;border-radius:8px;padding:20px;min-width:320px;max-width:420px;color:#ddd;font-family:sans-serif;";

    var label = document.createElement("div");
    label.textContent = message;
    label.style.cssText = "margin-bottom:14px;font-size:14px;line-height:1.5;";

    var btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;justify-content:flex-end;gap:8px;";

    var cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "padding:6px 16px;background:#444;border:none;border-radius:4px;color:#ccc;cursor:pointer;font-size:13px;";

    var okBtn = document.createElement("button");
    okBtn.textContent = confirmLabel;
    okBtn.style.cssText = "padding:6px 16px;background:#b91c1c;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:13px;";

    function close() { if (overlay.parentNode) document.body.removeChild(overlay); }

    cancelBtn.onclick = close;
    overlay.onclick = function (e) { if (e.target === overlay) close(); };
    okBtn.onclick = function () { close(); callback(); };

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(okBtn);
    box.appendChild(label);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    okBtn.focus();
}

function showToast(msg, isError) {
    var toast = document.createElement("div");
    toast.textContent = msg;
    toast.style.cssText = "position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:6px;color:#fff;font-size:13px;font-family:sans-serif;z-index:10001;opacity:1;transition:opacity 0.4s;";
    toast.style.background = isError ? "#b91c1c" : "#16a34a";
    document.body.appendChild(toast);
    setTimeout(function () {
        toast.style.opacity = "0";
        setTimeout(function () { document.body.removeChild(toast); }, 500);
    }, 2500);
}


function _postTemplate(name, content, overwrite, onSaved) {
    var status = 0;
    fetch("/anthropic_claude/save_template", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, content: content, overwrite: overwrite === true })
    }).then(function (res) {
        status = res.status;
        return res.json();
    }).then(function (data) {
        if (status === 409) {
            showConfirmDialog(
                "Template \"" + ((data && data.name) || name) + "\" already exists.",
                "Replace",
                function () { _postTemplate(name, content, true, onSaved); }
            );
            return;
        }
        if (data && data.ok) {
            if (onSaved) onSaved(data.name);
            showToast("Template saved: " + data.name, false);
        } else {
            showToast("Error: " + ((data && data.error) || "Unknown error"), true);
        }
    }).catch(function (err) {
        showToast("Failed to save template: " + err, true);
    });
}

var _warningsChecked = false;
function checkStartupWarnings() {
    if (_warningsChecked) return;
    _warningsChecked = true;
    fetch("/anthropic_claude/startup_warnings")
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.warnings && data.warnings.length) {
                for (var i = 0; i < data.warnings.length; i++) {
                    showToast("Anthropic Claude: " + data.warnings[i], true);
                }
            }
        })
        .catch(function () {});
}


var _apiErrorModalShown = false;
var _apiErrorOverlay = null;
var _apiErrorMsgEl = null;
var _apiErrorRetryBtn = null;
var _apiErrorNode = null;
var _apiRetrySuccessTime = 0;

var _apiErrorMessages = {
    auth_error: "The saved Anthropic API key is invalid.",
    missing_key: "Add and validate an Anthropic API key on the node.",
    missing_package: "The 'anthropic' package is not installed.\nRun: pip install anthropic",
    provider_unavailable: "Anthropic is temporarily unavailable.",
    catalog_error: "The Anthropic model catalogue is unavailable.",
    rate_limit: "Anthropic is rate limiting requests.\nWait and retry.",
    unknown: "Could not connect to the Anthropic API."
};

function _createApiErrorModal() {
    var overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;";

    var box = document.createElement("div");
    box.style.cssText = "background:#1a1a2e;border:1px solid #334155;border-radius:10px;padding:28px 32px;max-width:480px;width:90%;color:#e2e8f0;box-shadow:0 20px 60px rgba(0,0,0,0.5);";

    var title = document.createElement("div");
    title.style.cssText = "font-size:16px;font-weight:600;margin-bottom:16px;color:#f87171;";
    title.textContent = "API Connection Issue";

    var msg = document.createElement("div");
    msg.style.cssText = "font-size:13px;line-height:1.6;color:#94a3b8;margin-bottom:12px;white-space:pre-line;";

    var btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;justify-content:flex-end;gap:8px;";

    var dismissBtn = document.createElement("button");
    dismissBtn.textContent = "Dismiss";
    dismissBtn.style.cssText = "padding:8px 20px;background:#334155;border:none;border-radius:5px;color:#94a3b8;cursor:pointer;font-size:13px;";
    dismissBtn.onclick = function () { _closeApiErrorModal(); };

    var retryBtn = document.createElement("button");
    retryBtn.textContent = "Retry Connection";
    retryBtn.style.cssText = "padding:8px 20px;background:#2563eb;border:none;border-radius:5px;color:#fff;cursor:pointer;font-size:13px;";
    retryBtn.onclick = _retryApiConnection;

    btnRow.appendChild(dismissBtn);
    btnRow.appendChild(retryBtn);
    box.appendChild(title);
    box.appendChild(msg);
    box.appendChild(btnRow);
    overlay.appendChild(box);

    overlay.onclick = function (e) { if (e.target === overlay) _closeApiErrorModal(); };

    _apiErrorOverlay = overlay;
    _apiErrorMsgEl = msg;
    _apiErrorRetryBtn = retryBtn;
    return overlay;
}

function _showApiErrorModal(info, node) {
    if (Date.now() - _apiRetrySuccessTime < 5000) return;
    if (!_apiErrorOverlay) _createApiErrorModal();
    var message = _apiErrorMessages[info.error_type] || info.error || _apiErrorMessages.unknown;
    _apiErrorMsgEl.textContent = message;
    if (node) _apiErrorNode = node;
    if (!_apiErrorOverlay.parentNode) {
        document.body.appendChild(_apiErrorOverlay);
    }
}

function _closeApiErrorModal() {
    if (_apiErrorOverlay && _apiErrorOverlay.parentNode) {
        _apiErrorOverlay.parentNode.removeChild(_apiErrorOverlay);
    }
}

var _credentialControls = [];
var _credentialHealthTimer = null;
var _credentialLastStatus = {
    ok: false,
    status: "missing",
    error_type: ""
};

var _credentialStatusLabels = {
    checking: "Key: Checking...",
    valid: "Key: Ready",
    missing: "Key: Not set",
    invalid: "Key: Invalid",
    unavailable: "Key: Unavailable",
    storage_error: "Key: Save failed"
};

var _credentialStatusColors = {
    checking: "#eab308",
    valid: "#16a34a",
    missing: "#94a3b8",
    invalid: "#f87171",
    unavailable: "#f97316",
    storage_error: "#f87171"
};

function _updateModelWidget(widget, models) {
    if (!widget || !models || !models.length) return;
    widget.options.values = models;
    if (models.indexOf(widget.value) !== -1) return;
    var sonnet = null;
    for (var i = 0; i < models.length; i++) {
        if (models[i].indexOf("Sonnet") === 0) {
            sonnet = models[i];
            break;
        }
    }
    widget.value = sonnet || models[0];
}

function _syncCredentialControls(info, models, checking) {
    if (info && !checking) {
        _credentialLastStatus = {
            ok: info.ok === true,
            status: info.status || "missing",
            error_type: info.error_type || ""
        };
    }
    var status = checking ? "checking" : _credentialLastStatus.status;
    var label = _credentialStatusLabels[status] || _credentialStatusLabels.missing;
    var color = _credentialStatusColors[status] || _credentialStatusColors.missing;
    for (var i = 0; i < _credentialControls.length; i++) {
        var control = _credentialControls[i];
        control.statusEl.textContent = label;
        control.statusEl.style.color = color;
        control.button.disabled = checking === true;
        _updateModelWidget(control.modelWidget, models);
        if (control.node && control.node.setDirtyCanvas) {
            control.node.setDirtyCanvas(true, true);
        }
    }
}

function _registerCredentialControl(node, statusEl, button, modelWidget) {
    var control = {
        node: node,
        statusEl: statusEl,
        button: button,
        modelWidget: modelWidget
    };
    _credentialControls.push(control);
    _syncCredentialControls(_credentialLastStatus);
    return control;
}

function _unregisterCredentialControl(node) {
    var kept = [];
    for (var i = 0; i < _credentialControls.length; i++) {
        if (_credentialControls[i].node !== node) kept.push(_credentialControls[i]);
    }
    _credentialControls = kept;
}

function _saveCredential(input) {
    var candidate = input.value.trim();
    if (!candidate) {
        input.value = "";
        showToast("Enter an API key", true);
        return;
    }
    var payload = JSON.stringify({ api_key: candidate });
    candidate = "";
    input.value = "";
    _syncCredentialControls(null, null, true);

    var requestStatus = 0;
    fetch("/anthropic_claude/api_key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload
    }).then(function (response) {
        requestStatus = response.status;
        return response.json();
    }).then(function (data) {
        input.value = "";
        var activeStatus = (data && data.active_status)
            || (data && data.status)
            || _credentialLastStatus.status;
        _syncCredentialControls({
            ok: activeStatus === "valid",
            status: activeStatus,
            error_type: data && data.error && data.error.error_type
        }, data && data.models);
        if (requestStatus === 200 && data && data.ok) {
            showToast("API key saved", false);
            return;
        }
        var message = data && data.error && data.error.error;
        showToast(message || "Could not save API key", true);
    }).catch(function () {
        input.value = "";
        _syncCredentialControls(_credentialLastStatus);
        showToast("Could not reach the local API", true);
    });
}

function _retryApiConnection() {
    var retryStatus = 0;
    _apiErrorRetryBtn.textContent = "Retrying...";
    _apiErrorRetryBtn.disabled = true;
    _syncCredentialControls(null, null, true);
    fetch("/anthropic_claude/refresh_models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
    })
        .then(function (response) {
            retryStatus = response.status;
            return response.json();
        })
        .then(function (data) {
            _apiErrorRetryBtn.textContent = "Retry Connection";
            _apiErrorRetryBtn.disabled = false;
            _syncCredentialControls(data, data && data.models);
            if (retryStatus === 200 && data && data.ok) {
                if (_apiErrorNode && _apiErrorNode._acErrorLine) {
                    _apiErrorNode._acErrorLine.style.display = "none";
                    _apiErrorNode._errorText = null;
                }
                _apiRetrySuccessTime = Date.now();
                _apiErrorModalShown = false;
                _closeApiErrorModal();
                showToast("Models refreshed", false);
                return;
            }
            _apiErrorMsgEl.textContent =
                _apiErrorMessages[data && data.error_type]
                || _apiErrorMessages.unknown;
        })
        .catch(function () {
            _apiErrorRetryBtn.textContent = "Retry Connection";
            _apiErrorRetryBtn.disabled = false;
            _syncCredentialControls(_credentialLastStatus);
            _apiErrorMsgEl.textContent = "Network error. Check your connection.";
        });
}

function _checkApiHealth() {
    fetch("/anthropic_claude/api_health")
        .then(function (response) { return response.json(); })
        .then(function (info) {
            var checking = info && info.status === "checking";
            _syncCredentialControls(info, null, checking);
            if (checking && !_credentialHealthTimer) {
                _credentialHealthTimer = setTimeout(function () {
                    _credentialHealthTimer = null;
                    _checkApiHealth();
                }, 500);
            }
        })
        .catch(function () {
            _syncCredentialControls({
                ok: false,
                status: "unavailable",
                error_type: "provider_unavailable"
            });
        });
}

function _copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
            showToast("Copied to clipboard", false);
        }).catch(function () {
            showToast("Failed to copy", true);
        });
    } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.cssText = "position:fixed;left:-9999px";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); showToast("Copied to clipboard", false); }
        catch (e) { showToast("Failed to copy", true); }
        document.body.removeChild(ta);
    }
}


var _histStylesInjected = false;
var _histOverlay = null;
var _histCurrentNode = null;
var _histDebounce = null;

var _histState = {
    page: 1, perPage: 20, search: "", dateFrom: "", dateTo: "",
    favoritesOnly: false, sortBy: "date_desc",
    total: 0, totalPages: 1, expandedId: null
};
var _histEls = {};

function _injectHistoryStyles() {
    if (_histStylesInjected) return;
    _histStylesInjected = true;
    var s = document.createElement("style");
    s.textContent = [
        ".ach-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}",
        ".ach-modal{background:#1a1a2e;border:1px solid #334155;border-radius:10px;width:85%;max-width:960px;height:85vh;display:flex;flex-direction:column;color:#e2e8f0;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.5)}",
        ".ach-header{display:flex;align-items:center;padding:14px 20px;border-bottom:1px solid #334155;gap:12px;flex-shrink:0}",
        ".ach-title{font-size:16px;font-weight:600;white-space:nowrap}",
        ".ach-stats{font-size:12px;color:#94a3b8;margin-left:8px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
        ".ach-close{background:none;border:none;color:#94a3b8;font-size:22px;cursor:pointer;padding:0 4px;line-height:1}",
        ".ach-close:hover{color:#e2e8f0}",
        ".ach-toolbar{display:flex;align-items:center;padding:10px 20px;gap:8px;border-bottom:1px solid #334155;flex-shrink:0;flex-wrap:wrap}",
        ".ach-search{flex:1;min-width:180px;padding:7px 12px;background:#0f172a;border:1px solid #334155;border-radius:5px;color:#e2e8f0;font-size:13px;outline:none}",
        ".ach-search:focus{border-color:#2563eb}",
        ".ach-date-input{padding:6px 8px;background:#0f172a;border:1px solid #334155;border-radius:5px;color:#e2e8f0;font-size:12px;outline:none;width:130px}",
        ".ach-date-input:focus{border-color:#2563eb}",
        ".ach-select{padding:6px 8px;background:#0f172a;border:1px solid #334155;border-radius:5px;color:#e2e8f0;font-size:12px;outline:none;cursor:pointer}",
        ".ach-btn{padding:6px 14px;border:none;border-radius:5px;font-size:12px;cursor:pointer;white-space:nowrap}",
        ".ach-btn-fav{background:#1e293b;color:#94a3b8}",
        ".ach-btn-fav.active{background:#422006;color:#fbbf24}",
        ".ach-list{flex:1;overflow-y:auto;padding:8px 16px}",
        ".ach-list::-webkit-scrollbar{width:8px}",
        ".ach-list::-webkit-scrollbar-track{background:transparent}",
        ".ach-list::-webkit-scrollbar-thumb{background:#334155;border-radius:4px}",
        ".ach-empty{text-align:center;padding:60px 20px;color:#64748b;font-size:14px}",
        ".ach-note{background:#2d2410;border:1px solid #4a3a12;border-radius:5px;color:#fbbf24;font-size:12px;padding:7px 12px;margin-bottom:8px}",
        ".ach-entry{background:#22223a;border:1px solid #2d2d50;border-radius:6px;margin-bottom:6px;overflow:hidden;transition:border-color 0.15s}",
        ".ach-entry:hover{border-color:#3b3b60}",
        ".ach-entry-head{display:flex;align-items:center;padding:8px 12px;gap:8px;cursor:pointer;user-select:none}",
        ".ach-entry-head:hover{background:#2a2a48}",
        ".ach-fav-btn{background:none;border:none;font-size:15px;cursor:pointer;padding:0 2px;color:#64748b;line-height:1}",
        ".ach-fav-btn.active{color:#fbbf24}",
        ".ach-entry-date{font-size:12px;color:#94a3b8;white-space:nowrap}",
        ".ach-entry-model{font-size:12px;color:#60a5fa;font-weight:500;white-space:nowrap}",
        ".ach-entry-cost{font-size:12px;color:#fbbf24;white-space:nowrap}",
        ".ach-entry-tokens{font-size:11px;color:#64748b;white-space:nowrap}",
        ".ach-entry-template{font-size:10px;color:#a78bfa;background:#2d1b69;padding:1px 6px;border-radius:3px;white-space:nowrap}",
        ".ach-entry-err{font-size:10px;color:#fca5a5;background:#450a0a;padding:1px 6px;border-radius:3px;white-space:nowrap}",
        ".ach-entry-imgs{font-size:10px;color:#6ee7b7;white-space:nowrap}",
        ".ach-entry-spacer{flex:1}",
        ".ach-del-btn{background:none;border:none;color:#64748b;font-size:14px;cursor:pointer;padding:0 4px;line-height:1}",
        ".ach-del-btn:hover{color:#ef4444}",
        ".ach-entry-preview{padding:0 12px 8px;font-size:12px;cursor:pointer}",
        ".ach-entry-preview:hover{background:#2a2a48}",
        ".ach-prompt-pre{color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px}",
        ".ach-response-pre{color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-style:italic}",
        ".ach-detail{border-top:1px solid #334155;padding:14px;background:#1e1e38}",
        ".ach-detail-settings{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;font-size:11px}",
        ".ach-detail-settings span{background:#0f172a;padding:3px 8px;border-radius:3px;color:#94a3b8}",
        ".ach-detail-images{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}",
        ".ach-detail-thumb{border-radius:4px;object-fit:contain;background:#0f172a;cursor:pointer}",
        ".ach-detail-placeholder{border-radius:4px;background:#1e293b;display:flex;align-items:center;justify-content:center;color:#475569;font-size:10px}",
        ".ach-detail-section{margin-bottom:10px}",
        ".ach-detail-label{font-size:11px;color:#64748b;margin-bottom:4px;font-weight:500;text-transform:uppercase;letter-spacing:0.5px}",
        ".ach-text-wrap{position:relative}",
        ".ach-text-wrap .ach-copy-icon{position:absolute;top:6px;right:6px;opacity:0;transition:opacity 0.15s}",
        ".ach-text-wrap:hover .ach-copy-icon{opacity:1}",
        ".ach-copy-icon{background:#1e293b;border:1px solid #334155;color:#94a3b8;width:28px;height:28px;display:flex;align-items:center;justify-content:center;cursor:pointer;border-radius:4px;padding:0;line-height:1;transition:color 0.15s,background 0.15s,border-color 0.15s}",
        ".ach-copy-icon:hover{color:#e2e8f0;background:#334155;border-color:#475569}",
        ".ach-detail-text{background:#0f172a;border:1px solid #1e293b;border-radius:4px;padding:10px;font-size:12px;color:#e2e8f0;max-height:200px;overflow-y:auto;white-space:pre-wrap;word-break:break-word;font-family:'Cascadia Code','Fira Code',monospace;line-height:1.5}",
        ".ach-detail-text::-webkit-scrollbar{width:6px}",
        ".ach-detail-text::-webkit-scrollbar-thumb{background:#334155;border-radius:3px}",
        ".ach-detail-thinking{cursor:pointer}",
        ".ach-detail-thinking .ach-detail-label::after{content:' \\25BC';font-size:9px}",
        ".ach-detail-thinking.collapsed .ach-detail-label::after{content:' \\25B6'}",
        ".ach-detail-thinking.collapsed .ach-text-wrap{display:none}",
        ".ach-action-load{background:#1e3a5f;color:#60a5fa;padding:3px 10px;border:none;border-radius:3px;font-size:11px;cursor:pointer;font-weight:500;white-space:nowrap}",
        ".ach-action-load:hover{background:#1d4ed8;color:#fff}",
        ".ach-confirm{display:inline-flex;align-items:center;gap:4px;font-size:11px}",
        ".ach-confirm-yes{padding:3px 10px;background:#b91c1c;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:11px}",
        ".ach-confirm-no{padding:3px 10px;background:#334155;color:#94a3b8;border:none;border-radius:3px;cursor:pointer;font-size:11px}",
        ".ach-pagination{display:flex;align-items:center;justify-content:center;padding:10px 20px;border-top:1px solid #334155;gap:12px;flex-shrink:0}",
        ".ach-page-btn{padding:5px 14px;background:#1e293b;border:1px solid #334155;border-radius:4px;color:#94a3b8;font-size:12px;cursor:pointer}",
        ".ach-page-btn:hover:not(:disabled){background:#334155;color:#e2e8f0}",
        ".ach-page-btn:disabled{opacity:0.4;cursor:default}",
        ".ach-page-info{font-size:12px;color:#64748b}"
    ].join("\n");
    document.head.appendChild(s);
}

function _formatTs(iso) {
    if (!iso) return "";
    return iso.replace("T", " ").substring(0, 19);
}

var _copySvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';

function _createTextBlock(text, copyText) {
    var wrap = document.createElement("div");
    wrap.className = "ach-text-wrap";
    var textEl = document.createElement("div");
    textEl.className = "ach-detail-text";
    textEl.textContent = text;
    var copyBtn = document.createElement("button");
    copyBtn.className = "ach-copy-icon";
    copyBtn.innerHTML = _copySvg;
    copyBtn.title = "Copy";
    copyBtn.onclick = function (e) { e.stopPropagation(); _copyToClipboard(copyText || text); };
    wrap.appendChild(textEl);
    wrap.appendChild(copyBtn);
    return wrap;
}

function _createHistoryModal() {
    _injectHistoryStyles();

    var overlay = document.createElement("div");
    overlay.className = "ach-overlay";
    overlay.onclick = function (e) { if (e.target === overlay) _closeHistoryModal(); };

    var modal = document.createElement("div");
    modal.className = "ach-modal";


    var header = document.createElement("div");
    header.className = "ach-header";
    var title = document.createElement("span");
    title.className = "ach-title";
    title.textContent = "History";
    var stats = document.createElement("span");
    stats.className = "ach-stats";
    stats.textContent = "Loading...";
    var closeBtn = document.createElement("button");
    closeBtn.className = "ach-close";
    closeBtn.textContent = "\u00D7";
    closeBtn.onclick = _closeHistoryModal;
    header.appendChild(title);
    header.appendChild(stats);
    header.appendChild(closeBtn);


    var toolbar = document.createElement("div");
    toolbar.className = "ach-toolbar";

    var search = document.createElement("input");
    search.className = "ach-search";
    search.type = "text";
    search.placeholder = "Search prompts, responses, models...";
    search.oninput = function () {
        _histState.search = search.value;
        _histState.page = 1;
        clearTimeout(_histDebounce);
        _histDebounce = setTimeout(_fetchHistoryList, 300);
    };

    var dateFrom = document.createElement("input");
    dateFrom.className = "ach-date-input";
    dateFrom.type = "date";
    dateFrom.title = "From date";
    dateFrom.onchange = function () {
        _histState.dateFrom = dateFrom.value;
        _histState.page = 1;
        _fetchHistoryList();
    };

    var dateTo = document.createElement("input");
    dateTo.className = "ach-date-input";
    dateTo.type = "date";
    dateTo.title = "To date";
    dateTo.onchange = function () {
        _histState.dateTo = dateTo.value;
        _histState.page = 1;
        _fetchHistoryList();
    };

    var sortSel = document.createElement("select");
    sortSel.className = "ach-select";
    var sortOpts = [
        ["date_desc", "Newest first"],
        ["date_asc", "Oldest first"],
        ["cost_desc", "Highest cost"],
        ["tokens_desc", "Most tokens"]
    ];
    for (var i = 0; i < sortOpts.length; i++) {
        var opt = document.createElement("option");
        opt.value = sortOpts[i][0];
        opt.textContent = sortOpts[i][1];
        sortSel.appendChild(opt);
    }
    sortSel.onchange = function () {
        _histState.sortBy = sortSel.value;
        _histState.page = 1;
        _fetchHistoryList();
    };

    var favBtn = document.createElement("button");
    favBtn.className = "ach-btn ach-btn-fav";
    favBtn.textContent = "\u2606 Favorites";
    favBtn.onclick = function () {
        _histState.favoritesOnly = !_histState.favoritesOnly;
        _histState.page = 1;
        favBtn.className = "ach-btn ach-btn-fav" + (_histState.favoritesOnly ? " active" : "");
        favBtn.textContent = (_histState.favoritesOnly ? "\u2605" : "\u2606") + " Favorites";
        _fetchHistoryList();
    };

    toolbar.appendChild(search);
    toolbar.appendChild(dateFrom);
    toolbar.appendChild(dateTo);
    toolbar.appendChild(sortSel);
    toolbar.appendChild(favBtn);


    var list = document.createElement("div");
    list.className = "ach-list";


    var pagination = document.createElement("div");
    pagination.className = "ach-pagination";
    var prevBtn = document.createElement("button");
    prevBtn.className = "ach-page-btn";
    prevBtn.textContent = "\u2190 Prev";
    prevBtn.onclick = function () {
        if (_histState.page > 1) {
            _histState.page--;
            _fetchHistoryList();
        }
    };
    var pageInfo = document.createElement("span");
    pageInfo.className = "ach-page-info";
    pageInfo.textContent = "Page 1 of 1";
    var nextBtn = document.createElement("button");
    nextBtn.className = "ach-page-btn";
    nextBtn.textContent = "Next \u2192";
    nextBtn.onclick = function () {
        if (_histState.page < _histState.totalPages) {
            _histState.page++;
            _fetchHistoryList();
        }
    };
    pagination.appendChild(prevBtn);
    pagination.appendChild(pageInfo);
    pagination.appendChild(nextBtn);

    modal.appendChild(header);
    modal.appendChild(toolbar);
    modal.appendChild(list);
    modal.appendChild(pagination);
    overlay.appendChild(modal);

    _histEls = {
        overlay: overlay, stats: stats, search: search,
        dateFrom: dateFrom, dateTo: dateTo, sortSel: sortSel, favBtn: favBtn,
        list: list, prevBtn: prevBtn, nextBtn: nextBtn, pageInfo: pageInfo
    };

    return overlay;
}

function _openHistoryModal(node) {
    _histCurrentNode = node;
    _histState.page = 1;
    _histState.search = "";
    _histState.dateFrom = "";
    _histState.dateTo = "";
    _histState.favoritesOnly = false;
    _histState.sortBy = "date_desc";
    _histState.expandedId = null;

    if (!_histOverlay) {
        _histOverlay = _createHistoryModal();
    }

    _histEls.search.value = "";
    _histEls.dateFrom.value = "";
    _histEls.dateTo.value = "";
    _histEls.sortSel.value = "date_desc";
    _histEls.favBtn.className = "ach-btn ach-btn-fav";
    _histEls.favBtn.textContent = "\u2606 Favorites";
    _histEls.stats.textContent = "Loading...";
    _histEls.list.innerHTML = "";

    document.body.appendChild(_histOverlay);
    _histEls.search.focus();

    _fetchHistoryStats();
    _fetchHistoryList();
}

function _closeHistoryModal() {
    if (_histOverlay && _histOverlay.parentNode) {
        _histOverlay.parentNode.removeChild(_histOverlay);
    }
    _histCurrentNode = null;
}

function _fetchHistoryStats() {
    fetch("/anthropic_claude/history/stats")
        .then(function (r) { return r.json(); })
        .then(function (d) {
            var parts = [];
            parts.push(d.total_runs + " runs");
            if (d.total_cost > 0) {
                parts.push("$" + d.total_cost.toFixed(2) + " total");
            }
            if (d.total_tokens > 0) {
                var tk = d.total_tokens > 1000000
                    ? (d.total_tokens / 1000000).toFixed(1) + "M"
                    : d.total_tokens > 1000
                        ? (d.total_tokens / 1000).toFixed(1) + "K"
                        : d.total_tokens;
                parts.push(tk + " tokens");
            }
            if (d.most_used_model) {
                parts.push("Top: " + d.most_used_model);
            }
            if (d.truncated) {
                parts.push("partial totals");
            }
            _histEls.stats.textContent = parts.join("  \u2022  ");
        })
        .catch(function () {
            _histEls.stats.textContent = "";
        });
}

function _fetchHistoryList() {
    var params = "?page=" + _histState.page
        + "&per_page=" + _histState.perPage
        + "&sort_by=" + _histState.sortBy;
    if (_histState.search) params += "&search=" + encodeURIComponent(_histState.search);
    if (_histState.dateFrom) params += "&date_from=" + _histState.dateFrom;
    if (_histState.dateTo) params += "&date_to=" + _histState.dateTo;
    if (_histState.favoritesOnly) params += "&favorites_only=true";

    fetch("/anthropic_claude/history/list" + params)
        .then(function (r) { return r.json(); })
        .then(function (d) {
            _histState.total = d.total;
            _histState.totalPages = d.total_pages;
            _renderHistoryList(d.entries);
            if (d.truncated) {


                var note = document.createElement("div");
                note.className = "ach-note";
                note.textContent = "Older entries were not included. Narrow the date range to reach them.";
                _histEls.list.insertBefore(note, _histEls.list.firstChild);
            }
            _histEls.pageInfo.textContent = "Page " + d.page + " of " + d.total_pages + " (" + d.total + " total)";
            _histEls.prevBtn.disabled = d.page <= 1;
            _histEls.nextBtn.disabled = d.page >= d.total_pages;
        })
        .catch(function () {
            _histEls.list.innerHTML = '<div class="ach-empty">Failed to load history</div>';
        });
}

function _renderHistoryList(entries) {
    var list = _histEls.list;
    list.innerHTML = "";
    if (!entries || entries.length === 0) {
        list.innerHTML = '<div class="ach-empty">No history entries found</div>';
        return;
    }
    for (var i = 0; i < entries.length; i++) {
        list.appendChild(_renderHistoryEntry(entries[i]));
    }
}

function _renderHistoryEntry(entry) {
    var el = document.createElement("div");
    el.className = "ach-entry";
    el.setAttribute("data-id", entry.id);
    el.setAttribute("data-date", entry.date);


    var head = document.createElement("div");
    head.className = "ach-entry-head";

    var favBtn = document.createElement("button");
    favBtn.className = "ach-fav-btn" + (entry.favorite ? " active" : "");
    favBtn.textContent = entry.favorite ? "\u2605" : "\u2606";
    favBtn.onclick = function (e) {
        e.stopPropagation();
        _toggleFavorite(entry.id, entry.date, favBtn);
    };

    var dateSpan = document.createElement("span");
    dateSpan.className = "ach-entry-date";
    dateSpan.textContent = _formatTs(entry.timestamp);

    var modelSpan = document.createElement("span");
    modelSpan.className = "ach-entry-model";
    modelSpan.textContent = entry.model_display || entry.model;

    var costSpan = document.createElement("span");
    costSpan.className = "ach-entry-cost";
    costSpan.textContent = entry.cost_str || "";

    var tokenSpan = document.createElement("span");
    tokenSpan.className = "ach-entry-tokens";
    tokenSpan.textContent = "In:" + entry.input_tokens + " Out:" + entry.output_tokens;

    head.appendChild(favBtn);
    head.appendChild(dateSpan);
    head.appendChild(modelSpan);
    head.appendChild(costSpan);
    head.appendChild(tokenSpan);

    if (entry.template && entry.template !== "None") {
        var tplBadge = document.createElement("span");
        tplBadge.className = "ach-entry-template";
        tplBadge.textContent = entry.template;
        head.appendChild(tplBadge);
    }

    if (entry.error) {
        var errBadge = document.createElement("span");
        errBadge.className = "ach-entry-err";
        errBadge.textContent = "ERROR";
        head.appendChild(errBadge);
    }

    if (entry.image_count > 0) {
        var imgBadge = document.createElement("span");
        imgBadge.className = "ach-entry-imgs";
        imgBadge.textContent = "\uD83D\uDDBC";
        head.appendChild(imgBadge);
    }

    var spacer = document.createElement("span");
    spacer.className = "ach-entry-spacer";
    head.appendChild(spacer);

    var delBtn = document.createElement("button");
    delBtn.className = "ach-del-btn";
    delBtn.textContent = "\u00D7";
    delBtn.title = "Delete";
    delBtn.onclick = function (e) {
        e.stopPropagation();
        _confirmDelete(entry.id, entry.date, el, delBtn);
    };
    head.appendChild(delBtn);


    var preview = document.createElement("div");
    preview.className = "ach-entry-preview";
    var promptPre = document.createElement("div");
    promptPre.className = "ach-prompt-pre";
    promptPre.textContent = entry.prompt_preview || "(empty prompt)";
    var responsePre = document.createElement("div");
    responsePre.className = "ach-response-pre";
    responsePre.textContent = entry.error
        ? entry.error
        : (entry.response_preview || "(no response)");
    preview.appendChild(promptPre);
    preview.appendChild(responsePre);

    el.appendChild(head);
    el.appendChild(preview);


    var clickArea = function (e) {
        if (e.target.tagName === "BUTTON") return;
        var detail = el.querySelector(".ach-detail");
        if (detail) {
            el.removeChild(detail);
            _histState.expandedId = null;
        } else {
            _expandEntry(entry.id, entry.date, el);
        }
    };
    head.onclick = clickArea;
    preview.onclick = clickArea;

    return el;
}

function _expandEntry(entryId, date, el) {
    
    var prev = _histEls.list.querySelector(".ach-detail");
    if (prev) prev.parentNode.removeChild(prev);

    _histState.expandedId = entryId;

    var placeholder = document.createElement("div");
    placeholder.className = "ach-detail";
    placeholder.innerHTML = '<div style="color:#64748b;font-size:12px;padding:8px">Loading...</div>';
    el.appendChild(placeholder);


    var status = 0;
    fetch("/anthropic_claude/history/entry?id=" + encodeURIComponent(entryId)
        + "&date=" + encodeURIComponent(date))
        .then(function (r) { status = r.status; return r.json(); })
        .then(function (entry) {
            if (status !== 200 || !entry || !entry.id) {
                placeholder.innerHTML = '<div style="color:#ef4444;font-size:12px;padding:8px">Entry not found</div>';
                return;
            }
            _renderDetail(entry, placeholder);
        })
        .catch(function () {
            placeholder.innerHTML = '<div style="color:#ef4444;font-size:12px;padding:8px">Failed to load entry</div>';
        });
}

function _renderDetail(entry, container) {
    container.innerHTML = "";


    var settings = document.createElement("div");
    settings.className = "ach-detail-settings";
    var settingItems = [
        ["Seed", entry.seed],
        ["Temp", entry.temperature],
        ["Max Tokens", entry.max_tokens],
        ["Thinking", entry.extended_thinking ? "ON (" + entry.thinking_budget + ")" : "OFF"],
        ["Image Size", entry.max_image_size + "px"],
    ];
    if (entry.duration_ms > 0) {
        settingItems.push(["Duration", (entry.duration_ms / 1000).toFixed(1) + "s"]);
    }
    for (var i = 0; i < settingItems.length; i++) {
        var sp = document.createElement("span");
        sp.textContent = settingItems[i][0] + ": " + settingItems[i][1];
        settings.appendChild(sp);
    }
    var loadBtn = document.createElement("button");
    loadBtn.className = "ach-action-load";
    loadBtn.textContent = "Load Settings";
    loadBtn.onclick = function () { _loadSettings(entry); };
    settings.appendChild(loadBtn);
    container.appendChild(settings);


    if (entry.image_count > 0) {
        var imgBox = document.createElement("div");
        imgBox.className = "ach-detail-images";
        for (var j = 0; j < entry.image_count; j++) {
            (function (idx) {
                var dim = (entry.image_dimensions && entry.image_dimensions[idx]) || { width: 300, height: 300 };
                var maxPh = 150;
                var ar = dim.width / dim.height;
                var phW, phH;
                if (ar > 1) { phW = maxPh; phH = Math.round(maxPh / ar); }
                else { phH = maxPh; phW = Math.round(maxPh * ar); }

                var img = document.createElement("img");
                img.className = "ach-detail-thumb";
                img.src = "/anthropic_claude/history/image?id=" + encodeURIComponent(entry.id)
                    + "&date=" + encodeURIComponent(entry.date)
                    + "&index=" + idx;
                img.style.width = phW + "px";
                img.style.height = phH + "px";
                img.onerror = function () {
                    var ph = document.createElement("div");
                    ph.className = "ach-detail-placeholder";
                    ph.style.width = phW + "px";
                    ph.style.height = phH + "px";
                    ph.textContent = "Not found";
                    img.parentNode.replaceChild(ph, img);
                };
                imgBox.appendChild(img);
            })(j);
        }
        container.appendChild(imgBox);
    }


    var promptSec = document.createElement("div");
    promptSec.className = "ach-detail-section";
    var promptLabel = document.createElement("div");
    promptLabel.className = "ach-detail-label";
    promptLabel.textContent = "Prompt";
    promptSec.appendChild(promptLabel);
    promptSec.appendChild(_createTextBlock(entry.prompt || "(empty)", entry.prompt || ""));
    container.appendChild(promptSec);


    if (entry.response) {
        var respSec = document.createElement("div");
        respSec.className = "ach-detail-section";
        var respLabel = document.createElement("div");
        respLabel.className = "ach-detail-label";
        respLabel.textContent = "Response";
        respSec.appendChild(respLabel);
        respSec.appendChild(_createTextBlock(entry.response, entry.response));
        container.appendChild(respSec);
    }


    if (entry.error) {
        var errSec = document.createElement("div");
        errSec.className = "ach-detail-section";
        var errLabel = document.createElement("div");
        errLabel.className = "ach-detail-label";
        errLabel.textContent = "Error";
        var errText = document.createElement("div");
        errText.className = "ach-detail-text";
        errText.style.color = "#fca5a5";
        errText.textContent = entry.error;
        errSec.appendChild(errLabel);
        errSec.appendChild(errText);
        container.appendChild(errSec);
    }


    if (entry.thinking) {
        var thinkSec = document.createElement("div");
        thinkSec.className = "ach-detail-section ach-detail-thinking collapsed";
        var thinkLabel = document.createElement("div");
        thinkLabel.className = "ach-detail-label";
        thinkLabel.textContent = "Thinking";
        thinkLabel.style.cursor = "pointer";
        thinkLabel.onclick = function () {
            if (thinkSec.classList.contains("collapsed")) {
                thinkSec.classList.remove("collapsed");
            } else {
                thinkSec.classList.add("collapsed");
            }
        };
        thinkSec.appendChild(thinkLabel);
        thinkSec.appendChild(_createTextBlock(entry.thinking, entry.thinking));
        container.appendChild(thinkSec);
    }
}

function _toggleFavorite(entryId, date, btn) {
    fetch("/anthropic_claude/history/favorite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: entryId, date: date })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        if (d && typeof d.favorite === "boolean") {
            btn.className = "ach-fav-btn" + (d.favorite ? " active" : "");
            btn.textContent = d.favorite ? "\u2605" : "\u2606";
        } else {
            showToast("Failed to update favorite", true);
        }
    })
    .catch(function () {
        showToast("Failed to update favorite", true);
    });
}

function _confirmDelete(entryId, date, entryEl, delBtn) {
    delBtn.style.display = "none";

    var confirm = document.createElement("span");
    confirm.className = "ach-confirm";
    confirm.innerHTML = 'Delete? ';

    var yesBtn = document.createElement("button");
    yesBtn.className = "ach-confirm-yes";
    yesBtn.textContent = "Yes";
    yesBtn.onclick = function (e) {
        e.stopPropagation();
        _deleteEntry(entryId, date, entryEl);
    };

    var noBtn = document.createElement("button");
    noBtn.className = "ach-confirm-no";
    noBtn.textContent = "No";
    noBtn.onclick = function (e) {
        e.stopPropagation();
        delBtn.style.display = "";
        confirm.parentNode.removeChild(confirm);
    };

    confirm.appendChild(yesBtn);
    confirm.appendChild(noBtn);
    delBtn.parentNode.insertBefore(confirm, delBtn.nextSibling);
}

function _deleteEntry(entryId, date, entryEl) {
    fetch("/anthropic_claude/history/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: entryId, date: date })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        if (d.ok) {
            entryEl.style.transition = "opacity 0.2s";
            entryEl.style.opacity = "0";
            setTimeout(function () {
                if (entryEl.parentNode) entryEl.parentNode.removeChild(entryEl);
                _histState.total--;
                _histEls.pageInfo.textContent = "Page " + _histState.page + " of " + _histState.totalPages + " (" + _histState.total + " total)";
                _fetchHistoryStats();
                if (_histEls.list.children.length === 0 && _histState.page > 1) {
                    _histState.page--;
                    _fetchHistoryList();
                }
            }, 200);
            showToast("Entry deleted", false);
        } else {
            showToast("Failed to delete entry", true);
        }
    })
    .catch(function () {
        showToast("Failed to delete entry", true);
    });
}


var _templateAliases = {};
var _templateAliasesLoaded = false;


function _resolveTemplateName(name, values) {
    if (typeof name !== "string" || !name || !values) return null;
    if (values.indexOf(name) !== -1) return name;
    if (Object.prototype.hasOwnProperty.call(_templateAliases, name)) {
        var target = _templateAliases[name];
        if (target && values.indexOf(target) !== -1) return target;
    }
    return null;
}


function _restoreTemplateWidget(w, savedName, node, isRetry) {
    var values = (w.options && w.options.values) ? w.options.values : null;
    var resolved = _resolveTemplateName(savedName, values);
    if (resolved) {
        w.value = resolved;
        if (w.callback) w.callback(resolved);
        return;
    }
    if (!_templateAliasesLoaded && !isRetry && node && node._acRefreshTemplateList) {
        var pending = node._acRefreshTemplateList();
        if (pending && pending.then) {
            pending.then(function () {
                _restoreTemplateWidget(w, savedName, node, true);
                node.setDirtyCanvas(true, true);
            });
            return;
        }
    }
    if (!_templateAliasesLoaded) {
        showToast("Template list has not loaded yet, template not restored", true);
    } else {
        showToast("Template '" + savedName + "' not available, skipped", true);
    }
}

function _loadSettings(entry) {
    var node = _histCurrentNode;
    if (!node) {
        showToast("No node reference", true);
        return;
    }

    function findWidget(name) {
        for (var i = 0; i < node.widgets.length; i++) {
            if (node.widgets[i].name === name) return node.widgets[i];
        }
        return null;
    }

    var w;

    w = findWidget("prompt");
    if (w) w.value = entry.prompt || "";

    w = findWidget("model");
    if (w) {
        var display = entry.model_display || entry.model;
        if (w.options && w.options.values && w.options.values.indexOf(display) !== -1) {
            w.value = display;
        } else {
            showToast("Model '" + display + "' not available, skipped", true);
        }
    }

    w = findWidget("seed");
    if (w && entry.seed !== undefined) w.value = entry.seed;

    w = findWidget("template");
    if (w && entry.template) {
        _restoreTemplateWidget(w, entry.template, node, false);
    }

    w = findWidget("temperature");
    if (w && entry.temperature !== undefined) w.value = entry.temperature;

    w = findWidget("max_tokens");
    if (w && entry.max_tokens !== undefined) w.value = entry.max_tokens;

    w = findWidget("extended_thinking");
    if (w && entry.extended_thinking !== undefined) w.value = entry.extended_thinking;

    w = findWidget("thinking_budget");
    if (w && entry.thinking_budget !== undefined) w.value = entry.thinking_budget;

    w = findWidget("max_image_size");
    if (w && entry.max_image_size !== undefined) w.value = entry.max_image_size;

    node.setDirtyCanvas(true, true);
    _closeHistoryModal();
    showToast("Settings loaded from history", false);
}


var _apiStatus = "unknown";
var _statusDots = [];
var _statusPollingStarted = false;

var _statusColors = {
    operational: "#16a34a",
    degraded_performance: "#eab308",
    partial_outage: "#f97316",
    major_outage: "#b91c1c",
    under_maintenance: "#6366f1",
    unknown: "#666666"
};

var _statusLabels = {
    operational: "API: Operational",
    degraded_performance: "API: Degraded",
    partial_outage: "API: Partial Outage",
    major_outage: "API: Major Outage",
    under_maintenance: "API: Maintenance",
    unknown: "API: Checking..."
};

function updateAllStatusDots() {
    var color = _statusColors[_apiStatus] || _statusColors.unknown;
    var label = _statusLabels[_apiStatus] || _statusLabels.unknown;
    for (var i = 0; i < _statusDots.length; i++) {
        _statusDots[i].style.color = color;
        _statusDots[i].title = label;
    }
}

function fetchApiStatus() {
    fetch("https://status.claude.com/api/v2/components.json")
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.components) {
                for (var i = 0; i < data.components.length; i++) {
                    if (data.components[i].name && data.components[i].name.indexOf("Claude API") !== -1) {
                        _apiStatus = data.components[i].status || "unknown";
                        updateAllStatusDots();
                        return;
                    }
                }
            }
            _apiStatus = "unknown";
            updateAllStatusDots();
        })
        .catch(function () {
            _apiStatus = "unknown";
            updateAllStatusDots();
        });
}

function startApiStatusPolling() {
    if (_statusPollingStarted) return;
    _statusPollingStarted = true;
    fetchApiStatus();
    setInterval(fetchApiStatus, 60000);
}


function syncDisableState(node) {
    var instructionsConnected = false;
    if (node.inputs) {
        for (var k = 0; k < node.inputs.length; k++) {
            if (node.inputs[k].name === "instructions" && node.inputs[k].link != null) {
                instructionsConnected = true;
                break;
            }
        }
    }
    if (node._acTemplateWidget) {
        node._acTemplateWidget.disabled = instructionsConnected;
    }
    if (node._acSaveButton) {
        node._acSaveButton.disabled = instructionsConnected;
    }
}

app.registerExtension({
    name: "AnthropicClaude.NodeStyle",
    beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AnthropicClaudeNode") {
            var proto = nodeType.prototype;

            var onNodeCreated = proto.onNodeCreated;
            proto.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }
                this.color = "#223";
                this.bgcolor = "#335";
                this._costText = null;
                this._usageText = null;
                this._errorText = null;

                var node = this;

                var templateWidget = null;
                var instructionsWidget = null;
                var promptWidget = null;
                var modelWidget = null;
                for (var w = 0; w < this.widgets.length; w++) {
                    if (this.widgets[w].name === "template") templateWidget = this.widgets[w];
                    if (this.widgets[w].name === "instructions") instructionsWidget = this.widgets[w];
                    if (this.widgets[w].name === "prompt") promptWidget = this.widgets[w];
                    if (this.widgets[w].name === "model") modelWidget = this.widgets[w];
                }

                var seedWidget = null;
                var seedCtrlWidget = null;
                for (var w = 0; w < this.widgets.length; w++) {
                    if (this.widgets[w].name === "seed") {
                        seedWidget = this.widgets[w];
                        if (w + 1 < this.widgets.length) {
                            var ctrl = this.widgets[w + 1];
                            if (ctrl.options && ctrl.options.values &&
                                ctrl.options.values.indexOf("fixed") !== -1 &&
                                ctrl.options.values.indexOf("randomize") !== -1) {
                                ctrl.value = "fixed";
                                seedCtrlWidget = ctrl;
                            }
                        }
                        break;
                    }
                }

                var seedRef = seedWidget;
                var ctrlRef = seedCtrlWidget;
                this.addWidget("button", "Randomize Seed", null, function () {
                    if (seedRef) {
                        seedRef.value = Math.floor(Math.random() * 1125899906842624);
                        if (ctrlRef) ctrlRef.value = "fixed";
                        node.setDirtyCanvas(true, true);
                    }
                });

                var credentialContainer = document.createElement("div");
                credentialContainer.style.cssText = "width:100%;box-sizing:border-box;padding:4px 10px 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;";

                var credentialRow = document.createElement("div");
                credentialRow.style.cssText = "display:flex;gap:6px;align-items:center;";

                var credentialInput = document.createElement("input");
                credentialInput.type = "password";
                credentialInput.value = "";
                credentialInput.placeholder = "Anthropic API key";
                credentialInput.autocomplete = "off";
                credentialInput.spellcheck = false;
                credentialInput.setAttribute("aria-label", "Anthropic API key");
                credentialInput.style.cssText = "flex:1;min-width:0;box-sizing:border-box;padding:7px 9px;background:#1a1a2e;border:1px solid #445;border-radius:4px;color:#eee;font-size:12px;outline:none;";
                credentialInput.onfocus = function () {
                    credentialInput.style.borderColor = "#6677aa";
                };
                credentialInput.onblur = function () {
                    credentialInput.style.borderColor = "#445";
                };

                var credentialButton = document.createElement("button");
                credentialButton.textContent = "Save & validate";
                credentialButton.style.cssText = "padding:7px 10px;background:#445577;border:1px solid #556688;border-radius:4px;color:#eef;cursor:pointer;font-size:12px;white-space:nowrap;";
                credentialButton.onclick = function () {
                    _saveCredential(credentialInput);
                };

                var credentialStatus = document.createElement("div");
                credentialStatus.textContent = "Key: Checking...";
                credentialStatus.style.cssText = "padding-top:4px;color:#eab308;font-size:11px;";

                credentialRow.appendChild(credentialInput);
                credentialRow.appendChild(credentialButton);
                credentialContainer.appendChild(credentialRow);
                credentialContainer.appendChild(credentialStatus);

                var credentialWidget = this.addDOMWidget(
                    "credential_control",
                    "custom",
                    credentialContainer,
                    { hideOnZoom: false, serialize: false }
                );
                credentialWidget.serialize = false;
                credentialWidget.serializeValue = function () {
                    return undefined;
                };
                delete credentialWidget.computeLayoutSize;
                credentialWidget.computeSize = function () {
                    return [0, 62];
                };
                _registerCredentialControl(
                    node,
                    credentialStatus,
                    credentialButton,
                    modelWidget
                );

                var previousRemoved = this.onRemoved;
                this.onRemoved = function () {
                    credentialInput.value = "";
                    _unregisterCredentialControl(node);
                    if (previousRemoved) {
                        previousRemoved.apply(this, arguments);
                    }
                };

                function refreshTemplateList(selectName) {
                    if (!templateWidget) return null;
                    return fetch("/anthropic_claude/list_templates")
                        .then(function (res) { return res.json(); })
                        .then(function (data) {
                            if (data.aliases) {
                                _templateAliases = data.aliases;
                                _templateAliasesLoaded = true;
                            }
                            if (data.templates) {
                                templateWidget.options.values = data.templates;
                                if (selectName) {
                                    templateWidget.value = selectName;
                                }
                                node.setDirtyCanvas(true, true);
                            }
                        })
                        .catch(function () {});
                }

                if (templateWidget && instructionsWidget) {
                    var origCallback = templateWidget.callback;
                    templateWidget.callback = function (value) {
                        if (origCallback) origCallback.apply(this, arguments);
                        if (!value || value === "None") {
                            instructionsWidget.value = "";
                            node.setDirtyCanvas(true, true);
                            return;
                        }
                        fetch("/anthropic_claude/load_template?name=" + encodeURIComponent(value))
                            .then(function (res) { return res.json(); })
                            .then(function (data) {
                                if (data.content) {
                                    instructionsWidget.value = data.content;
                                    node.setDirtyCanvas(true, true);
                                }
                            })
                            .catch(function () {});
                    };
                }

                var saveButton = this.addWidget("button", "Save Instructions as Template", null, function () {
                    if (!instructionsWidget) return;
                    var content = instructionsWidget.value || "";
                    if (!content.trim()) {
                        showToast("Instructions are empty. Nothing to save.", true);
                        return;
                    }
                    showInputDialog("Template name:", function (name) {
                        _postTemplate(name, content, false, refreshTemplateList);
                    });
                });

                this.addWidget("button", "\u21BB Refresh Templates", null, function () {
                    refreshTemplateList();
                    showToast("Templates refreshed", false);
                });

                this.addWidget("button", "\u25F7 History", null, function () {
                    _openHistoryModal(node);
                });

                refreshTemplateList();

                var FOOTER_H = 38;

                var footerContainer = document.createElement("div");
                footerContainer.style.cssText = "width:100%;font-family:monospace;font-size:12px;user-select:text;pointer-events:none;";

                var costLine = document.createElement("div");
                costLine.style.cssText = "display:flex;align-items:center;padding:4px 10px 10px;gap:6px;";
                var statusDot = document.createElement("span");
                statusDot.textContent = "\u25CF";
                statusDot.style.cssText = "font-size:30px;color:#666666;line-height:0;cursor:default;pointer-events:auto;";
                statusDot.title = "API: Checking...";
                _statusDots.push(statusDot);
                var costSpan = document.createElement("span");
                costSpan.style.color = "#556677";
                costSpan.textContent = "---";
                var usageSpan = document.createElement("span");
                usageSpan.style.cssText = "color:#445566;margin-left:auto;";
                usageSpan.textContent = "awaiting execution";
                costLine.appendChild(statusDot);
                costLine.appendChild(costSpan);
                costLine.appendChild(usageSpan);

                var errorLine = document.createElement("div");
                errorLine.style.cssText = "display:none;padding:2px 10px 4px;color:#FF6666;font-size:11px;word-wrap:break-word;";

                footerContainer.appendChild(costLine);
                footerContainer.appendChild(errorLine);

                var footerWidget = this.addDOMWidget("cost_footer", "custom", footerContainer, {
                    hideOnZoom: false,
                    serialize: false
                });


                delete footerWidget.computeLayoutSize;
                footerWidget.computeSize = function () {
                    var h = FOOTER_H - 4;
                    if (errorLine.style.display !== "none") {
                        h += errorLine.scrollHeight || 18;
                    }
                    return [0, h];
                };

                this._acTemplateWidget = templateWidget;
                this._acSaveButton = saveButton;
                this._acRefreshTemplateList = refreshTemplateList;
                this._acCostSpan = costSpan;
                this._acUsageSpan = usageSpan;
                this._acErrorLine = errorLine;

                syncDisableState(this);
                checkStartupWarnings();
                startApiStatusPolling();
                _checkApiHealth();
            };

            var onConnectionsChange = proto.onConnectionsChange;
            proto.onConnectionsChange = function () {
                if (onConnectionsChange) {
                    onConnectionsChange.apply(this, arguments);
                }
                if (this._acRefreshTemplateList) {
                    this._acRefreshTemplateList();
                }
                syncDisableState(this);
            };

            var onExecuted = proto.onExecuted;
            proto.onExecuted = function (output) {
                if (onExecuted) {
                    onExecuted.apply(this, arguments);
                }
                if (output) {
                    if (output.cost && output.cost[0]) {
                        this._costText = output.cost[0];
                    }
                    if (output.usage && output.usage[0]) {
                        this._usageText = output.usage[0];
                    }
                    if (output.error && output.error[0]) {
                        this._errorText = output.error[0];
                        var errLower = this._errorText.toLowerCase();
                        if (errLower.indexOf("invalid api key") !== -1
                            || errLower.indexOf("saved anthropic api key is invalid") !== -1) {
                            _showApiErrorModal({error_type: "auth_error"}, this);
                        } else if (errLower.indexOf("rate limit") !== -1) {
                            _showApiErrorModal({error_type: "rate_limit", error: "You've been rate limited by the Anthropic API. Wait a moment and try again."}, this);
                        } else if (errLower.indexOf("add and validate an anthropic api key") !== -1) {
                            _showApiErrorModal({error_type: "missing_key"}, this);
                        }
                    } else {
                        this._errorText = null;
                    }
                    
                    if (this._acCostSpan) {
                        this._acCostSpan.textContent = this._costText || "---";
                        this._acCostSpan.style.color = this._costText ? "#FFD700" : "#556677";
                    }
                    if (this._acUsageSpan) {
                        this._acUsageSpan.textContent = this._usageText || "awaiting execution";
                        this._acUsageSpan.style.color = this._usageText ? "#8899AA" : "#445566";
                    }
                    if (this._acErrorLine) {
                        if (this._errorText) {
                            this._acErrorLine.textContent = "\u26A0 " + this._errorText;
                            this._acErrorLine.style.display = "block";
                        } else {
                            this._acErrorLine.style.display = "none";
                        }
                    }
                    
                    var minSize = this.computeSize();
                    if (this.size[1] < minSize[1]) {
                        this.setSize([this.size[0], minSize[1]]);
                    }
                    this.setDirtyCanvas(true, true);
                }
            };
        }
    }
});
