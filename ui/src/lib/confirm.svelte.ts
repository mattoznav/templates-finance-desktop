export interface ConfirmRequest {
	title: string;
	message: string;
	confirm?: string;
	danger?: boolean;
	resolve: (ok: boolean) => void;
}

class Confirmations {
	current = $state<ConfirmRequest | null>(null);

	ask(options: Omit<ConfirmRequest, 'resolve'>): Promise<boolean> {
		return new Promise((resolve) => {
			this.current = { ...options, resolve };
		});
	}

	answer(ok: boolean): void {
		this.current?.resolve(ok);
		this.current = null;
	}
}

export const confirmations = new Confirmations();
export const confirmAction = (options: Omit<ConfirmRequest, 'resolve'>) => confirmations.ask(options);
