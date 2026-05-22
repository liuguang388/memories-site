/**
 * 粒子背景动画 - 金色微粒星空效果
 */
(function() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;
    
    // 配置
    const config = {
        particleCount: 80,
        minSize: 0.5,
        maxSize: 2.5,
        minSpeed: 0.1,
        maxSpeed: 0.4,
        colors: [
            'rgba(212, 175, 55, 0.6)',   // gold
            'rgba(240, 208, 96, 0.4)',   // light gold
            'rgba(184, 148, 31, 0.5)',   // dark gold
            'rgba(255, 255, 255, 0.2)',  // white
            'rgba(200, 180, 140, 0.3)',  // warm
        ]
    };
    
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    
    class Particle {
        constructor() {
            this.reset();
            // Random initial position
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
        }
        
        reset() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.size = config.minSize + Math.random() * (config.maxSize - config.minSize);
            this.speedX = (Math.random() - 0.5) * config.maxSpeed * 2;
            this.speedY = config.minSpeed + Math.random() * (config.maxSpeed - config.minSpeed);
            this.color = config.colors[Math.floor(Math.random() * config.colors.length)];
            this.opacity = 0.3 + Math.random() * 0.7;
            this.pulseSpeed = 0.005 + Math.random() * 0.015;
            this.pulseOffset = Math.random() * Math.PI * 2;
        }
        
        update() {
            this.y -= this.speedY;
            this.x += this.speedX;
            
            // Wrap around
            if (this.y < -10) {
                this.y = canvas.height + 10;
                this.x = Math.random() * canvas.width;
            }
            if (this.x < -10) this.x = canvas.width + 10;
            if (this.x > canvas.width + 10) this.x = -10;
            
            // Pulse opacity
            this.currentOpacity = this.opacity * (0.6 + 0.4 * Math.sin(Date.now() * this.pulseSpeed + this.pulseOffset));
        }
        
        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = this.color.replace(/[\d.]+\)$/, `${this.currentOpacity})`);
            ctx.fill();
            
            // Glow effect for larger particles
            if (this.size > 1.5) {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size * 2.5, 0, Math.PI * 2);
                ctx.fillStyle = this.color.replace(/[\d.]+\)$/, `${this.currentOpacity * 0.15})`);
                ctx.fill();
            }
        }
    }
    
    function init() {
        resize();
        particles = [];
        for (let i = 0; i < config.particleCount; i++) {
            particles.push(new Particle());
        }
    }
    
    function connectParticles() {
        const maxDist = 150;
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                
                if (dist < maxDist) {
                    const opacity = (1 - dist / maxDist) * 0.08;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(212, 175, 55, ${opacity})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }
    
    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        particles.forEach(p => {
            p.update();
            p.draw(ctx);
        });
        
        connectParticles();
        animationId = requestAnimationFrame(animate);
    }
    
    // Handle resize
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            resize();
            particles.forEach(p => p.reset());
        }, 200);
    });
    
    // Handle visibility change to save resources
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            cancelAnimationFrame(animationId);
        } else {
            animate();
        }
    });
    
    init();
    animate();
})();
