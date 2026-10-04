// One function, `rpc`, reaches the Python core. In the desktop window it goes
// through pywebview's bridge; while developing in a browser it falls back to
// the local dev server (`python -m coffer.devserver`).

type RpcResult<T> = { ok: T } | { error: { code: string; message: string } };

interface PywebviewApi {
	rpc(command: string, args: unknown): Promise<RpcResult<unknown>>;
	choose_save_path(filename: string): Promise<string | null>;
}

declare global {
	interface Window {
		pywebview?: { api: PywebviewApi };
	}
}

const DEV_SERVER = 'http://127.0.0.1:1430/rpc';

export class ApiError extends Error {
	constructor(
		public code: string,
		message: string
	) {
		super(message);
	}
}

let bridge: Promise<PywebviewApi | null> | null = null;

function waitForBridge(): Promise<PywebviewApi | null> {
	if (bridge) return bridge;
	bridge = new Promise((resolve) => {
		if (window.pywebview?.api?.rpc) return resolve(window.pywebview.api);
		const onReady = () => resolve(window.pywebview?.api ?? null);
		window.addEventListener('pywebviewready', onReady, { once: true });
		// Only a development build may fall back to HTTP.
		if (import.meta.env.DEV) {
			setTimeout(() => {
				window.removeEventListener('pywebviewready', onReady);
				resolve(window.pywebview?.api ?? null);
			}, 700);
		}
	});
	return bridge;
}

const lockListeners = new Set<() => void>();

/** Called whenever the core reports that the vault is locked. */
export function onLocked(listener: () => void): () => void {
	lockListeners.add(listener);
	return () => lockListeners.delete(listener);
}

export async function rpc<T>(command: string, args: Record<string, unknown> = {}): Promise<T> {
	const api = await waitForBridge();
	let result: RpcResult<T>;
	if (api) {
		result = (await api.rpc(command, args)) as RpcResult<T>;
	} else {
		try {
			const response = await fetch(DEV_SERVER, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ command, args })
			});
			result = await response.json();
		} catch {
			throw new ApiError('unreachable', 'The Coffer core is not running');
		}
	}
	if ('error' in result) {
		if (result.error.code === 'locked') lockListeners.forEach((fn) => fn());
		throw new ApiError(result.error.code, result.error.message);
	}
	return result.ok;
}

export async function inDesktop(): Promise<boolean> {
	return (await waitForBridge()) !== null;
}

/** Saves text or base64 data where the user chooses. Returns false if cancelled. */
export async function saveFile(
	filename: string,
	write: (path: string) => Promise<unknown>,
	fallback: () => Promise<{ content: string; base64?: boolean }>
): Promise<boolean> {
	const api = await waitForBridge();
	if (api) {
		const path = await api.choose_save_path(filename);
		if (!path) return false;
		await write(path);
		return true;
	}
	const { content, base64 } = await fallback();
	const blob = base64
		? new Blob([Uint8Array.from(atob(content), (c) => c.charCodeAt(0))], { type: 'application/octet-stream' })
		: new Blob([content], { type: 'text/csv' });
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	link.click();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
	return true;
}

export function readFileText(file: File): Promise<string> {
	return file.text();
}

export async function readFileBase64(file: File): Promise<string> {
	const bytes = new Uint8Array(await file.arrayBuffer());
	let binary = '';
	for (let i = 0; i < bytes.length; i += 0x8000) {
		binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
	}
	return btoa(binary);
}
