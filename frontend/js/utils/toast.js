// F25 FIX: Toast notification system — delegates to global showToast() in app.js
// Previously had its own implementation that could conflict
const toast = {
    show(message, type = 'info') {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            console.warn(`[toast] ${type}: ${message}`);
        }
    },

    success(message) {
        this.show(message, 'success');
    },

    error(message) {
        this.show(message, 'error');
    },

    info(message) {
        this.show(message, 'info');
    },

    warning(message) {
        this.show(message, 'warning');
    }
};
