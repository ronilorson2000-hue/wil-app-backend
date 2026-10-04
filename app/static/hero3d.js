(function () {
  function start() {
    var canvas = document.getElementById('hero-3d');
    if (!canvas || !window.THREE) return;
    var hero = canvas.parentElement;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var small = window.innerWidth < 700;
    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: !small, alpha: true, powerPreference: 'low-power' });
    } catch (e) { return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.25 : 1.75));

    var scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x0b1220, 0.038);
    var camera = new THREE.PerspectiveCamera(72, 1, 0.1, 120);

    var DEPTH = 60;
    var SPEED = 8;
    var CARD_COUNT = small ? 26 : 46;
    var PALETTES = [['#1D4ED8', '#38BDF8'], ['#1E3A8A', '#3B82F6'], ['#0E7490', '#22D3EE'], ['#312E81', '#60A5FA'], ['#0F172A', '#2563EB']];

    function roundRect(g, x, y, w, h, r) {
      g.beginPath();
      g.moveTo(x + r, y);
      g.arcTo(x + w, y, x + w, y + h, r);
      g.arcTo(x + w, y + h, x, y + h, r);
      g.arcTo(x, y + h, x, y, r);
      g.arcTo(x, y, x + w, y, r);
      g.closePath();
    }

    // Une « vidéo verticale » avec un score de viralité : l'idée de Wil App, en 3D.
    function makeTexture(kind, pal, score) {
      var c = document.createElement('canvas');
      c.width = 256; c.height = 456;
      var g = c.getContext('2d');
      roundRect(g, 4, 4, 248, 448, 30);
      g.save();
      g.clip();
      var grad = g.createLinearGradient(0, 0, 256, 456);
      grad.addColorStop(0, pal[0]);
      grad.addColorStop(1, pal[1]);
      g.fillStyle = grad;
      g.fillRect(0, 0, 256, 456);
      g.fillStyle = 'rgba(255,255,255,0.07)';
      g.fillRect(0, 0, 256, 140);

      if (kind === 0) { // lecture
        g.fillStyle = 'rgba(255,255,255,0.92)';
        g.beginPath(); g.arc(128, 190, 46, 0, Math.PI * 2); g.fill();
        g.fillStyle = pal[0];
        g.beginPath(); g.moveTo(116, 168); g.lineTo(116, 212); g.lineTo(150, 190); g.closePath(); g.fill();
      } else if (kind === 1) { // barres qui montent
        var hs = [50, 82, 116, 156];
        for (var i = 0; i < hs.length; i++) {
          g.fillStyle = 'rgba(255,255,255,' + (0.35 + i * 0.18) + ')';
          roundRect(g, 52 + i * 38, 262 - hs[i], 26, hs[i], 7);
          g.fill();
        }
      } else if (kind === 2) { // cœur
        g.fillStyle = 'rgba(255,255,255,0.93)';
        g.beginPath();
        g.moveTo(128, 232);
        g.bezierCurveTo(58, 187, 88, 132, 128, 165);
        g.bezierCurveTo(168, 132, 198, 187, 128, 232);
        g.fill();
      } else { // jauge
        g.lineWidth = 16; g.lineCap = 'round';
        g.strokeStyle = 'rgba(255,255,255,0.28)';
        g.beginPath(); g.arc(128, 190, 52, 0, Math.PI * 2); g.stroke();
        g.strokeStyle = 'rgba(255,255,255,0.95)';
        g.beginPath(); g.arc(128, 190, 52, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (score / 100)); g.stroke();
      }
      g.restore();

      g.fillStyle = 'rgba(255,255,255,0.96)';
      roundRect(g, 58, 366, 140, 52, 26);
      g.fill();
      g.fillStyle = '#16A34A';
      g.font = 'bold 30px Inter, system-ui, sans-serif';
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillText('↑ ' + score, 128, 393);

      roundRect(g, 4, 4, 248, 448, 30);
      g.strokeStyle = 'rgba(255,255,255,0.35)';
      g.lineWidth = 3;
      g.stroke();

      var tex = new THREE.CanvasTexture(c);
      tex.anisotropy = 4;
      return tex;
    }

    var materials = [];
    for (var m = 0; m < 10; m++) {
      var score = [71, 78, 84, 88, 92, 95][m % 6];
      var map = makeTexture(m % 4, PALETTES[m % PALETTES.length], score);
      materials.push(new THREE.MeshBasicMaterial({ map: map, transparent: true, side: THREE.DoubleSide, depthWrite: false }));
    }

    var planeGeo = new THREE.PlaneGeometry(1.5, 2.67);
    var cards = [];
    for (var i = 0; i < CARD_COUNT; i++) {
      var mesh = new THREE.Mesh(planeGeo, materials[i % materials.length]);
      var card = {
        mesh: mesh,
        angle: i * 2.399963,
        radius: 2.7 + (i % 4) * 0.75 + Math.random() * 0.4,
        z: -(i / CARD_COUNT) * DEPTH,
        tilt: (Math.random() - 0.5) * 0.9,
        spin: (Math.random() - 0.5) * 0.3
      };
      cards.push(card);
      scene.add(mesh);
    }

    var rings = [];
    var ringGeo = new THREE.TorusGeometry(8, 0.025, 8, 96);
    var ringMat = new THREE.MeshBasicMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.4 });
    for (var r = 0; r < 12; r++) {
      var ring = new THREE.Mesh(ringGeo, ringMat);
      ring.position.z = -(r / 12) * DEPTH;
      rings.push(ring);
      scene.add(ring);
    }

    var P = small ? 260 : 520;
    var pos = new Float32Array(P * 3);
    for (var p = 0; p < P; p++) {
      var a = Math.random() * Math.PI * 2, rad = 1.5 + Math.random() * 7;
      pos[p * 3] = Math.cos(a) * rad;
      pos[p * 3 + 1] = Math.sin(a) * rad;
      pos[p * 3 + 2] = -Math.random() * DEPTH;
    }
    var pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    var points = new THREE.Points(pGeo, new THREE.PointsMaterial({ color: 0x93c5fd, size: 0.07, transparent: true, opacity: 0.75, sizeAttenuation: true }));
    scene.add(points);

    var tx = 0, ty = 0, elapsed = 0;
    function update(dt) {
      elapsed += dt;
      for (var i = 0; i < cards.length; i++) {
        var c = cards[i];
        c.z += SPEED * dt;
        if (c.z > 3) c.z -= DEPTH;
        c.angle += dt * 0.12;
        c.mesh.position.set(Math.cos(c.angle) * c.radius, Math.sin(c.angle) * c.radius, c.z);
        c.mesh.lookAt(0, 0, c.z);
        c.mesh.rotateZ(c.tilt + elapsed * c.spin);
      }
      for (var j = 0; j < rings.length; j++) {
        rings[j].position.z += SPEED * dt;
        if (rings[j].position.z > 3) rings[j].position.z -= DEPTH;
      }
      var arr = pGeo.attributes.position.array;
      for (var k = 0; k < P; k++) {
        arr[k * 3 + 2] += SPEED * 1.5 * dt;
        if (arr[k * 3 + 2] > 3) arr[k * 3 + 2] -= DEPTH;
      }
      pGeo.attributes.position.needsUpdate = true;
      camera.rotation.y += (-tx * 0.2 - camera.rotation.y) * 0.05;
      camera.rotation.x += (ty * 0.12 - camera.rotation.x) * 0.05;
      camera.rotation.z = Math.sin(elapsed * 0.25) * 0.05;
    }

    function resize() {
      var w = hero.clientWidth, h = hero.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    if (window.ResizeObserver) { new ResizeObserver(resize).observe(hero); } else { window.addEventListener('resize', resize); }

    hero.addEventListener('pointermove', function (e) {
      tx = (e.clientX / window.innerWidth - 0.5) * 2;
      ty = (e.clientY / window.innerHeight - 0.5) * 2;
    });

    update(0);
    renderer.render(scene, camera);
    canvas.classList.add('ready');
    if (reduceMotion) return;

    var last = 0, raf = 0, visible = true;
    function frame(now) {
      raf = requestAnimationFrame(frame);
      var dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      update(dt);
      renderer.render(scene, camera);
    }
    function play() { if (!raf && visible && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); } }
    function pause() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (entries) { visible = entries[0].isIntersecting; visible ? play() : pause(); }).observe(hero);
    }
    document.addEventListener('visibilitychange', function () { document.hidden ? pause() : play(); });
    play();
  }

  if (document.readyState === 'complete') { start(); } else { window.addEventListener('load', start); }
})();
