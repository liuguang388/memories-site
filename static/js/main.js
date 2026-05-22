/**
 * 记忆时光 - 主脚本
 * 处理导航滚动效果、移动端菜单等通用功能
 */

(function() {
    // ─── Navbar Scroll Effect ───────────────────────────────────
    const navbar = document.getElementById('navbar');
    let lastScroll = 0;
    
    function handleScroll() {
        const scrollY = window.scrollY;
        
        if (navbar) {
            if (scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        }
        
        lastScroll = scrollY;
    }
    
    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll(); // Initial check
    
    // ─── Mobile Menu Toggle ────────────────────────────────────
    const mobileToggle = document.getElementById('mobileToggle');
    const mobileMenu = document.getElementById('mobileMenu');
    
    if (mobileToggle && mobileMenu) {
        mobileToggle.addEventListener('click', () => {
            mobileMenu.classList.toggle('active');
            // Animate hamburger
            const spans = mobileToggle.querySelectorAll('span');
            if (mobileMenu.classList.contains('active')) {
                spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
                spans[1].style.opacity = '0';
                spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
            } else {
                spans[0].style.transform = '';
                spans[1].style.opacity = '';
                spans[2].style.transform = '';
            }
        });
        
        // Close mobile menu when clicking a link
        mobileMenu.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                mobileMenu.classList.remove('active');
                const spans = mobileToggle.querySelectorAll('span');
                spans[0].style.transform = '';
                spans[1].style.opacity = '';
                spans[2].style.transform = '';
            });
        });
    }
    
    // ─── Hero Scroll Indicator ─────────────────────────────────
    const heroScroll = document.querySelector('.hero-scroll');
    if (heroScroll) {
        heroScroll.addEventListener('click', () => {
            const categories = document.getElementById('categories');
            if (categories) {
                categories.scrollIntoView({ behavior: 'smooth' });
            }
        });
    }
    
    // ─── Smooth Scroll for Anchor Links ────────────────────────
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
    
    // ─── Auto-dismiss Flash Messages ───────────────────────────
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transform = 'translateX(30px)';
            msg.style.transition = 'all 0.3s ease';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });
    
    // ─── Image Lazy Loading with Fade ──────────────────────────
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    img.style.opacity = '1';
                    imageObserver.unobserve(img);
                }
            });
        }, { rootMargin: '100px' });
        
        document.querySelectorAll('img[loading="lazy"]').forEach(img => {
            img.style.opacity = '0';
            img.style.transition = 'opacity 0.5s ease';
            imageObserver.observe(img);
        });
    }
    
    // ─── Keyboard Shortcuts ────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        // Escape to close modals
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                modal.classList.remove('active');
            });
            // Also close lightbox
            const lightbox = document.getElementById('lightbox');
            if (lightbox && lightbox.classList.contains('active')) {
                lightbox.classList.remove('active');
                document.body.style.overflow = '';
            }
        }
    });
    
    // ─── Prevent body scroll when modal is open ────────────────
    const modalObserver = new MutationObserver(() => {
        const hasActiveModal = document.querySelector('.modal.active');
        const hasActiveLightbox = document.getElementById('lightbox')?.classList.contains('active');
        document.body.style.overflow = (hasActiveModal || hasActiveLightbox) ? 'hidden' : '';
    });
    
    document.querySelectorAll('.modal').forEach(modal => {
        modalObserver.observe(modal, { attributes: true, attributeFilter: ['class'] });
    });
    
})();
