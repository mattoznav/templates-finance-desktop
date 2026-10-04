import { ApiError } from './api.ts';

export interface Toast {
	id: number;
	text: string;
	tone: 'info' | 'error';
}

class Toasts {
	items = $state<Toast[]>([]);
	private next = 1;

	show(text: string, tone: Toast['tone'] = 'info'): void {
		const id = this.next++;
		this.items = [...this.items, { id, text, tone }];
		setTimeout(() => this.dismiss(id), tone === 'error' ? 6000 : 3200);
	}

	error(err: unknown): void {
		// The lock screen already explains a locked vault.
		if (err instanceof ApiError && err.code === 'locked') return;
		this.show(err instanceof Error ? err.message : String(err), 'error');
	}

	dismiss(id: number): void {
		this.items = this.items.filter((t) => t.id !== id);
	}
}

export const toasts = new Toasts();
