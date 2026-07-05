// OmniSphere.js - The Infinite Knowledge Sphere
let scene, camera, renderer, particles, lines;
let animationId;
let isInitialized = false;

export function initOmniSphere(canvasId = 'omniSphereCanvas') {
    if (isInitialized) return;
    
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    // Safety check for THREE
    if (typeof THREE === 'undefined') {
        console.error('Three.js is required for Omni-Synapse');
        return;
    }

    const container = canvas.parentElement;

    scene = new THREE.Scene();
    
    camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.z = 200;

    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);

    // Particle nodes
    const particleGeometry = new THREE.BufferGeometry();
    const particleCount = 200;
    
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    
    const color = new THREE.Color();
    const baseColor = new THREE.Color(0xa855f7); // Brand primary

    for(let i = 0; i < particleCount * 3; i+=3) {
        // Sphere distribution
        const r = 100 + Math.random() * 20;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos((Math.random() * 2) - 1);
        
        positions[i] = r * Math.sin(phi) * Math.cos(theta); // x
        positions[i+1] = r * Math.sin(phi) * Math.sin(theta); // y
        positions[i+2] = r * Math.cos(phi); // z

        color.copy(baseColor).lerp(new THREE.Color(0xffffff), Math.random() * 0.3);
        colors[i] = color.r;
        colors[i+1] = color.g;
        colors[i+2] = color.b;
    }

    particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particleGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const particleMaterial = new THREE.PointsMaterial({
        size: 3,
        vertexColors: true,
        transparent: true,
        opacity: 0.8,
        blending: THREE.AdditiveBlending
    });

    particles = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(particles);

    // Neural connections
    const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xa855f7,
        transparent: true,
        opacity: 0.15,
        blending: THREE.AdditiveBlending
    });
    
    lines = new THREE.LineSegments(
        new THREE.WireframeGeometry(new THREE.SphereGeometry(105, 12, 12)),
        lineMaterial
    );
    scene.add(lines);

    isInitialized = true;
    animate();
    
    // Expose for Search.js
    window.pulseSphere = pulseSphere;
    window.relaxSphere = relaxSphere;

    window.addEventListener('resize', () => {
        if (!container) return;
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });
}

export function pulseSphere() {
    if (!particles) return;
    
    if (typeof gsap !== 'undefined') {
        gsap.to(particles.material, {size: 6, opacity: 1, duration: 0.3, yoyo: true, repeat: 1});
        gsap.to(camera.position, {z: 150, duration: 2, ease: "power2.out"});
    }
}

export function relaxSphere() {
    if (!camera) return;
    if (typeof gsap !== 'undefined') {
        gsap.to(camera.position, {z: 200, duration: 3, ease: "power2.inOut"});
    }
}

function animate() {
    animationId = requestAnimationFrame(animate);
    
    if (particles) {
        particles.rotation.y += 0.002;
        particles.rotation.x += 0.001;
    }
    
    if (lines) {
        lines.rotation.y += 0.0015;
    }

    renderer.render(scene, camera);
}

// Auto-init if container exists
function tryInit() {
    if (document.getElementById('omniSphereCanvas')) {
        initOmniSphere();
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInit);
} else {
    tryInit();
}
