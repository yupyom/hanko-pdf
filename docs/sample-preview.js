(function () {
  "use strict";

  function closeDialog(dialog) {
    if (dialog && dialog.open) {
      dialog.close();
    }
  }

  document.querySelectorAll("[data-preview-open]").forEach(function (trigger) {
    var dialog = document.getElementById(trigger.dataset.previewOpen);

    if (!dialog || typeof dialog.showModal !== "function") {
      return;
    }

    trigger.addEventListener("click", function () {
      dialog.showModal();
    });
  });

  document.querySelectorAll("[data-preview-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      closeDialog(button.closest("dialog"));
    });
  });

  document.querySelectorAll("dialog[data-preview-dialog]").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        closeDialog(dialog);
      }
    });
  });
}());
