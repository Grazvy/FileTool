// API client for communicating with backend

class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}/api${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    async healthCheck() {
        return this.request('/health');
    }

    async processFiles(data) {
        return this.request('/process', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
}

// Global API client instance
const api = new ApiClient();