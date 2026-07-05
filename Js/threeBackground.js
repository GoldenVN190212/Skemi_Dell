import * as THREE from 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.module.min.js';

class ThreeBackground {
    constructor() {
        this.container = document.createElement('div');
        this.container.id = 'three-canvas-container';
        this.container.style.position = 'fixed';
        this.container.style.top = '0';
        this.container.style.left = '0';
        this.container.style.width = '100vw';
        this.container.style.height = '100vh';
        this.container.style.zIndex = '-2'; // Behind everything
        this.container.style.pointerEvents = 'none';
        this.container.style.opacity = '0.7';
        document.body.appendChild(this.container);

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.container.appendChild(this.renderer.domElement);

        this.mouse = { x: 0, y: 0 };
        this.targetMouse = { x: 0, y: 0 };
        this.clock = new THREE.Clock();

        this.initParticles();
        this.initCore();
        this.camera.position.z = 5.5; // Moved even closer to make it look HUGE

        this.animate();

        // Listen for performance toggle
        window.addEventListener('storage', (e) => {
            if (e.key === 'skemi-performance-3d') {
                this.updatePerformanceMode();
            }
        });
        this.updatePerformanceMode();

        window.addEventListener('resize', () => this.onResize());
        window.addEventListener('mousemove', (e) => this.onMouseMove(e));
    }

    updatePerformanceMode() {
        this.isHighPerf = localStorage.getItem('skemi-performance-3d') !== 'false';
        if (this.particles) {
            this.particles.visible = true;
        }
        if (this.core) {
            this.core.material.wireframe = true;
            this.core.material.opacity = this.isHighPerf ? 0.7 : 0.4;
        }
    }

    initParticles() {
        const particlesGeometry = new THREE.BufferGeometry();
        const count = 2000;
        const positions = new Float32Array(count * 3);
        const colors = new Float32Array(count * 3);

        const color1 = new THREE.Color(0xf472b6); // Pink
        const color2 = new THREE.Color(0xa855f7); // Purple

        for (let i = 0; i < count * 3; i += 3) {
            positions[i] = (Math.random() - 0.5) * 20;
            positions[i + 1] = (Math.random() - 0.5) * 20;
            positions[i + 2] = (Math.random() - 0.5) * 20;

            const mixedColor = color1.clone().lerp(color2, Math.random());
            colors[i] = mixedColor.r;
            colors[i + 1] = mixedColor.g;
            colors[i + 2] = mixedColor.b;
        }

        particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        particlesGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const particlesMaterial = new THREE.PointsMaterial({
            size: 0.015,
            vertexColors: true,
            transparent: true,
            opacity: 0.4,
            blending: THREE.AdditiveBlending
        });

        this.particles = new THREE.Points(particlesGeometry, particlesMaterial);
        this.scene.add(this.particles);
    }

    initCore() {
        // Morphing Core (Icosahedron for organic look) - enlarged to 3.6 for "HUGE" feel
        const geometry = new THREE.IcosahedronGeometry(3.6, 16); 
        this.originalPositions = geometry.attributes.position.array.slice();
        
        const material = new THREE.MeshPhongMaterial({
            color: 0xa855f7,
            emissive: 0xf472b6,
            emissiveIntensity: 0.8,
            wireframe: true,
            transparent: true,
            opacity: 0.7,
            blending: THREE.AdditiveBlending
        });

        this.core = new THREE.Mesh(geometry, material);
        this.scene.add(this.core);

        const light = new THREE.PointLight(0xf472b6, 3, 30);
        light.position.set(5, 5, 5);
        this.scene.add(light);
        this.scene.add(new THREE.AmbientLight(0x404040));
    }

    onMouseMove(e) {
        this.targetMouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
        this.targetMouse.y = -(e.clientY / window.innerHeight - 0.5) * 2;
    }

    onResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        const time = this.clock.getElapsedTime();

        // Parallax Smoothing
        this.mouse.x += (this.targetMouse.x - this.mouse.x) * 0.05;
        this.mouse.y += (this.targetMouse.y - this.mouse.y) * 0.05;

        // Animate Particles Parallax
        this.particles.rotation.y = time * 0.05 + this.mouse.x * 0.1;
        this.particles.rotation.x = this.mouse.y * 0.1;

        // Morph Core - Only if high performance is enabled
        if (this.isHighPerf) {
            const positions = this.core.geometry.attributes.position.array;
            for (let i = 0; i < positions.length; i += 3) {
                const ix = this.originalPositions[i];
                const iy = this.originalPositions[i + 1];
                const iz = this.originalPositions[i + 2];

                // More organic noise
                const noise = Math.sin(ix * 1.5 + time) * 0.25 + 
                              Math.cos(iy * 2.0 + time * 0.8) * 0.25 + 
                              Math.sin(iz * 1.8 + time * 1.1) * 0.25;
                
                positions[i] = ix * (1 + noise);
                positions[i + 1] = iy * (1 + noise);
                positions[i + 2] = iz * (1 + noise);
            }
            this.core.geometry.attributes.position.needsUpdate = true;
        }
        this.core.rotation.y = time * 0.2;
        this.core.rotation.z = time * 0.1;

        // Move Core with Mouse
        this.core.position.x = this.mouse.x * 0.5;
        this.core.position.y = this.mouse.y * 0.5;

        this.renderer.render(this.scene, this.camera);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.skemiBackground = new ThreeBackground();
});
