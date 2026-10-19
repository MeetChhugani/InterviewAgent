import axios from 'axios';

// Local development defaults to FastAPI on port 8000. For a shared demo,
// set VITE_API_URL to the public backend tunnel URL before starting Vite.
const apiBaseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 15000,
});

export { apiBaseUrl };
