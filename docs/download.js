(function () {
  "use strict";

  var config = window.HANKO_DOWNLOAD_CONFIG;

  if (!config || !config.platforms) {
    return;
  }

  function detectPlatform() {
    var userAgentData = navigator.userAgentData;
    var platform = userAgentData && userAgentData.platform ? userAgentData.platform : "";
    var signature = [platform, navigator.platform || "", navigator.userAgent || ""].join(" ");

    if (/Windows/i.test(signature)) {
      return "windows";
    }

    if (/Linux/i.test(signature)) {
      return "linux";
    }

    if (/(Mac|iPhone|iPad|iPod)/i.test(signature)) {
      return "mac";
    }

    return null;
  }

  function getEnabledPlatforms() {
    return Object.keys(config.platforms).filter(function (platform) {
      return config.platforms[platform].enabled;
    });
  }

  function selectPlatform() {
    var enabledPlatforms = getEnabledPlatforms();
    var detectedPlatform = detectPlatform();
    var fallbackPlatform = config.fallbackPlatform;

    if (detectedPlatform && config.platforms[detectedPlatform] && config.platforms[detectedPlatform].enabled) {
      return detectedPlatform;
    }

    if (fallbackPlatform && config.platforms[fallbackPlatform] && config.platforms[fallbackPlatform].enabled) {
      return fallbackPlatform;
    }

    return enabledPlatforms[0] || null;
  }

  function updateDownloadLinks(platform) {
    var download = config.platforms[platform];

    if (!download) {
      return;
    }

    document.querySelectorAll("[data-download-link]").forEach(function (link) {
      link.href = download.url;
      link.textContent = download.label;
      link.setAttribute("aria-label", download.label);
    });
  }

  function updatePlatformCopy() {
    var enabledPlatforms = getEnabledPlatforms();
    var isMacOnly = enabledPlatforms.length === 1 && enabledPlatforms[0] === "mac";

    if (isMacOnly) {
      return;
    }

    var eyebrow = document.querySelector("[data-download-eyebrow]");
    var title = document.querySelector("[data-download-title]");
    var description = document.querySelector("[data-download-description]");

    if (eyebrow) {
      eyebrow.textContent = "FREEWARE FOR DESKTOP";
    }

    if (title) {
      title.textContent = "デスクトップ向けフリーウェアとして公開中。";
    }

    if (description) {
      description.textContent = "Hanko PDFは、PDFへハンコを押して保存するためのフリーウェアです。ソースコードもGitHubで公開しています。";
    }
  }

  var selectedPlatform = selectPlatform();

  if (!selectedPlatform) {
    return;
  }

  updateDownloadLinks(selectedPlatform);
  updatePlatformCopy();
}());
