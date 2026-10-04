import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// The desktop window loads build/index.html from disk, so routing
			// lives in the URL hash and every asset path is relative.
			adapter: adapter(),
			router: { type: 'hash' },
			paths: { relative: true }
		})
	],
	server: { port: 1420, strictPort: true, host: '127.0.0.1' }
});
