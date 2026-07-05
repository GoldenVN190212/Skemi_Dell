/**
 * Skemi Galaxy Engine v1.0
 * Real moving starfield and nebula background for Galaxy Mode
 */

class GalaxyEngine {
    constructor() {
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stars = [];
        this.starCount = 200;
        this.nebulae = [];
        this.active = false;
        
        this.init();
    }

    init() {
        this.canvas.id = 'galaxy-canvas';
        this.canvas.style.position = 'fixed';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.width = '100vw';
        this.canvas.style.height = '100vh';
        this.canvas.style.zIndex = '-1';
        this.canvas.style.pointerEvents = 'none';
        this.canvas.style.transition = 'opacity 1s ease';
        this.canvas.style.opacity = '0';
        
        document.body.prepend(this.canvas);
        
        window.addEventListener('resize', () => this.resize());
        this.resize();
        this.createStars();
        this.animate();
        
        this.checkTheme();
        
        // Listen for theme changes
        const observer = new MutationObserver(() => this.checkTheme());
        observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    createStars() {
        this.stars = [];
        for (let i = 0; i < this.starCount; i++) {
            this.stars.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                size: Math.random() * 2,
                speedX: (Math.random() - 0.5) * 0.2,
                speedY: (Math.random() - 0.5) * 0.2,
                opacity: Math.random()
            });
        }
    }

    checkTheme() {
        const isGalaxy = document.body.classList.contains('galaxy-mode');
        if (isGalaxy && !this.active) {
            this.active = true;
            this.canvas.style.opacity = '1';
        } else if (!isGalaxy && this.active) {
            this.active = false;
            this.canvas.style.opacity = '0';
        }
    }

    drawNebula() {
        const gradient = this.ctx.createRadialGradient(
            this.canvas.width * 0.5, this.canvas.height * 0.2, 0,
            this.canvas.width * 0.5, this.canvas.height * 0.2, this.canvas.width * 0.8
        );
        gradient.addColorStop(0, 'rgba(99, 102, 241, 0.15)');
        gradient.addColorStop(0.5, 'rgba(168, 85, 247, 0.05)');
        gradient.addColorStop(1, 'transparent');
        
        this.ctx.fillStyle = gradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    animate() {
        if (this.active) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.drawNebula();
            
            this.ctx.fillStyle = 'white';
            this.stars.forEach(star => {
                star.x += star.speedX;
                star.y += star.speedY;
                
                // Wrap around
                if (star.x < 0) star.x = this.canvas.width;
                if (star.x > this.canvas.width) star.x = 0;
                if (star.y < 0) star.y = this.canvas.height;
                if (star.y > this.canvas.height) star.y = 0;
                
                this.ctx.globalAlpha = star.opacity * (Math.sin(Date.now() * 0.001 + star.x) * 0.5 + 0.5);
                this.ctx.beginPath();
                this.ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
                this.ctx.fill();
            });
            this.ctx.globalAlpha = 1.0;
        }
        
        requestAnimationFrame(() => this.animate());
    }
}

// Instantiate
new GalaxyEngine();
