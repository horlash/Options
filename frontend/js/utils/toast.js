// Toast notification system
const toast = {
    show(message, type = 'info') {
        const container = document.getElementById('toast-container');

        const toastEl = document.createElement('div');
        toastEl.className = `toast ${type}`;
        toastEl.textContent = message;

        container.appendChild(toastEl);

        // Auto remove after 3 seconds
        setTimeout(() => {
            toastEl.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                container.removeChild(toastEl);
            }, 300);
        }, 3000);
    },

    success(message) {
        this.show(message, 'success');
    },

    error(message) {
        this.show(message, 'error');
    },

    info(message) {
        this.show(message, 'info');
    }
};
