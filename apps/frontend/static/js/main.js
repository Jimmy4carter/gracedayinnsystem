// Graceday Inn - Main JavaScript

// Public site template behavior (preloader/menu/widgets)
(function ($) {
    function hidePreloader() {
        const preloder = document.getElementById('preloder');
        if (!preloder) {
            return;
        }

        if ($ && typeof $.fn.fadeOut === 'function') {
            $('.loader').fadeOut();
            $('#preloder').delay(200).fadeOut('slow');
            return;
        }

        preloder.style.opacity = '0';
        preloder.style.visibility = 'hidden';
        preloder.style.pointerEvents = 'none';
    }

    // Ensure preloader always clears even if another plugin errors.
    if (typeof globalThis.window !== 'undefined') {
        globalThis.window.addEventListener('load', hidePreloader);
        document.addEventListener('DOMContentLoaded', function () {
            setTimeout(hidePreloader, 1200);
        });
        setTimeout(hidePreloader, 0);
        setTimeout(hidePreloader, 400);
    }

    if (!$) {
        return;
    }

    $('.set-bg').each(function () {
        let bg = $(this).data('setbg');
        $(this).css('background-image', 'url(' + bg + ')');
    });

    $('.canvas-open').on('click', function () {
        $('.offcanvas-menu-wrapper').addClass('show-offcanvas-menu-wrapper');
        $('.offcanvas-menu-overlay').addClass('active');
    });

    $('.canvas-close, .offcanvas-menu-overlay').on('click', function () {
        $('.offcanvas-menu-wrapper').removeClass('show-offcanvas-menu-wrapper');
        $('.offcanvas-menu-overlay').removeClass('active');
    });

    $('.search-switch').on('click', function () {
        $('.search-model').fadeIn(400);
    });

    $('.search-close-switch').on('click', function () {
        $('.search-model').fadeOut(400, function () {
            $('#search-input').val('');
        });
    });

    if (typeof $.fn.slicknav === 'function') {
        $('.mobile-menu').slicknav({
            prependTo: '#mobile-menu-wrap',
            allowParentLinks: true,
        });
    }

    if (typeof $.fn.owlCarousel === 'function') {
        $('.hero-slider').owlCarousel({
            loop: true,
            margin: 0,
            items: 1,
            dots: true,
            animateOut: 'fadeOut',
            animateIn: 'fadeIn',
            smartSpeed: 1200,
            autoHeight: false,
            autoplay: true,
            mouseDrag: false,
        });

        $('.testimonial-slider').owlCarousel({
            items: 1,
            dots: false,
            autoplay: true,
            loop: true,
            smartSpeed: 1200,
            nav: true,
            navText: ["<i class='arrow_left'></i>", "<i class='arrow_right'></i>"],
        });
    }

    if (typeof $.fn.magnificPopup === 'function') {
        $('.video-popup').magnificPopup({
            type: 'iframe',
        });
    }

    if (typeof $.fn.datepicker === 'function') {
        $('.date-input').datepicker({
            minDate: 0,
            dateFormat: 'dd MM, yy',
        });
    }

    if (typeof $.fn.niceSelect === 'function') {
        $('select').niceSelect();
    }
})(globalThis.jQuery);

const API_BASE = '/api';
let authToken = localStorage.getItem('access_token');

// API Client
const api = {
    async request(method, endpoint, data = null) {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const config = { method, headers };
        if (data) config.body = JSON.stringify(data);
        const resp = await fetch(`${API_BASE}${endpoint}`, config);
        if (resp.status === 401) {
            const refreshed = await this.refreshToken();
            if (refreshed) return this.request(method, endpoint, data);
            window.location.href = '/login/';
            return;
        }
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(JSON.stringify(err));
        }
        if (resp.status === 204) return null;
        return resp.json();
    },

    async refreshToken() {
        const refresh = localStorage.getItem('refresh_token');
        if (!refresh) return false;
        try {
            const resp = await fetch(`${API_BASE}/accounts/token/refresh/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh }),
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            authToken = data.access;
            localStorage.setItem('access_token', authToken);
            return true;
        } catch { return false; }
    },

    get: (ep) => api.request('GET', ep),
    post: (ep, d) => api.request('POST', ep, d),
    put: (ep, d) => api.request('PUT', ep, d),
    patch: (ep, d) => api.request('PATCH', ep, d),
    delete: (ep) => api.request('DELETE', ep),
};

// Toast Notifications
const toast = {
    container: null,
    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },
    show(message, type = 'info', duration = 4000) {
        this.init();
        const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `<span>${icons[type] || icons.info}</span><span>${message}</span>`;
        this.container.appendChild(el);
        setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(100%)';
            setTimeout(() => el.remove(), 300); }, duration);
    },
    success: (msg) => toast.show(msg, 'success'),
    error: (msg) => toast.show(msg, 'error'),
    warning: (msg) => toast.show(msg, 'warning'),
    info: (msg) => toast.show(msg, 'info'),
};

// Modal helpers
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('active');
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('active');
}

// Status badge helper
function statusBadge(status) {
    const map = {
        available: 'badge-success', occupied: 'badge-danger',
        housekeeping: 'badge-warning', maintenance: 'badge-info',
        confirmed: 'badge-success', pending: 'badge-warning',
        checked_in: 'badge-info', checked_out: 'badge-secondary',
        cancelled: 'badge-danger', paid: 'badge-success',
        partially_paid: 'badge-warning', overdue: 'badge-danger',
        draft: 'badge-secondary', completed: 'badge-success',
        in_progress: 'badge-info', out_of_order: 'badge-danger',
    };
    const cls = map[status] || 'badge-secondary';
    return `<span class="badge ${cls}">${status.replace(/_/g, ' ')}</span>`;
}

// Format currency
function formatCurrency(amount) {
    return '$' + parseFloat(amount || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Format date
function formatDate(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric'
    });
}

// Auth check
function requireAuth() {
    if (!authToken) {
        window.location.href = '/login/';
        return false;
    }
    return true;
}

// Load current user info
async function loadUserInfo() {
    if (!authToken) return;
    try {
        const user = await api.get('/accounts/users/me/');
        const el = document.getElementById('user-name');
        if (el) el.textContent = user.first_name || user.username;
        const roleEl = document.getElementById('user-role');
        if (roleEl) roleEl.textContent = user.role;
    } catch (e) {}
}

// Logout
async function logout() {
    try {
        await api.post('/accounts/users/logout/', {
            refresh: localStorage.getItem('refresh_token')
        });
    } catch (e) {}
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login/';
}

// Load unread notifications count
async function loadNotificationCount() {
    if (!authToken) return;
    try {
        const data = await api.get('/notifications/unread_count/');
        const el = document.getElementById('notif-count');
        if (el) {
            el.textContent = data.count;
            el.style.display = data.count > 0 ? 'inline' : 'none';
        }
    } catch (e) {}
}

// Init on page load
document.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    loadNotificationCount();

    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', logout);

    // Close modals on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('active');
        });
    });

    // Mobile sidebar toggle
    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            document.querySelector('.sidebar').classList.toggle('open');
        });
    }
});
